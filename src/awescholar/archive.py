"""Archive merge operations for project data JSON."""

import json
import os
from datetime import date, datetime
from difflib import SequenceMatcher

from .categories import canonicalize_category
from .data_fields import (
    merge_preserving_nonempty,
    normalize_name,
    normalize_project_paper_fields,
    normalize_title,
    utc_now_iso,
)

DEFAULT_REVIEW_FILENAME = "dedupe_review.json"

# A near-identical title alone is suspicious; a slightly looser title plus a
# shared author token is the usual preprint-vs-published signature.
_TITLE_SIMILARITY_THRESHOLD = 0.90
_TITLE_SIMILARITY_WITH_TEAM_THRESHOLD = 0.80


class DateEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return super().default(o)


def _build_entry_indexes(archive: dict) -> tuple[dict, dict]:
    """Global DOI and normalized-title indexes over the whole archive.

    Values are [category, index] pointing at the first entry carrying that
    DOI/title, so dedup works across categories, not just within one.
    """
    doi_index: dict[str, list] = {}
    title_index: dict[str, list] = {}
    for category, papers in archive.items():
        for i, p in enumerate(papers):
            if p.get("doi"):
                doi_index.setdefault(p["doi"], [category, i])
            title = normalize_title(p.get("title"))
            if title:
                title_index.setdefault(title, [category, i])
    return doi_index, title_index


def _find_existing(doi: str | None, title: str, doi_index: dict, title_index: dict) -> list | None:
    """Locate an existing entry by DOI, falling back to title match."""
    if doi and doi in doi_index:
        return doi_index[doi]
    if title:
        return title_index.get(title)
    return None


def _team_tokens(team) -> set[str]:
    return {t for t in normalize_name(team).split() if len(t) > 1}


def _author_roster(paper: dict) -> set[str]:
    """Normalized full author names for roster-overlap comparison."""
    authors = paper.get("authors")
    if not isinstance(authors, list):
        return set()
    return {normalize_name(a) for a in authors if normalize_name(a)}


# A full retitle defeats every title signal, but the author roster survives:
# below-threshold titles plus a near-identical roster (≥3 names) is the
# retitled preprint/published signature.
_ROSTER_MIN_NAMES = 3
_ROSTER_OVERLAP_THRESHOLD = 0.75


def _find_roster_overlap(entry: dict, archive_entries: list) -> list | None:
    """Find an archive entry whose author roster almost fully overlaps."""
    roster = _author_roster(entry)
    if len(roster) < _ROSTER_MIN_NAMES:
        return None
    for item in archive_entries:
        existing_roster = item[4] if len(item) > 4 else set()
        if len(existing_roster) < _ROSTER_MIN_NAMES:
            continue
        overlap = len(roster & existing_roster) / min(len(roster), len(existing_roster))
        if overlap >= _ROSTER_OVERLAP_THRESHOLD:
            return item[:2]
    return None


def _find_fuzzy_duplicate(title: str, team: str, archive_entries: list) -> list | None:
    """Find a near-duplicate archive entry for a title that missed exact match.

    `archive_entries` is a flat list of [category, index, normalized_title,
    team_tokens]. Returns the best entry above threshold, else None.
    """
    if not title:
        return None
    team_tokens = _team_tokens(team)
    best = None
    best_sim = 0.0
    for entry in archive_entries:
        sim = SequenceMatcher(None, title, entry[2]).ratio()
        if sim < _TITLE_SIMILARITY_WITH_TEAM_THRESHOLD:
            continue
        if sim < _TITLE_SIMILARITY_THRESHOLD and not (team_tokens & entry[3]):
            continue
        if sim > best_sim:
            best, best_sim = entry, sim
    return best


def _find_code_collision(code_url: str, archive: dict) -> tuple[str, int, dict] | None:
    """Find an archive entry already pointing at the same code repository.

    Two different papers almost never share an official repo, so a codeUrl
    collision is the strongest preprint-vs-published signal the archive
    carries — stronger than title similarity, which title rewrites defeat.
    Returns (category, index, entry) of the first matching entry, else None.
    """
    if not code_url:
        return None
    needle = code_url.rstrip("/").lower()
    for category, papers in archive.items():
        for i, p in enumerate(papers):
            existing = str(p.get("codeUrl") or "").rstrip("/").lower()
            if existing and existing == needle:
                return category, i, p
    return None


def merge_new_to_archive(new_path: str, archive_path: str, *,
                         dedupe: bool = True, review_path: str | None = None) -> dict:
    """Merge new filtered data into cumulative archive JSON.

    Deduplicates globally by DOI, falling back to normalized-title match for
    papers without a DOI (which also backfills the DOI onto the archive entry).
    Existing papers are updated in place — their category never moves.

    With `dedupe` (default), entries whose title is a near-match of an archive
    entry but that dodge the exact match (typical preprint vs published pairs)
    are held back into a review file instead of being appended. The review file
    is rewritten on every merge so it always mirrors the latest run.
    Returns the merged archive.
    """
    with open(new_path, "r", encoding="utf-8") as f:
        new_data = json.load(f)

    if os.path.exists(archive_path):
        with open(archive_path, "r", encoding="utf-8") as f:
            archive = json.load(f)
    else:
        archive = {}

    doi_index, title_index = _build_entry_indexes(archive)
    archive_entries = [
        [category, i, normalize_title(p.get("title")), _team_tokens(p.get("team")),
         _author_roster(p)]
        for category, papers in archive.items() for i, p in enumerate(papers)
    ]
    held_back = []

    for category, papers in new_data.items():
        target_category = canonicalize_category(category, archive.keys())
        if target_category not in archive:
            archive[target_category] = []

        for paper in papers:
            entry = normalize_project_paper_fields(paper)

            doi = entry.get("doi")
            title = normalize_title(entry.get("title"))
            hit = _find_existing(doi, title, doi_index, title_index)
            if hit is not None:
                cat, i = hit
                archive[cat][i] = merge_preserving_nonempty(archive[cat][i], entry)
                continue

            fuzzy = _find_fuzzy_duplicate(title, entry.get("team"), archive_entries) \
                if dedupe else None
            if fuzzy is not None:
                cat, i, _existing_title, existing_team, _existing_roster = fuzzy
                held_back.append({
                    "incoming": entry,
                    "existing": {"category": cat, "index": i, "paper": archive[cat][i]},
                    "title_similarity": round(
                        SequenceMatcher(None, title, normalize_title(
                            archive[cat][i].get("title"))).ratio(), 3),
                    "shared_team": bool(_team_tokens(entry.get("team")) & existing_team),
                })
                continue

            # Same official repo, different title: the classic title-rewrite
            # that dodges both exact and fuzzy matching. Hold back like a
            # fuzzy duplicate so `updater dedupe --keep published` can split
            # the preprint from the journal version.
            collision = _find_code_collision(entry.get("codeUrl"), archive) \
                if dedupe else None
            if collision is not None:
                cat, i, existing_paper = collision
                held_back.append({
                    "incoming": entry,
                    "existing": {"category": cat, "index": i, "paper": existing_paper},
                    "codeUrl_collision": entry.get("codeUrl"),
                    "title_similarity": round(
                        SequenceMatcher(None, title, normalize_title(
                            existing_paper.get("title"))).ratio(), 3),
                    "shared_team": bool(_team_tokens(entry.get("team"))
                                        & _team_tokens(existing_paper.get("team"))),
                })
                continue

            # Retitled pair with a near-identical author roster: the title
            # bars are defeated by the rewrite, the roster is not.
            roster = _find_roster_overlap(entry, archive_entries) if dedupe else None
            if roster is not None:
                cat, i = roster
                existing_paper = archive[cat][i]
                held_back.append({
                    "incoming": entry,
                    "existing": {"category": cat, "index": i, "paper": existing_paper},
                    "shared_authors": round(
                        len(_author_roster(entry) & _author_roster(existing_paper))
                        / min(len(_author_roster(entry)), len(_author_roster(existing_paper))), 3),
                    "title_similarity": round(
                        SequenceMatcher(None, title, normalize_title(
                            existing_paper.get("title"))).ratio(), 3),
                    "shared_team": bool(_team_tokens(entry.get("team"))
                                        & _team_tokens(existing_paper.get("team"))),
                })
                continue

            if not entry.get("addedAt"):
                entry["addedAt"] = utc_now_iso()
            archive[target_category].append(entry)
            pos = [target_category, len(archive[target_category]) - 1]
            if doi:
                doi_index[doi] = pos
            if title:
                title_index[title] = pos
            archive_entries.append([target_category, pos[1], title, _team_tokens(entry.get("team"))])

    if dedupe:
        path = review_path or os.path.join(
            os.path.dirname(new_path) or ".", DEFAULT_REVIEW_FILENAME)
        if held_back:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(held_back, f, indent=2, ensure_ascii=False)
        elif os.path.exists(path):
            os.remove(path)

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)

    return archive


# Preprint-server DOI prefixes (arXiv, bioRxiv/medRxiv old and new, Research
# Square, Preprints.org, ChemRxiv, Authorea, SSRN) and venue name markers —
# a bioRxiv DOI never contains "arxiv", so substring matching alone missed
# every non-arXiv preprint server.
_PREPRINT_DOI_PREFIXES = (
    "10.48550/", "10.1101/", "10.64898/", "10.21203/", "10.20944/",
    "10.26434/", "10.22541/", "10.2139/",
)
_PREPRINT_VENUE_MARKERS = (
    "arxiv", "biorxiv", "medrxiv", "chemrxiv", "research square",
    "preprints.org", "preprint", "ssrn",
)


def is_preprint(paper: dict) -> bool:
    doi = str(paper.get("doi") or "").casefold()
    venue = str(paper.get("venue") or "").casefold()
    if doi.startswith(_PREPRINT_DOI_PREFIXES):
        return True
    return any(m in venue for m in _PREPRINT_VENUE_MARKERS) or (not doi and not venue)


def _wins_incoming(incoming: dict, existing: dict, keep: str) -> bool:
    """Decide whether the incoming entry replaces the existing one."""
    if keep == "newer":
        return str(incoming.get("year") or "")[:10] > str(existing.get("year") or "")[:10]
    if keep == "published":
        return (not is_preprint(incoming)) - (not is_preprint(existing)) > 0
    return False


def apply_dedupe_review(review_path: str, archive_path: str, keep: str = "newer") -> list[dict]:
    """Apply held-back duplicate pairs to the archive per the chosen strategy.

    keep=newer/published: the winner's non-empty fields overwrite the loser,
    in place (the loser is never a separate entry). keep=both: the incoming
    entry is appended to the existing entry's category. The review file is
    removed once applied. Returns per-pair resolutions.
    """
    with open(review_path, "r", encoding="utf-8") as f:
        review = json.load(f)
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    applied = []
    for item in review:
        existing_ref = item.get("existing") or {}
        cat, i = existing_ref.get("category"), existing_ref.get("index")
        incoming = item.get("incoming") or {}
        if cat not in archive or not isinstance(i, int) or not 0 <= i < len(archive.get(cat, [])):
            applied.append({**item, "resolution": "skipped (archive entry no longer there)"})
            continue

        existing = archive[cat][i]
        if keep == "both":
            archive[cat].append(incoming)
            resolution = "kept both entries"
        elif _wins_incoming(incoming, existing, keep):
            archive[cat][i] = merge_preserving_nonempty(existing, incoming)
            resolution = f"kept incoming ({keep})"
        else:
            archive[cat][i] = merge_preserving_nonempty(incoming, existing)
            resolution = f"kept existing ({keep})"
        applied.append({**item, "resolution": resolution})

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)
    os.remove(review_path)
    return applied


def merge_archive_to_new(new_path: str, archive_path: str) -> dict:
    """Enrich new data with relevant papers from the archive.

    For each category in new_data, also include papers from the archive that
    belong to the same category. Deduplicates globally by DOI with a
    normalized-title fallback, mirroring merge_new_to_archive. Archive fields
    only fill gaps — non-empty values already present in new_data are kept.
    Returns the enriched new data.
    """
    if not os.path.exists(archive_path):
        with open(new_path, "r", encoding="utf-8") as f:
            return json.load(f)

    with open(new_path, "r", encoding="utf-8") as f:
        new_data = json.load(f)
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    doi_index, title_index = _build_entry_indexes(new_data)

    for category, archive_papers in archive.items():
        target_category = canonicalize_category(category, new_data.keys())
        if target_category not in new_data:
            new_data[target_category] = []

        for paper in archive_papers:
            entry = normalize_project_paper_fields(paper)
            doi = entry.get("doi")
            hit = _find_existing(doi, normalize_title(entry.get("title")), doi_index, title_index)
            if hit is not None:
                cat, i = hit
                new_data[cat][i] = merge_preserving_nonempty(new_data[cat][i], entry)
                continue

            new_data[target_category].append(entry)
            pos = [target_category, len(new_data[target_category]) - 1]
            if doi:
                doi_index[doi] = pos
            title = normalize_title(entry.get("title"))
            if title:
                title_index[title] = pos

    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, indent=2, ensure_ascii=False)

    return new_data
