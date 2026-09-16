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
