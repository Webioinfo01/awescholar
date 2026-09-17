"""Month helpers — derive search dates and output paths from a YYYY-MM value."""

import calendar
import re

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})-([12])$")


def parse_month(value: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' into (year, month); raises ValueError with usage guidance."""
    match = _MONTH_RE.match(value.strip())
    if not match:
        raise ValueError(f"invalid month '{value}' — expected YYYY-MM, e.g. 2026-05")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"invalid month '{value}' — month must be 01-12")
    return year, month


def parse_period(value: str) -> tuple[int, int, int]:
    """Parse 'YYYY-MM-P' (P=1|2) into (year, month, half); ValueError otherwise.

    Half 1 covers days 01–15, half 2 covers day 16 to month end — the
    half-month curation cadence: two runs per month, each with its own
    window, output directory, and report file.
    """
    match = _PERIOD_RE.match(value.strip())
    if not match:
        raise ValueError(f"invalid period '{value}' — expected YYYY-MM-1 or YYYY-MM-2, "
                         "e.g. 2026-06-1")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"invalid period '{value}' — month must be 01-12")
    return year, month, int(match.group(3))


def period_date_range(year: int, month: int, half: int) -> str:
    """Half-month search range: 1 → days 01–15, 2 → day 16 to month end."""
    last_day = calendar.monthrange(year, month)[1]
    start = f"{year:04d}-{month:02d}-01" if half == 1 else f"{year:04d}-{month:02d}-16"
    end_day = 15 if half == 1 else last_day
    return f"{start}:{year:04d}-{month:02d}-{end_day:02d}"


def month_date_range(year: int, month: int) -> str:
    """First-to-last-day range for search, e.g. '2026-02-01:2026-02-28'."""
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01:{year:04d}-{month:02d}-{last_day:02d}"


def month_short(year: int, month: int) -> str:
    """YYMM directory label, e.g. (2026, 5) -> '2605'."""
    return f"{year % 100:02d}{month:02d}"


def month_report_dir(year: int, month: int) -> str:
    """Output directory for a month run: 'month_reports/YYMM', relative to cwd."""
    return f"month_reports/{month_short(year, month)}"


def period_report_dir(year: int, month: int, half: int) -> str:
    """Output directory for a half-month run: 'month_reports/YYMM_P'."""
    return f"month_reports/{month_short(year, month)}_{half}"
