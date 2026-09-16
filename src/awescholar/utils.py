"""Utilities — re-exports from archive, readme, and rss modules, plus shared matchers.

This module exists for backwards compatibility. Import from the
sub-modules directly in new code.
"""

from .archive import DateEncoder, merge_archive_to_new, merge_new_to_archive
from .readme import (
    README_END_MARKER,
    README_START_MARKER,
    discover_readme_targets,
    update_readme,
)
from .rss import generate_rss


def matches_only(entry: dict, only: list[str]) -> bool:
    """Return True when ``only`` is empty or at least one pattern matches.

    Patterns are compared case-insensitively: a match is either exact
    equality with the entry's ``doi`` or a case-insensitive substring of
    the entry's ``title``.  Non-string or empty entry fields never match.
    """
    if not only:
        return True
    doi = entry.get("doi")
    title = entry.get("title")
    doi_lower = doi.lower() if isinstance(doi, str) and doi else None
    title_lower = title.lower() if isinstance(title, str) and title else None
    for p in only:
        p_lower = p.lower()
        if doi_lower is not None and p_lower == doi_lower:
            return True
        if title_lower is not None and p_lower in title_lower:
            return True
    return False


__all__ = [
    "README_END_MARKER",
    "README_START_MARKER",
    "DateEncoder",
    "discover_readme_targets",
    "generate_rss",
    "matches_only",
    "merge_archive_to_new",
    "merge_new_to_archive",
    "update_readme",
]
