"""Export archive papers with GitHub repos as AgentX candidate agents.

AgentX (the repo-first agent registry) consumes records shaped like its
data/agents-snapshot.json entries. This exporter turns paper-first archive
entries that carry a github.com codeUrl into that shape, so agentx can review
and ingest them without a paper-side re-format. Live repo metrics are fetched
when a token is available; otherwise the exporter falls back to what the
archive already knows and agentx's own refresh fills the rest.
"""

import json
import re

from .github import fetch_repo, owner_repo_from_url, stars_from_repo

# The nine AgentX user-intent category slugs; category labels live on the
# agentx side, so only slugs are validated here.
AGENTX_CATEGORIES = (
    "autonomous-research", "literature-writing", "bio-omics", "chem-drug",
    "clinical-health", "workbenches", "platforms", "orchestration",
    "evaluation-safety",
)


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
    team = str(paper.get("team") or "")
    return {
        "title": paper.get("title") or "",
        "venue": paper.get("venue") or "",
        "doi": paper.get("doi") or "",
        "year": paper.get("year") or "",
        "team": team,
        "firstAuthor": _first_author(team),
        "paperUrl": paper.get("paperUrl") or "",
    }


def _paper_url(paper: dict) -> str | None:
    url = paper.get("paperUrl") or ""
    if url:
        return url
    doi = paper.get("doi") or ""
    return f"https://doi.org/{doi}" if doi else None


def _category_for(archive_category: str, category_map: dict,
                  default_category: str, status_cb) -> str:
    slug = category_map.get(archive_category) or category_map.get(
        archive_category.strip().lower())
    if not slug:
        return default_category
    if slug not in AGENTX_CATEGORIES:
        status_cb(f"  Warning: '{slug}' is not a known agentx category "
                  f"(from '{archive_category}'); keeping it as-is")
    return slug


def _load_exclude_repos(path: str) -> set[str]:
    """Lowercased owner/name repos already present in an agentx snapshot file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("agents", []) if isinstance(data, dict) else data
    return {str(a.get("repo") or "").lower() for a in entries if a.get("repo")}


def export_agentx(archive_path: str, output_path: str, token: str | None = None,
                  category_map: dict | None = None, default_category: str = "platforms",
                  source: str = "awescholar", source_url: str | None = None,
                  categories: list[str] | None = None,
                  exclude_snapshot: str | None = None, status_cb=print) -> dict:
    """Write an AgentX-shaped candidate file from papers with GitHub repos."""
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
    exclude_repos = _load_exclude_repos(exclude_snapshot) if exclude_snapshot else set()

    agents = []
    used_slugs: set[str] = set()
    seen_repos: set[str] = set()
    skipped_no_repo = deduped_repos = excluded_snapshot = 0

    for archive_category, papers in archive.items():
        category = _category_for(archive_category, category_map, default_category, status_cb)
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

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"agents": agents, "counts": {"total": len(agents), "graveyard": 0}},
                  f, indent=2, ensure_ascii=False)
        f.write("\n")

    status_cb(f"Exported {len(agents)} agent candidates to {output_path} "
              f"({skipped_no_repo} papers without a GitHub repo skipped, "
              f"{deduped_repos} duplicate repos collapsed"
              + (f", {excluded_snapshot} repos already in the exclude snapshot"
                 if excluded_snapshot else "") + ")")
    return {"exported": len(agents), "skipped_no_repo": skipped_no_repo,
            "deduped_repos": deduped_repos, "excluded_snapshot": excluded_snapshot}
