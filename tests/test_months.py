"""Tests for month parsing and derivation."""

import pytest

from awescholar.months import month_date_range, month_report_dir, month_short, parse_month


def test_parse_month_accepts_yyyy_mm():
    assert parse_month("2026-05") == (2026, 5)


def test_parse_month_rejects_non_month_input():
    for bad in ("2026-13", "2026-5", "202605", "2026/05", "", "2026-00"):
        with pytest.raises(ValueError, match="invalid month"):
            parse_month(bad)


def test_month_date_range_covers_first_to_last_day():
    assert month_date_range(2026, 5) == "2026-05-01:2026-05-31"


def test_month_date_range_handles_leap_years():
    assert month_date_range(2028, 2) == "2028-02-01:2028-02-29"
    assert month_date_range(2026, 2) == "2026-02-01:2026-02-28"


def test_month_report_dir_uses_yymm_label():
    assert month_report_dir(2026, 5) == "month_reports/2605"
    assert month_short(2026, 12) == "2612"


# ── half-month periods ─────────────────────────────────────────

from awescholar.months import parse_period, period_date_range, period_report_dir


def test_parse_period_accepts_yyyy_mm_p():
    assert parse_period("2026-06-1") == (2026, 6, 1)
    assert parse_period("2026-06-2") == (2026, 6, 2)


def test_parse_period_rejects_bad_input():
    for bad in ("2026-06", "2026-06-3", "2026-06-0", "2026-13-1", "2606-1", ""):
        with pytest.raises(ValueError, match="invalid period"):
            parse_period(bad)


def test_period_date_range_first_half():
    assert period_date_range(2026, 6, 1) == "2026-06-01:2026-06-15"


def test_period_date_range_second_half_covers_month_end():
    assert period_date_range(2026, 6, 2) == "2026-06-16:2026-06-30"
    assert period_date_range(2026, 2, 2) == "2026-02-16:2026-02-28"
    assert period_date_range(2028, 2, 2) == "2028-02-16:2028-02-29"


def test_period_report_dir_appends_half_suffix():
    assert period_report_dir(2026, 6, 1) == "month_reports/2606_1"
    assert period_report_dir(2026, 9, 2) == "month_reports/2609_2"
