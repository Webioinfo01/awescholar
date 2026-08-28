"""Archive merge operations for project data JSON."""

import json
import os
from datetime import date, datetime

from .categories import canonicalize_category
from .data_fields import merge_preserving_nonempty, normalize_project_paper_fields, normalize_title


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


def merge_new_to_archive(new_path: str, archive_path: str) -> dict:
    """Merge new filtered data into cumulative archive JSON.

    Deduplicates globally by DOI, falling back to normalized-title match for
    papers without a DOI (which also backfills the DOI onto the archive entry).
    Existing papers are updated in place — their category never moves.
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

    for category, papers in new_data.items():
        target_category = canonicalize_category(category, archive.keys())
        if target_category not in archive:
            archive[target_category] = []

        for paper in papers:
            entry = normalize_project_paper_fields(paper)

            doi = entry.get("doi")
            hit = _find_existing(doi, normalize_title(entry.get("title")), doi_index, title_index)
            if hit is not None:
                cat, i = hit
                archive[cat][i] = merge_preserving_nonempty(archive[cat][i], entry)
                continue

            archive[target_category].append(entry)
            pos = [target_category, len(archive[target_category]) - 1]
            if doi:
                doi_index[doi] = pos
            title = normalize_title(entry.get("title"))
            if title:
                title_index[title] = pos

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)

    return archive


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
