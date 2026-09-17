"""Tests for retry_with_backoff and since_filter — transient-failure and provenance helpers."""

import pytest

from awescholar.utils import retry_with_backoff, since_filter


class Transient(Exception):
    pass


def _flaky(fails, payload="ok", sleeper=lambda s: None):
    state = {"calls": 0}

    def fn():
        state["calls"] += 1
        if state["calls"] <= fails:
            import httpx
            raise httpx.ReadTimeout("timed out")
        return payload

    fn.calls = state
    fn.sleep = sleeper
    return fn


def test_retry_succeeds_after_transient_failures(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    fn = _flaky(2)
    assert retry_with_backoff(fn, max_attempts=3) == "ok"
    assert fn.calls["calls"] == 3


def test_retry_reraises_after_exhaustion(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    fn = _flaky(5)
    with pytest.raises(Exception):
        retry_with_backoff(fn, max_attempts=3)
    assert fn.calls["calls"] == 3


def test_retry_uses_exponential_backoff(monkeypatch):
    waits = []
    monkeypatch.setattr("time.sleep", waits.append)
    fn = _flaky(2)
    retry_with_backoff(fn, max_attempts=3, base_delay=2.0)
    assert waits == [2.0, 4.0]


# ── since_filter ───────────────────────────────────────────────

def test_since_filter_keeps_everything_when_since_absent():
    assert since_filter({"title": "x"}, None) is True
    assert since_filter({"title": "x"}, "") is True


def test_since_filter_keeps_entries_without_addedat():
    assert since_filter({"title": "x"}, "2026-09-01") is True
    assert since_filter({"addedAt": ""}, "2026-09-01") is True


def test_since_filter_compares_dates():
    assert since_filter({"addedAt": "2026-09-17T08:00:00Z"}, "2026-09-01") is True
    assert since_filter({"addedAt": "2026-08-30T08:00:00Z"}, "2026-09-01") is False
    assert since_filter({"addedAt": "2026-09-01T00:00:00Z"}, "2026-09-01") is True
