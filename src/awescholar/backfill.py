"""Backfill missing affiliation/team fields in an archive from Semantic Scholar.

Fetches each DOI-paper's authors in batch, resolves which author represents
the entry's team (last author by convention, or the author the archive
already recorded), and fills only empty fields — existing values are never
overwritten, and entries never move between categories.
"""

import json
import shutil
import time
from datetime import datetime

from semanticscholar import SemanticScholar

from .data_fields import format_affiliations, normalize_name

PAPERS_PER_BATCH = 500
AUTHORS_PER_BATCH = 1000
BATCH_PAUSE_SECONDS = 1.0
EMPTY_BATCH_RETRIES = 3
RETRY_PAUSE_SECONDS = 5.0


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _fetch_batch(fn, chunk, fields):
    """Call a batch endpoint, retrying all-empty responses.

    Semantic Scholar occasionally returns HTTP 200 with every ID null; a
    fully-empty batch of real IDs is an anomaly worth retrying, not a result.
    """
    for attempt in range(EMPTY_BATCH_RETRIES):
        results = _call_sch(fn, chunk, fields=fields)
        if results:
            return list(results)
        if attempt < EMPTY_BATCH_RETRIES - 1:
            time.sleep(RETRY_PAUSE_SECONDS * (attempt + 1))
    return []


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
        for paper in _fetch_batch(sch.get_papers, chunk, ["authors"]):
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
        for author in _fetch_batch(sch.get_authors, chunk, ["name", "affiliations"]):
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
        f"Filled {filled_affiliations} affiliations, {filled_teams} teams "
        f"({reused_trusted} reused from existing archive entries); "
        f"{papers_missing} papers not found, {authors_missing} authors without data"
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
        "filled_affiliations": filled_affiliations,
        "filled_teams": filled_teams,
        "reused_trusted": reused_trusted,
        "papers_missing": papers_missing,
        "authors_missing": authors_missing,
    }
