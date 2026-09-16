"""Export archive papers with GitHub repos as AgentX candidate agents.

AgentX (the repo-first agent registry) consumes records shaped like its
data/agents-snapshot.json entries. This exporter turns paper-first archive
entries that carry a github.com codeUrl into that shape, so agentx can review
and ingest them without a paper-side re-format. Live repo metrics are fetched
when a token is available; otherwise the exporter falls back to what the
archive already knows and agentx's own refresh fills the rest.

Category validation is driven entirely by the agentx exclude snapshot when one
is passed: its agents' `category` values are the source of truth for known
slugs. With no snapshot there is no validation, since awescholar has no other
way to know agentx's categories.
"""

import json
import os
import re
import shlex

from .github import fetch_repo, owner_repo_from_url, stars_from_repo


def agentx_slugify(text: str) -> str:
    """Mirror agentx slugify(): lowercase, non-alphanumeric runs to '-', trimmed."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:64]
    return slug or "agent"


def _first_author(team: str) -> str:
    for separator in (",", ";", " and "):
        if separator in team:
            return team.split(separator)[0].strip()
    return team.strip()


def _archive_stars(value) -> int:
    """Numeric star count from an archive field that may hold a legacy badge URL."""
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _paper_meta(paper: dict) -> dict:
    # The archive's full author list is authoritative when it was backfilled;
    # team (often just the first author) is the legacy fallback.
    authors = str(paper.get("authors") or paper.get("team") or "")
    return {
        "title": paper.get("title") or "",
        "venue": paper.get("venue") or "",
        "doi": paper.get("doi") or "",
        "year": paper.get("year") or "",
        "authors": authors,
        "firstAuthor": _first_author(authors),
        "paperUrl": paper.get("paperUrl") or "",
        "citations": paper.get("citations") or 0,
    }


def _paper_url(paper: dict) -> str | None:
    url = paper.get("paperUrl") or ""
    if url:
        return url
    doi = paper.get("doi") or ""
    return f"https://doi.org/{doi}" if doi else None


def _category_for(archive_category: str, category_map: dict,
                  default_category: str, known_categories: set[str],
                  status_cb) -> str:
    slug = category_map.get(archive_category) or category_map.get(
        archive_category.strip().lower())
    if not slug:
        return default_category
    if known_categories and slug not in known_categories:
        status_cb(f"  Warning: '{slug}' is not a category in the agentx snapshot "
                  f"(from '{archive_category}'); keeping it as-is")
    return slug


def _load_snapshot(path: str) -> tuple[set[str], set[str]]:
    """Load an agentx snapshot file: repo dedup set and known category slugs."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("agents", []) if isinstance(data, dict) else data
    repos = {str(a.get("repo") or "").lower() for a in entries if a.get("repo")}
    categories = {str(a["category"]) for a in entries if a.get("category")}
    return repos, categories


def _intake_command(agent: dict) -> str:
    """One `pnpm agent:add` line the target agentx repo can run as-is.

    Tags are deliberately omitted: the tag registry (which spellings are
    registered, e.g. Nature-BME) belongs to the target repo, whose agent:add
    validates it at run time.
    """
    parts = ["pnpm agent:add", agent["repo"], "--category", agent["category"]]
    if agent.get("name"):
        parts += ["--name", shlex.quote(str(agent["name"]))]
    if agent.get("paper"):
        parts += ["--paper", shlex.quote(str(agent["paper"]))]
    description = agent.get("description")
    if description:
        parts += ["--description", shlex.quote(str(description))]
    return " ".join(parts)


def export_agentx(archive_path: str, output_path: str, token: str | None = None,
                  category_map: dict | None = None, default_category: str = "platforms",
                  source: str = "awescholar", source_url: str | None = None,
                  categories: list[str] | None = None,
                  exclude_snapshot: str | None = None, emit: str = "json",
                  status_cb=print) -> dict:
    """Write an AgentX-shaped candidate file from papers with GitHub repos.

    `emit="json"` (default) writes the snapshot-shaped candidate JSON;
    `emit="commands"` writes an executable shell script of `pnpm agent:add`
    intake lines — one per candidate — for the last mile into an agentx repo.
    """
    category_map = category_map or {}
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)
    if categories is not None:
        wanted = {c.strip().lower() for c in categories}
        dropped = [c for c in archive if c.strip().lower() not in wanted]
        for c in dropped:
            archive.pop(c)
        if dropped:
            status_cb(f"Scoped to {sorted(archive)}; skipped categories: {dropped}")
    exclude_repos = set()
    known_categories = set()
    if exclude_snapshot:
        exclude_repos, known_categories = _load_snapshot(exclude_snapshot)

    if known_categories and default_category not in known_categories:
        status_cb(f"  Warning: '{default_category}' is not a category in the agentx "
                  f"snapshot; using it as the default fallback")

    agents = []
    used_slugs: set[str] = set()
    seen_repos: set[str] = set()
    skipped_no_repo = deduped_repos = excluded_snapshot = 0

    for archive_category, papers in archive.items():
        category = _category_for(archive_category, category_map, default_category,
                                 known_categories, status_cb)
        for p in papers:
            owner_repo = owner_repo_from_url(str(p.get("codeUrl") or ""))
            if not owner_repo:
                skipped_no_repo += 1
                continue
            if owner_repo.lower() in exclude_repos:
                excluded_snapshot += 1
                continue
            if owner_repo.lower() in seen_repos:
                deduped_repos += 1
                continue
            seen_repos.add(owner_repo.lower())

            repo = fetch_repo(owner_repo, token) if token else None
            name = (repo or {}).get("name") or owner_repo.split("/")[1]
            slug = agentx_slugify(name)
            while slug in used_slugs:
                slug = f"{slug}-2"
            used_slugs.add(slug)

            license_info = (repo or {}).get("license") or {}
            license_id = license_info.get("spdx_id")
            agents.append({
                "slug": slug,
                "name": name,
                "repo": owner_repo,
                "githubUrl": f"https://github.com/{owner_repo}",
                "homepage": p.get("team website") or (repo or {}).get("homepage"),
                "paper": _paper_url(p),
                "paperMeta": _paper_meta(p),
                "category": category,
                "tags": [],
                "language": (repo or {}).get("language"),
                "stars": stars_from_repo(repo) if repo else _archive_stars(p.get("githubStars")),
                "pushedAt": (repo or {}).get("pushed_at"),
                "openIssues": (repo or {}).get("open_issues_count", 0),
                "license": license_id if license_id not in (None, "NOASSERTION") else None,
                "description": (repo or {}).get("description"),
                "status": "active",
                "source": source,
                "sourceUrl": source_url,
            })

    if emit == "commands":
        lines = [
            "#!/usr/bin/env bash",
            f"# agentx intake commands generated by awescholar from {archive_path}",
            "# Review each line (categories and tags are the target repo's call), then run inside the agentx website repo.",
            "set -e",
            "",
        ]
        lines += [_intake_command(a) for a in agents]
        lines.append("")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        os.chmod(output_path, 0o755)
        status_cb(f"Exported {len(agents)} intake commands to {output_path} "
                  f"({skipped_no_repo} papers without a GitHub repo skipped, "
                  f"{deduped_repos} duplicate repos collapsed"
                  + (f", {excluded_snapshot} repos already in the exclude snapshot"
                     if excluded_snapshot else "") + ")")
        return {"exported": len(agents), "skipped_no_repo": skipped_no_repo,
                "deduped_repos": deduped_repos, "excluded_snapshot": excluded_snapshot}

    with open(output_path, "w", encoding="utf-8") as f:
        # agentx SnapshotFile counts contract is {total, gone}.
        json.dump({"agents": agents, "counts": {"total": len(agents), "gone": 0}},
                  f, indent=2, ensure_ascii=False)
        f.write("\n")

    status_cb(f"Exported {len(agents)} agent candidates to {output_path} "
              f"({skipped_no_repo} papers without a GitHub repo skipped, "
              f"{deduped_repos} duplicate repos collapsed"
              + (f", {excluded_snapshot} repos already in the exclude snapshot"
                 if excluded_snapshot else "") + ")")
    return {"exported": len(agents), "skipped_no_repo": skipped_no_repo,
            "deduped_repos": deduped_repos, "excluded_snapshot": excluded_snapshot}
