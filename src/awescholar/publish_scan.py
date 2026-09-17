"""Scan the archive for preprints that have since been published.

The mirror of merge-time dedupe: instead of waiting for a published version
to arrive as new input and collide with the archived preprint, publish-scan
asks Semantic Scholar about every preprint already in the archive and queues
the version-of-record metadata for review. A dry run writes the review file;
``--apply`` (or ``apply_review`` directly) upgrades the entries in place —
venue, DOI, paperUrl, year, authors and citations switch to the published
version, while category, codeUrl, githubStars, domain and affiliation stay.
"""

import json
import os
import shutil
import urllib.parse
import urllib.request
from datetime import datetime
from difflib import SequenceMatcher

from .archive import is_preprint
from .data_fields import merge_preserving_nonempty, normalize_title
from .record import _get_client, _paper_to_record, search_by_doi
from .utils import matches_only

DEFAULT_REVIEW_FILENAME = "publish_review.json"
CROSSREF_SEARCH_URL = "https://api.crossref.org/works"
CROSSREF_UA = "awescholar-publish-scan (https://github.com/wehuman01/awescholar)"
CROSSREF_TIMEOUT_SECONDS = 20

# Same thresholds the merge-time dedupe uses: a near-identical title alone is
# suspicious, a slightly looser title needs a shared author token.
_TITLE_SIMILARITY_THRESHOLD = 0.90
_TITLE_SIMILARITY_WITH_TEAM_THRESHOLD = 0.80

_TITLE_FIELDS = ["paperId", "title", "venue", "year", "publicationDate",
                 "authors", "externalIds", "url", "journal", "citationCount", "abstract"]


def _load_archive_json(archive_path: str) -> dict:
    with open(archive_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_preprints(archive: dict, only: list[str] | None = None) -> list[dict]:
    """Every archive entry that looks like a preprint, as review references.

    Returns [{"category", "index", "paper"}] in archive order. ``only`` scopes
    by DOI or title substring, same as updater enrich/backfill.
    """
    found = []
    for category, papers in archive.items():
        for i, paper in enumerate(papers):
            if is_preprint(paper) and matches_only(paper, only or []):
                found.append({"category": category, "index": i, "paper": paper})
    return found


def _author_tokens(record: dict) -> set[str]:
    names = record.get("authors") or []
    if not names and record.get("team"):
        names = [record["team"]]
    return {n.split()[-1].casefold() for n in names if n and n.split()}


def _title_match_ok(preprint: dict, record: dict) -> tuple[bool, float]:
    """Conservative gate for the title-search path: the found record must be
    a near-duplicate of the preprint title (dedupe thresholds) — DOI lookups
    skip this because the identifier itself pins the paper."""
    a = normalize_title(preprint.get("title"))
    b = normalize_title(record.get("title"))
    if not a or not b:
        return False, 0.0
    sim = SequenceMatcher(None, a, b).ratio()
    if sim >= _TITLE_SIMILARITY_THRESHOLD:
        return True, sim
    if sim >= _TITLE_SIMILARITY_WITH_TEAM_THRESHOLD and \
            _author_tokens(preprint) & _author_tokens(record):
        return True, sim
    return False, sim


def _title_candidates(title: str, sch) -> list[dict]:
    """S2 title-search candidates as records, best first.

    Exact-match search misses published twins whose title drifted
    ("AlphaFold3" vs "AlphaFold 3"), which is the norm between preprint and
    version of record — so fetch several candidates and let the similarity
    gate in _title_match_ok decide.
    """
    if not title.strip():
        return []
    try:
        results = sch.search_paper(title, limit=5, fields=_TITLE_FIELDS)
        return [_paper_to_record(p) for p in results if p]
    except Exception as e:  # noqa: BLE001 — one failed lookup must not abort the batch
        print(f"  Error: {e}")
        return []


def _crossref_candidates(title: str) -> list[dict]:
    """Crossref title-search candidates as records, best first.

    S2's relevance search sometimes fails to surface the published twin at
    all (it keyword-matches citers of the paper); Crossref ``query.title``
    ranks exact-title matches up top, which is what version-of-record lookup
    needs.
    """
    if not title.strip():
        return []
    params = urllib.parse.urlencode({
        "query.title": title, "rows": 5,
        "select": "DOI,title,container-title,issued,author,is-referenced-by-count",
    })
    req = urllib.request.Request(
        f"{CROSSREF_SEARCH_URL}?{params}", headers={"User-Agent": CROSSREF_UA})
    try:
        with urllib.request.urlopen(req, timeout=CROSSREF_TIMEOUT_SECONDS) as resp:
            items = json.load(resp)["message"].get("items", [])
    except Exception as e:  # noqa: BLE001 — one failed lookup must not abort the batch
        print(f"  Error: crossref: {e}")
        return []

    records = []
    for it in items:
        titles = it.get("title") or []
        doi = it.get("DOI") or ""
        if not titles or not doi:
            continue
        authors = [f"{a.get('given', '').strip()} {a.get('family', '').strip()}".strip()
                   for a in it.get("author") or [] if (a.get("given") or a.get("family"))]
        parts = (it.get("issued") or {}).get("date-parts") or [[]]
        year = parts[0][0] if parts and parts[0] else ""
        month = parts[0][1] if parts and len(parts[0]) > 1 else None
        containers = it.get("container-title") or []
        records.append({
            "year": f"{year}.{month:02d}" if year and month else (str(year) if year else ""),
            "title": titles[0],
            "team": authors[-1] if authors else "",
            "authors": authors,
            "venue": containers[0] if containers else "",
            "paperUrl": f"https://doi.org/{doi}",
            "doi": doi,
            "citations": it.get("is-referenced-by-count", 0),
        })
    return records


def scan_archive(archive_path: str, api_key: str | None = None,
                 only: list[str] | None = None, limit: int | None = None,
                 use_title_search: bool = True, status_cb=print) -> list[dict]:
    """Verify every archived preprint against Semantic Scholar.

    For each preprint: look it up by DOI (preprints without a DOI go straight
    to title search). A record that is itself no longer a preprint is the
    published version. Falls back to title search for DOI misses, gated by
    dedupe-style title similarity. Returns the review items; nothing is
    written to the archive.
    """
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    preprints = find_preprints(archive, only=only)
    if limit is not None:
        preprints = preprints[:limit]
    status_cb(f"Scanning {len(preprints)} preprint(s) against Semantic Scholar")

    sch = _get_client(api_key)
    review = []
    for pos, item in enumerate(preprints, 1):
        paper = item["paper"]
        title = str(paper.get("title") or "")[:60]
        record = None
        evidence = {"match": "none"}

        doi = paper.get("doi")
        if doi:
            record = search_by_doi(doi, sch)
            if record and not is_preprint(record):
                evidence = {"match": "doi"}
            elif record and is_preprint(record):
                # S2 returned the preprint itself — still unpublished (or S2
                # keeps both versions separate; title search may find the twin).
                record = None
        if record is None and use_title_search:
            # Title-matched identity is inferred, so demand a venue: the
            # version of record carries a journal name, repost copies
            # (ResearchHub etc.) and registry entries do not.
            for candidate in _title_candidates(paper.get("title") or "", sch):
                if is_preprint(candidate) or not str(candidate.get("venue") or "").strip():
                    continue
                ok, sim = _title_match_ok(paper, candidate)
                if ok:
                    record = candidate
                    evidence = {"match": "title", "title_similarity": round(sim, 3)}
                    break
        if record is None and use_title_search:
            for candidate in _crossref_candidates(paper.get("title") or ""):
                if is_preprint(candidate) or not str(candidate.get("venue") or "").strip() \
                        or candidate.get("doi", "").casefold() == str(doi or "").casefold():
                    continue
                ok, sim = _title_match_ok(paper, candidate)
                if ok:
                    record = candidate
                    evidence = {"match": "crossref-title", "title_similarity": round(sim, 3)}
                    break

        if record is not None:
            record.pop("abstract", None)
            review.append({
                "category": item["category"],
                "index": item["index"],
                "existing": paper,
                "published": record,
                "evidence": evidence,
            })
            status_cb(f"  [{pos}/{len(preprints)}] {evidence['match']}: {title} "
                      f"-> {record.get('venue') or record.get('doi')}")
        else:
            status_cb(f"  [{pos}/{len(preprints)}] still preprint: {title}")

    return review


def write_review(review: list[dict], review_path: str) -> None:
    with open(review_path, "w", encoding="utf-8") as f:
        json.dump(review, f, indent=2, ensure_ascii=False)


def apply_review(review_path: str, archive_path: str,
                 no_backup: bool = False) -> list[dict]:
    """Upgrade the archive per a publish review file.

    The published record's non-empty fields overwrite the preprint entry in
    place; the category never moves; codeUrl/githubStars/domain/affiliation
    survive because the published record does not carry them. The review file
    is removed once applied. Returns per-item resolutions.
    """
    with open(review_path, "r", encoding="utf-8") as f:
        review = json.load(f)
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    applied = []
    for item in review:
        cat, i = item.get("category"), item.get("index")
        published = item.get("published") or {}
        if cat not in archive or not isinstance(i, int) or not 0 <= i < len(archive.get(cat, [])):
            applied.append({**item, "resolution": "skipped (archive entry no longer there)"})
            continue

        archive[cat][i] = merge_preserving_nonempty(archive[cat][i], published)
        applied.append({**item, "resolution": "upgraded to published version"})

    if not no_backup:
        ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{archive_path}.{ts}.bak"
        shutil.copy2(archive_path, backup_path)
        print(f"Created backup: {backup_path}")

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)
    os.remove(review_path)
    return applied


def queue_pair(archive_path: str, preprint_doi: str, published_doi: str,
               api_key: str | None = None, review_path: str | None = None,
               status_cb=print) -> list[dict]:
    """Queue a manual preprint→published upgrade for a retitled twin.

    Retitled twins defeat every automatic channel — no shared DOI link, no
    title similarity. ``--pair`` is the human override: point it at both
    DOIs, it locates the preprint in the archive, fetches the published
    record from Semantic Scholar, and writes the same review item shape the
    scan produces, so ``--review <file> --apply`` upgrades it unchanged.
    """
    from .record import _get_client, _paper_to_record

    archive = _load_archive_json(archive_path)
    needle = preprint_doi.strip().lower()
    location = None
    for category, papers in archive.items():
        for i, p in enumerate(papers):
            if str(p.get("doi") or "").casefold() == needle:
                location = (category, i, p)
                break
        if location:
            break
    if location is None:
        raise ValueError(f"preprint DOI {preprint_doi!r} not found in {archive_path}")

    sch = _get_client(api_key)
    paper = sch.get_paper(
        f"DOI:{published_doi}",
        fields=["paperId", "title", "venue", "year", "publicationDate",
                "authors", "externalIds", "url", "journal", "citationCount"],
    )
    record = _paper_to_record(paper)
    if not record or not record.get("title"):
        raise ValueError(f"published DOI {published_doi!r} not found on Semantic Scholar")
    record.pop("abstract", None)

    category, index, existing = location
    review = [{
        "category": category,
        "index": index,
        "existing": existing,
        "published": record,
        "evidence": {"match": "manual-pair", "preprint_doi": preprint_doi,
                     "published_doi": published_doi},
    }]
    path = review_path or os.path.join(
        os.path.dirname(archive_path) or ".", DEFAULT_REVIEW_FILENAME)
    write_review(review, path)
    status_cb(f"Queued manual pair: {existing.get('title')}\n"
              f"  -> {record.get('title')} ({record.get('venue') or published_doi})")
    status_cb(f"Apply : awescholar updater publish-scan --archive {archive_path} "
              f"--review {path} --apply")
    return review


def publish_scan(archive_path: str, api_key: str | None = None, *,
                 apply: bool = False, review_path: str | None = None,
                 only: list[str] | None = None, limit: int | None = None,
                 use_title_search: bool = True, no_backup: bool = False,
                 status_cb=print) -> dict:
    """Orchestrate scan → review file → optional apply.

    Default is a dry run that writes ``publish_review.json`` next to the
    archive. ``apply=True`` applies the review in the same invocation.
    Returns a stats dict.
    """
    path = review_path or os.path.join(
        os.path.dirname(archive_path) or ".", DEFAULT_REVIEW_FILENAME)
    review = scan_archive(archive_path, api_key=api_key, only=only, limit=limit,
                          use_title_search=use_title_search, status_cb=status_cb)
    write_review(review, path)

    applied = []
    if apply and review:
        applied = apply_review(path, archive_path, no_backup=no_backup)
        upgraded = sum(1 for a in applied if a["resolution"].startswith("upgraded"))
        status_cb(f"\nUpgraded {upgraded} preprint(s) to published versions in {archive_path}")
    elif review:
        status_cb(f"\n{len(review)} upgrade(s) queued in {path}")
        status_cb(f"Apply : awescholar updater publish-scan --archive {archive_path} "
                  f"--review {path} --apply")
    else:
        if os.path.exists(path):
            os.remove(path)
        status_cb("\nNo preprint has a published version yet — nothing queued")

    return {"scanned": len(review), "applied": applied}
