"""Utilities — re-exports from archive, readme, and rss modules, plus shared matchers.

This module exists for backwards compatibility. Import from the
sub-modules directly in new code.
"""

import logging
import time
from collections.abc import Callable

from .archive import DateEncoder, merge_archive_to_new, merge_new_to_archive
from .readme import (
    README_END_MARKER,
    README_START_MARKER,
    discover_readme_targets,
    update_readme,
)
from .rss import generate_rss

_log = logging.getLogger(__name__)

# Retryable network exception classes. Anything else (auth failures, bad
# requests, programmer errors) should propagate immediately so the caller
# learns the truth on the first attempt.
_RETRYABLE_IMPORTS = (
    ("httpx", ("ReadTimeout", "ConnectError", "RemoteProtocolError", "WriteTimeout", "PoolTimeout")),
    ("urllib3", ("MaxRetryError",)),
    ("requests", ("ConnectionError", "ReadTimeout")),
)
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = tuple(
    cls for mod, names in _RETRYABLE_IMPORTS
    if (m := __import__(mod, fromlist=["__name__"])) is not None
    for name in names if hasattr(m, name) and isinstance(getattr(m, name), type)
    for cls in [getattr(m, name)]
)


def retry_with_backoff(
    fn: Callable,
    *args,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    on_retry: Callable[[int, BaseException], None] | None = None,
    **kwargs,
):
    """Call ``fn(*args, **kwargs)`` with exponential backoff on transient failures.

    Retries on connection-level errors (httpx/urllib3/requests timeouts and
    resets). Lets authentication errors, bad-request responses, and
    programmer errors propagate on the first attempt. ``on_retry`` receives
    the attempt index (1-based) and the exception for logging.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except _RETRYABLE_EXCEPTIONS as e:
            last_exc = e
            if attempt == max_attempts:
                break
            if on_retry:
                on_retry(attempt, e)
            else:
                _log.warning(
                    "transient failure on attempt %d/%d (%s: %s); retrying",
                    attempt, max_attempts, type(e).__name__, e,
                )
            time.sleep(base_delay * (2 ** (attempt - 1)))
    assert last_exc is not None
    raise last_exc


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


def since_filter(entry: dict, since: str | None) -> bool:
    """Return True when ``entry.addedAt`` is missing, empty, or >= ``since``.

    ``since`` is an ISO 8601 timestamp or date; entries without a parseable
    addedAt are kept (so legacy archive entries don't disappear from the
    filter).
    """
    if not since:
        return True
    added = entry.get("addedAt")
    if not added or not isinstance(added, str):
        return True
    # Lexical compare works for ISO 8601 (lexical == chronological for fixed width).
    return str(added)[:10] >= since[:10]


__all__ = [
    "README_END_MARKER",
    "README_START_MARKER",
    "DateEncoder",
    "discover_readme_targets",
    "generate_rss",
    "matches_only",
    "merge_archive_to_new",
    "merge_new_to_archive",
    "retry_with_backoff",
    "since_filter",
    "update_readme",
]
