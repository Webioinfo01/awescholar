"""Tests for transform.py — status policy, license resolution, freshness."""

from datetime import UTC, datetime, timedelta

import pytest

from awescholar.agentx import transform

# --- Fixtures ----------------------------------------------------------------

NOW = datetime(2026, 9, 17, tzinfo=UTC)


def days_ago(n: int) -> datetime:
    """n days before NOW."""
    return NOW - timedelta(seconds=n * 86_400)


# --- idleDays / freshnessStatus ----------------------------------------------


def test_splits_freshness_at_120_idle_days():
    assert transform.freshness_status(days_ago(119), NOW) == "active"
    assert transform.freshness_status(days_ago(121), NOW) == "stale"


def test_idle_days_round_trip():
    assert transform.idle_days(days_ago(10), NOW) == pytest.approx(10.0)


# --- resolveRepoStatus -------------------------------------------------------


def test_never_rederives_protected_statuses():
    for status in ("stable", "no-repo"):
        assert transform.resolve_repo_status(
            current_status=status,
            archived=True,
            stars=0,
            pushed_at=days_ago(400),
            now=NOW,
        ) == status


def test_maps_owner_archived_repos_to_gone():
    assert transform.resolve_repo_status(
        current_status="active",
        archived=True,
        stars=100,
        pushed_at=days_ago(1),
        now=NOW,
    ) == "gone"


def test_promotes_peer_reviewed_papers_to_stable_before_idle_rules():
    assert transform.resolve_repo_status(
        current_status="active",
        archived=False,
        stars=3,
        pushed_at=days_ago(400),
        paper_venue="Nature Biotechnology",
        now=NOW,
    ) == "stable"


def test_promotes_popular_preprint_backed_repos_honoring_curator_veto():
    base = {
        "current_status": "active",
        "archived": False,
        "pushed_at": days_ago(10),
        "paper_venue": "arXiv",
        "now": NOW,
    }
    assert transform.resolve_repo_status(**{**base, "stars": 1500}) == "stable"
    assert transform.resolve_repo_status(**{**base, "stars": 900}) == "active"
    assert transform.resolve_repo_status(
        **{**base, "stars": 1500, "auto_stable_exempt": True}
    ) == "active"


def test_archives_nursery_repos_past_180_idle_days_established_past_3_years():
    nursery = {
        "current_status": "active",
        "archived": False,
        "stars": 10,
        "paper_venue": "",
        "now": NOW,
    }
    assert transform.resolve_repo_status(**{**nursery, "pushed_at": days_ago(181)}) == "archived"
    assert transform.resolve_repo_status(**{**nursery, "pushed_at": days_ago(130)}) == "stale"

    established = {**nursery, "stars": 500}
    assert transform.resolve_repo_status(**{**established, "pushed_at": days_ago(365)}) == "stale"
    assert transform.resolve_repo_status(
        **{**established, "pushed_at": days_ago(3 * 365 + 1)}
    ) == "archived"


def test_keeps_current_status_when_pushed_at_is_missing():
    assert transform.resolve_repo_status(
        current_status="stale",
        archived=False,
        stars=10,
        pushed_at=None,
        now=NOW,
    ) == "stale"


# --- resolveLicenseSpdxId ----------------------------------------------------


def test_keeps_real_spdx_ids():
    assert transform.resolve_license_spdx_id("MIT", None) == "MIT"
    assert transform.resolve_license_spdx_id("Apache-2.0", "junk") == "Apache-2.0"


def test_recognises_standard_license_texts_behind_noassertion():
    mit = "MIT License\n\nPermission is hereby granted, free of charge."
    assert transform.resolve_license_spdx_id("NOASSERTION", mit) == "MIT"
    assert (
        transform.resolve_license_spdx_id(
            "NOASSERTION",
            "Creative Commons Attribution 4.0 International Public License",
        )
        == "CC-BY-4.0"
    )
    assert transform.resolve_license_spdx_id("NOASSERTION", None) is None


# --- resolveRetirement -------------------------------------------------------


def test_clears_metadata_when_a_record_returns_to_a_live_status():
    assert transform.resolve_retirement(
        current_status="archived",
        next_status="active",
        archived=False,
        stars=12,
        retired_reason="idle",
        retired_stars=12,
    ) == transform.Retirement(retired_reason=None, retired_stars=None)


def test_freezes_reason_and_stars_at_first_retirement():
    assert transform.resolve_retirement(
        current_status="active",
        next_status="archived",
        archived=True,
        stars=42,
    ) == transform.Retirement(retired_reason="owner-archived", retired_stars=42)
    assert transform.resolve_retirement(
        current_status="active",
        next_status="gone",
        archived=False,
        not_found=True,
        stars=42,
    ) == transform.Retirement(retired_reason="not-found", retired_stars=42)


def test_keeps_frozen_values_on_repeat_visits():
    assert transform.resolve_retirement(
        current_status="archived",
        next_status="archived",
        archived=True,
        stars=50,
        retired_reason="idle",
        retired_stars=44,
    ) == transform.Retirement(retired_reason="idle", retired_stars=44)
