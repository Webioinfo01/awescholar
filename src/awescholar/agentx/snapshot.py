"""Read/write access to <root>/data/agents-snapshot.json — the single source
of truth for the AgentX directory. All commands resolve the file through the
repository root, so the tooling operates on any AgentX checkout without
copying data.

Unlike the archive helpers elsewhere in awescholar, these functions take the
snapshot FILE PATH directly (the archive_path convention), not a root dir.
"""

import json
import os
import re

from .transform import normalize_homepage


def snapshot_path(root: str) -> str:
    """The snapshot file for an AgentX repository root."""
    return os.path.join(root, "data", "agents-snapshot.json")


def read_snapshot(snapshot_file: str) -> dict:
    with open(snapshot_file, encoding="utf-8") as f:
        return json.load(f)


def write_snapshot(snapshot_file: str, file: dict) -> None:
    """Sort into stable slug order, refresh counts.total, write pretty JSON.

    Stable slug order => deterministic diffs, and the daily workflow only
    commits when data actually changed; the file intentionally carries NO
    timestamp for the same reason. Slugs sort in plain codepoint order
    (`sorted`) — the TypeScript writer uses the same comparator, aligned
    after ICU localeCompare disagreed on digit-vs-underscore slugs.
    """
    file["agents"] = sorted(file["agents"], key=lambda a: a["slug"])
    file["counts"]["total"] = len(file["agents"])
    parent = os.path.dirname(snapshot_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(snapshot_file, "w", encoding="utf-8") as f:
        json.dump(file, f, indent=2, ensure_ascii=False)
        f.write("\n")


def slugify(text: str) -> str:
    """Lowercase, dash runs of non-alphanumerics, trim, cap at 64; never empty.

    Per-character stand-in for the TypeScript `/[^\\p{L}\\p{N}]+/u` regex
    (stdlib `re` has no `\\p{}`): `str.isalnum()` covers letters and numbers
    and is False for "_", so underscores become dashes just like in TS.
    """
    dashed = "".join(ch if ch.isalnum() else "-" for ch in text.lower())
    return re.sub("-+", "-", dashed).strip("-")[:64] or "agent"


def unique_slug(base: str, used: set[str]) -> str:
    """Unique slug against the already-used ones, "-2" suffix on collision."""
    slug = base
    while slug in used:
        slug = f"{slug}-2"
    used.add(slug)
    return slug


def _coalesce(value, fallback):
    """TypeScript `??`: fall back only on None, so 0 / "" / False survive."""
    return fallback if value is None else value


def merge_snapshot_agent(
    agent: dict,
    slug: str,
    github: dict | None,
    status: str,
    license_spdx: str | None,
) -> dict:
    """Merge refreshed GitHub fields without replacing curated snapshot metadata."""
    gh = github if github else {}
    homepage = normalize_homepage(agent.get("homepage"))
    if homepage is None:
        homepage = normalize_homepage(gh.get("homepage"))

    out = {
        "slug": slug,
        "name": agent.get("name"),
        "repo": agent.get("repo"),
        "githubUrl": agent.get("githubUrl"),
        "homepage": homepage,
        "paper": agent.get("paper"),
        "paperMeta": agent.get("paperMeta"),
        "category": agent.get("category"),
        "tags": agent.get("tags"),
        "language": _coalesce(gh.get("language"), agent.get("language")),
        "stars": _coalesce(gh.get("stargazers_count"), agent.get("stars")),
        "pushedAt": _coalesce(gh.get("pushed_at"), agent.get("pushedAt")),
        "openIssues": _coalesce(gh.get("open_issues_count"), agent.get("openIssues")),
        # github?.archived ?? agent.archived ?? false
        "archived": _coalesce(_coalesce(gh.get("archived"), agent.get("archived")), False),
        "license": _coalesce(license_spdx, agent.get("license")),
        "description": _coalesce(gh.get("description"), agent.get("description")),
        "status": status,
        "autoStableExempt": _coalesce(agent.get("autoStableExempt"), False),
        "source": _coalesce(agent.get("source"), "curated"),
        "sourceUrl": agent.get("sourceUrl"),
    }
    # Graveyard metadata rides along only when the record already carries it.
    if "retiredReason" in agent:
        out["retiredReason"] = agent["retiredReason"]
    if "retiredStars" in agent:
        out["retiredStars"] = agent["retiredStars"]
    return out
