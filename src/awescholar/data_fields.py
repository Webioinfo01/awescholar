"""Project data field normalization."""

import ast


def normalize_title(title) -> str:
    """Normalize a paper title for matching (case/whitespace-insensitive)."""
    return " ".join(str(title or "").split()).casefold()

PROJECT_PAPER_FIELDS = (
    "year",
    "title",
    "team",
    "team website",
    "affiliation",
    "domain",
    "venue",
    "paperUrl",
    "codeUrl",
    "githubStars",
    "doi",
)

UPDATER_PAPER_FIELDS = (
    "year",
    "title",
    "team",
    "team website",
    "affiliation",
    "domain",
    "abstract",
    "venue",
    "paperUrl",
    "codeUrl",
    "githubStars",
    "doi",
    "reason_for_inclusion",
)

FIELD_ALIASES = {
    "year": ("year", "publication_date", "publicationDate"),
    "title": ("title",),
    "team": ("team",),
    "team website": ("team website", "team_website", "teamWebsite"),
    "affiliation": ("affiliation",),
    "domain": ("domain",),
    "abstract": ("abstract",),
    "venue": ("venue", "journal"),
    "paperUrl": ("paperUrl", "paper_url", "url"),
    "codeUrl": ("codeUrl", "code_url", "codeURL"),
    "githubStars": ("githubStars", "github_stars", "githubStarsUrl"),
    "doi": ("doi", "DOI"),
    "reason_for_inclusion": ("reason_for_inclusion",),
}


def first_present(data: dict, *keys: str, default: str = ""):
    """Return the first non-empty value for any key."""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def normalize_name(name) -> str:
    """Normalize a person name for matching (case/period/whitespace-insensitive)."""
    return " ".join(str(name or "").replace(".", " ").split()).casefold()


def format_affiliations(affiliations) -> str:
    """Join an affiliation list for display; single source of truth for the separator."""
    return ", ".join(a for a in (affiliations or []) if a)


def _extract_team_name(authors: str) -> str:
    """Extract author name from the stored authors string.

    The search step stores authors as a JSON string, e.g.
    '{"name": "Yutaka Saito", "affiliations": ["The University of Tokyo"]}'.
    """
    if not authors:
        return ""
    if isinstance(authors, str):
        try:
            parsed = ast.literal_eval(authors)
            if isinstance(parsed, dict):
                return parsed.get("name") or ""
        except (ValueError, SyntaxError):
            return ""
    return ""


def _extract_affiliation(authors: str) -> str:
    """Extract affiliations from the stored authors string, joined for display."""
    if not authors:
        return ""
    if isinstance(authors, str):
        try:
            parsed = ast.literal_eval(authors)
            if isinstance(parsed, dict):
                return format_affiliations(parsed.get("affiliations") or [])
        except (ValueError, SyntaxError):
            return ""
    return ""


def normalize_paper(paper: dict, fields: tuple) -> dict:
    """Normalize paper dict to keep only the given fields."""
    entry = {}
    for field in fields:
        entry[field] = first_present(paper, *FIELD_ALIASES[field])

    # Extract team from authors if not already set
    if not entry.get("team"):
        entry["team"] = _extract_team_name(paper.get("authors", ""))

    if not entry.get("affiliation"):
        entry["affiliation"] = _extract_affiliation(paper.get("authors", ""))

    year = entry.get("year")
    if isinstance(year, str) and len(year) >= 7:
        entry["year"] = year[:7]

    return entry


def normalize_project_paper_fields(paper: dict) -> dict:
    """Project data (data.json) — 11 fields only."""
    return normalize_paper(paper, PROJECT_PAPER_FIELDS)


def normalize_updater_paper_fields(paper: dict) -> dict:
    """Updater pipeline (updater.json / updater_filter.json) — 13 fields."""
    return normalize_paper(paper, UPDATER_PAPER_FIELDS)


def merge_preserving_nonempty(existing: dict, incoming: dict) -> dict:
    """Merge incoming fields without clearing existing non-empty values."""
    merged = {**existing}
    for key, value in incoming.items():
        if value in (None, "") and existing.get(key) not in (None, ""):
            continue
        merged[key] = value
    return merged
