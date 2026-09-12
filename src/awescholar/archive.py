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
        [category, i, normalize_title(p.get("title")), _team_tokens(p.get("team"))]
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
                cat, i, _existing_title, existing_team = fuzzy
                held_back.append({
                    "incoming": entry,
                    "existing": {"category": cat, "index": i, "paper": archive[cat][i]},
                    "title_similarity": round(
                        SequenceMatcher(None, title, normalize_title(
                            archive[cat][i].get("title"))).ratio(), 3),
                    "shared_team": bool(_team_tokens(entry.get("team")) & existing_team),
                })
                continue

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


def _is_preprint(paper: dict) -> bool:
    doi = str(paper.get("doi") or "").casefold()
    venue = str(paper.get("venue") or "").casefold()
    return "arxiv" in doi or "arxiv" in venue or (not doi and not venue)


def _wins_incoming(incoming: dict, existing: dict, keep: str) -> bool:
    """Decide whether the incoming entry replaces the existing one."""
    if keep == "newer":
        return str(incoming.get("year") or "")[:10] > str(existing.get("year") or "")[:10]
    if keep == "published":
        return (not _is_preprint(incoming)) - (not _is_preprint(existing)) > 0
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
