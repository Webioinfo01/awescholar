# Pure lifecycle-policy helpers for the refresh and add commands.
# Kept free of side effects so they can be unit-tested directly.

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal, NamedTuple

from awescholar.agentx.papers import venue_tier
from awescholar.agentx.policy import (
    AUTO_STABLE_MIN_STARS,
    ESTABLISHED_ARCHIVE_IDLE_DAYS,
    NURSERY_ARCHIVE_IDLE_DAYS,
    NURSERY_MAX_STARS,
)

# --- Types -------------------------------------------------------------------

RetiredReason = Literal["idle", "owner-archived", "not-found"]
"""Freeze reason recorded at first retirement; cleared when a record returns
to a live status."""


class Retirement(NamedTuple):
    """Frozen retirement explanation and the star count at time of retirement."""
    retired_reason: RetiredReason | None
    retired_stars: int | None


# --- Helpers ------------------------------------------------------------------

def normalize_homepage(homepage: str | None) -> str | None:
    """Empty or whitespace-only homepages are represented consistently as None."""
    normalized = homepage.strip() if homepage else homepage
    return normalized or None


# --- License resolution -------------------------------------------------------

_CREATIVE_COMMONS_LICENSES: dict[str, str] = {
    "Attribution": "BY",
    "Attribution-ShareAlike": "BY-SA",
    "Attribution-NoDerivatives": "BY-ND",
    "Attribution-NonCommercial": "BY-NC",
    "Attribution-NonCommercial-ShareAlike": "BY-NC-SA",
    "Attribution-NonCommercial-NoDerivatives": "BY-NC-ND",
}


def resolve_license_spdx_id(
    spdx_id: str | None,
    license_text: str | None,
) -> str | None:
    """Keep GitHub's SPDX detection when present and recognise standard Creative
    Commons license titles when GitHub reports the raw file as NOASSERTION.
    """
    if spdx_id and spdx_id != "NOASSERTION":
        return spdx_id
    if not license_text:
        return None

    if re.match(
        r"^MIT License\s*\n[\s\S]*Permission is hereby granted, free of charge",
        license_text,
        re.IGNORECASE,
    ):
        return "MIT"

    if re.search(r"Creative Commons Zero v1\.0 Universal", license_text, re.IGNORECASE):
        return "CC0-1.0"

    m = re.search(
        r"Creative Commons "
        r"(Attribution(?:-(?:ShareAlike|NoDerivatives|NonCommercial)(?:-(?:ShareAlike|NoDerivatives))?)?)"
        r" (\d\.\d) "
        r"(?:International|Unported)\s+Public License",
        license_text,
        re.IGNORECASE,
    )
    if not m:
        return None

    code = _CREATIVE_COMMONS_LICENSES.get(m.group(1))
    return f"CC-{code}-{m.group(2)}" if code else None


# --- Freshness ----------------------------------------------------------------

def freshness_status(pushed_at: datetime, now: datetime | None = None) -> str:
    """Freshness from last push: stale after 120 idle days, active otherwise."""
    return "stale" if idle_days(pushed_at, now) > 120 else "active"


def idle_days(pushed_at: datetime, now: datetime | None = None) -> float:
    """How many days since the last push."""
    now = now or datetime.now(UTC)
    return (now - pushed_at).total_seconds() / 86_400


# --- Status policy ------------------------------------------------------------

# Statuses the refresh job must never rederive:
# - stable: an editorial (or auto-granted, sticky) verdict that quiet is
#   expected — see qualifies_auto_stable for the automatic path
# - no-repo: nothing to track
# Everything else — including archived and gone — is derived from live
# inputs each refresh, so recovery never needs a human edit.
_PROTECTED_STATUSES: frozenset[str] = frozenset({"stable", "no-repo"})


def qualifies_auto_stable(stars: int, paper_venue: str) -> bool:
    """The automatic stable promotion: a peer-reviewed companion paper (journal
    or conference venue, any star count) or a popular preprint-backed repo
    (stars above AUTO_STABLE_MIN_STARS).  Records flagged autoStableExempt
    never take this path — a curator's veto the pipeline cannot outvote.
    """
    tier = venue_tier(paper_venue)
    if tier in ("journal", "conference"):
        return True
    return tier == "preprint" and stars > AUTO_STABLE_MIN_STARS


def archive_idle_limit(stars: int) -> int:
    """Idle limit before a repo is considered abandoned, by star tier."""
    return (
        NURSERY_ARCHIVE_IDLE_DAYS
        if stars < NURSERY_MAX_STARS
        else ESTABLISHED_ARCHIVE_IDLE_DAYS
    )


def resolve_repo_status(
    *,
    current_status: str,
    archived: bool,
    stars: int,
    pushed_at: datetime | None,
    paper_venue: str = "",
    auto_stable_exempt: bool = False,
    now: datetime | None = None,
) -> str:
    """Unified refresh status policy shared by the snapshot command.  In order:

    - Protected statuses are kept as-is: a stable verdict survives anything,
      no-repo has nothing to rederive.
    - A repo archived by its owner is gone: the code may still be readable
      but it is frozen for good.  Un-archiving the repo lifts this on the
      next refresh.
    - The auto-stable paper rule promotes qualifying repos (unless exempt).
      It runs before the idle rules, so a peer-reviewed project that went
      quiet reads as stable, not archived.
    - A repo idle past its tier's limit (180 days under the nursery star
      line, 3 years above) is archived — reversible by any fresh push.
    - Everything else is freshness from pushedAt: active within 120 days,
      stale beyond.  Missing pushedAt keeps the current status.

    Repos that vanish entirely (404) bypass this policy in the refresh
    command and are written to "gone" directly.
    """
    if current_status in _PROTECTED_STATUSES:
        return current_status
    if archived:
        return "gone"
    if not auto_stable_exempt and qualifies_auto_stable(stars, paper_venue):
        return "stable"
    if pushed_at is None:
        return current_status
    if idle_days(pushed_at, now) > archive_idle_limit(stars):
        return "archived"
    return freshness_status(pushed_at, now)


# --- Retirement ---------------------------------------------------------------

def resolve_retirement(
    *,
    current_status: str,
    next_status: str,
    archived: bool,
    not_found: bool = False,
    stars: int,
    retired_reason: RetiredReason | None = None,
    retired_stars: int | None = None,
) -> Retirement:
    """Freeze the explanation and star count at the first retirement.

    A live status clears both values so a recovered project leaves no stale
    memorial.
    """
    if next_status not in ("archived", "gone"):
        return Retirement(retired_reason=None, retired_stars=None)

    previous_reason: RetiredReason | None = (
        retired_reason if retired_reason in ("idle", "owner-archived", "not-found") else None
    )
    if current_status == next_status and previous_reason is not None and retired_stars is not None:
        return Retirement(retired_reason=previous_reason, retired_stars=retired_stars)

    return Retirement(
        retired_reason="not-found" if not_found else ("owner-archived" if archived else "idle"),
        retired_stars=stars,
    )
