"""Backfill missing affiliation/team fields in an archive from the web.

Two sources are consulted, cheapest-per-coverage first:
1. Semantic Scholar — batch endpoints (papers, then authors); covers names
   and teams well, affiliations poorly.
2. Crossref — per-DOI work metadata; the primary source for author
   affiliations (publisher-deposited).

Only empty fields are filled, entries never move between categories, and
the affiliation always comes from the same author as the team, so the
pair can never mismatch.
"""

import json
import shutil
import time
import urllib.request
from datetime import datetime

from semanticscholar import SemanticScholar

from .data_fields import format_affiliations, normalize_name

PAPERS_PER_BATCH = 500
AUTHORS_PER_BATCH = 1000
BATCH_PAUSE_SECONDS = 1.0
CROSSREF_PAUSE_SECONDS = 0.4
CROSSREF_TIMEOUT_SECONDS = 15
CROSSREF_URL = "https://api.crossref.org/works/{doi}"


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _call_sch(fn, *args, **kwargs):
    """Call a SemanticScholar method with friendly rate-limit/auth errors."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        msg = str(e)
        if "403" in msg or "Forbidden" in msg:
            raise RuntimeError("Semantic Scholar API 403. Check your API key.") from e
        if "429" in msg:
            raise RuntimeError("Semantic Scholar rate limit (429). Wait and retry.") from e
        raise


def _plan_team(authors, entry, trusted):
    """Pick which fetched author represents the entry's team.

    Returns (author, trusted_name). trusted_name is a display name already
    recorded for this person elsewhere in the archive — reuse it instead of
    the fetched form. The last author is checked first, then the
    second-to-last (some groups record the PI one position earlier).
    """
    tail = authors[-2:] if len(authors) >= 2 else authors
    if entry.get("team"):
        wanted = normalize_name(entry["team"])
        for a in reversed(tail):
            if normalize_name(a.name) == wanted:
                return a, None
        return authors[-1], None
    for a in reversed(tail):
        name = trusted.get(normalize_name(a.name))
        if name:
            return a, name
    return authors[-1], None


def _crossref_last_author(doi: str) -> dict | None:
    """Fetch a work from Crossref and return its last author entry.

    Returns {"name": str, "affiliations": [str]} or None when the DOI is
    unknown to Crossref (e.g. DataCite-registered arXiv DOIs) or the request
    fails — a missing record is a normal outcome, not an error.
    """
    req = urllib.request.Request(
        CROSSREF_URL.format(doi=doi),
        headers={"User-Agent": "awescholar-backfill (https://github.com/Webioinfo01/awescholar)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=CROSSREF_TIMEOUT_SECONDS) as resp:
            authors = json.load(resp)["message"].get("author") or []
    except Exception:  # noqa: BLE001 — unknown DOIs and transient failures are normal outcomes
        return None
    if not authors:
        return None
    last = authors[-1]
    name = " ".join(x for x in (last.get("given"), last.get("family")) if x)
    return {
        "name": name.strip(),
        "affiliations": [a.get("name") for a in last.get("affiliation", []) if a.get("name")],
    }


def backfill_affiliations(archive_path: str, api_key: str | None = None,
                          no_backup: bool = False, status_cb=print) -> dict:
    """Fill empty affiliation/team fields in an archive JSON from Semantic Scholar.

    Only entries with a DOI and an empty affiliation are fetched. Empty team
    fields are filled from the same response. Returns a stats dict.
    """
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    # Names already trusted in this archive: normalized name -> display form.
    trusted: dict[str, str] = {}
    candidates = []  # (category, index, entry)
    for category, papers in archive.items():
        for i, p in enumerate(papers):
            if p.get("team"):
                trusted.setdefault(normalize_name(p["team"]), p["team"])
            if not p.get("affiliation") and p.get("doi"):
                candidates.append((category, i, p))

    status_cb(f"Entries missing affiliation with a DOI: {len(candidates)}")
    if not candidates:
        return {"candidates": 0, "filled_affiliations": 0, "filled_teams": 0,
                "reused_trusted": 0, "papers_missing": 0, "authors_missing": 0}

    sch = SemanticScholar(api_key=api_key) if api_key else SemanticScholar()

    fetched = {}  # doi -> Paper
    doi_list = [f"DOI:{p['doi']}" for _, _, p in candidates]
    for n, chunk in enumerate(_chunk(doi_list, PAPERS_PER_BATCH)):
        if n:
            time.sleep(BATCH_PAUSE_SECONDS)
        # externalIds must be requested: the batch endpoint returns only the
        # requested fields, and without it there is no DOI to map results back
        for paper in _call_sch(sch.get_papers, chunk, fields=["authors", "externalIds"]):
            doi = paper.externalIds.get("DOI") if paper.externalIds else None
            if doi:
                fetched[doi] = paper

    # Resolve who the team is for each entry, then batch-fetch those authors.
    plans = []  # (category, index, entry, authorId, list_name, trusted_name)
    papers_missing = 0
    for category, i, entry in candidates:
        paper = fetched.get(entry["doi"])
        if not paper or not paper.authors:
            papers_missing += 1
            continue
        author, trusted_name = _plan_team(paper.authors, entry, trusted)
        if author and author.authorId:
            plans.append((category, i, entry, author.authorId, author.name, trusted_name))

    details = {}  # authorId -> Author
    author_ids = sorted({author_id for _, _, _, author_id, _, _ in plans})
    for n, chunk in enumerate(_chunk(author_ids, AUTHORS_PER_BATCH)):
        if n:
            time.sleep(BATCH_PAUSE_SECONDS)
        # authorId is always returned by the author batch endpoint
        for author in _call_sch(sch.get_authors, chunk, fields=["name", "affiliations"]):
            details[author.authorId] = author

    filled_affiliations = filled_teams = reused_trusted = 0
    for category, i, entry, author_id, list_name, trusted_name in plans:
        author = details.get(author_id)
        if not entry.get("team"):
            name = trusted_name or (author.name if author else None) or list_name
            if name:
                entry["team"] = name
                filled_teams += 1
                if trusted_name:
                    reused_trusted += 1
        if not entry.get("affiliation"):
            affiliations = list(author.affiliations or []) if author else []
            if affiliations:
                entry["affiliation"] = format_affiliations(affiliations)
                filled_affiliations += 1

    authors_missing = len(plans) - len(details)
    status_cb(
        f"Semantic Scholar: filled {filled_affiliations} affiliations, "
        f"{filled_teams} teams ({reused_trusted} reused from existing entries); "
        f"{papers_missing} papers not found, {authors_missing} authors without data"
    )

    # Crossref fallback for whatever still lacks an affiliation — it is the
    # primary source for affiliations; SS rarely carries them.
    trusted = {}
    still_missing = []
    for papers in archive.values():
        for p in papers:
            if p.get("team"):
                trusted.setdefault(normalize_name(p["team"]), p["team"])
            if not p.get("affiliation") and p.get("doi"):
                still_missing.append(p)

    crossref_affiliations = crossref_teams = 0
    if still_missing:
        status_cb(f"Crossref: checking {len(still_missing)} remaining DOIs...")
        for k, p in enumerate(still_missing):
            if k:
                time.sleep(CROSSREF_PAUSE_SECONDS)
            author = _crossref_last_author(p["doi"])
            if not author:
                continue
            if not p.get("team") and author["name"]:
                p["team"] = trusted.get(normalize_name(author["name"]), author["name"])
                crossref_teams += 1
            if not p.get("affiliation") and author["affiliations"]:
                p["affiliation"] = format_affiliations(author["affiliations"])
                crossref_affiliations += 1
        status_cb(
            f"Crossref: filled {crossref_affiliations} affiliations, {crossref_teams} teams"
        )

    if not no_backup:
        ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{archive_path}.{ts}.bak"
        shutil.copy2(archive_path, backup_path)
        status_cb(f"Created backup: {backup_path}")

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)

    return {
        "candidates": len(candidates),
        "filled_affiliations": filled_affiliations + crossref_affiliations,
        "filled_teams": filled_teams + crossref_teams,
        "reused_trusted": reused_trusted,
        "papers_missing": papers_missing,
        "authors_missing": authors_missing,
    }
