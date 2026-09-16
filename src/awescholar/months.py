"""Month helpers — derive search dates and output paths from a YYYY-MM value."""

import calendar
import re

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def parse_month(value: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' into (year, month); raises ValueError with usage guidance."""
    match = _MONTH_RE.match(value.strip())
    if not match:
        raise ValueError(f"invalid month '{value}' — expected YYYY-MM, e.g. 2026-05")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"invalid month '{value}' — month must be 01-12")
    return year, month


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
