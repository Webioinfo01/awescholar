"""Tests for the monthly archive digest."""

import json

import pytest

from awescholar import digest


def _write_archive(tmp_path, archive):
    path = tmp_path / "data.json"
    path.write_text(json.dumps(archive), encoding="utf-8")
    return str(path)


def test_select_month_papers_matches_padded_and_unpadded_years():
    archive = {
        "AI Agents": [
            {"doi": "10.1/a", "title": "Padded", "year": "2026.05"},
            {"doi": "10.1/b", "title": "Unpadded", "year": "2026.5"},
            {"doi": "10.1/c", "title": "Other month", "year": "2026.04"},
            {"doi": "10.1/d", "title": "No year"},
        ],
        "Reviews": [],
    }

    selected = digest.select_month_papers(archive, 2026, 5)

    assert [p["doi"] for p in selected["AI Agents"]] == ["10.1/a", "10.1/b"]
    assert "Reviews" not in selected


def test_render_month_digest_lists_papers_with_global_index():
    month_papers = {
        "AI Agents": [
            {"doi": "10.1/a", "title": "Alpha | Beta", "year": "2026.05",
             "domain": "Agents", "venue": "Nature", "team": "MIT", "affiliation": "MIT",
             "paperUrl": "https://example.com/a"},
        ],
    }

    markdown = digest.render_month_digest(month_papers, 2026, 5, archive_total=356)

    assert markdown.startswith("# Monthly Research Digest — 2026-05")
    assert "1 paper across 1 categories (archive total: 356)." in markdown
    assert "## AI Agents" in markdown
    assert "Alpha \\| Beta" in markdown  # pipe inside a title is escaped
    assert "[Link](https://example.com/a)" in markdown


def test_run_digest_offline_without_model(tmp_path):
    archive_path = _write_archive(
        tmp_path, {"AI Agents": [{"doi": "10.1/a", "title": "Alpha", "year": "2026.05"}]}
    )

    markdown = digest.run_digest(archive_path, 2026, 5)

    assert "digest (offline)" in markdown
    assert "Alpha" in markdown


def test_run_digest_with_model_uses_digest_prompt(tmp_path, monkeypatch):
    archive_path = _write_archive(
        tmp_path, {"AI Agents": [{"doi": "10.1/a", "title": "Alpha", "year": "2026.05"}]}
    )
    captured = {}

    def fake_run_report(**kwargs):
        captured.update(kwargs)
        return "# Monthly Research Digest — 2026-05"

    monkeypatch.setattr(digest, "run_report", fake_run_report)

    markdown = digest.run_digest(
        archive_path, 2026, 5, model="openai/glm-5.3", api_key="key"
    )

    assert markdown == "# Monthly Research Digest — 2026-05"
    assert "Monthly Research Digest — 2026-05" in captured["system_prompt"]
    assert captured["date_range"] == "2026-05"
    assert [p["doi"] for p in captured["filtered_data"]["AI Agents"]] == ["10.1/a"]


def test_run_digest_raises_actionable_error_when_month_empty(tmp_path):
    archive_path = _write_archive(
        tmp_path, {"AI Agents": [{"doi": "10.1/a", "title": "Alpha", "year": "2026.04"}]}
    )

    with pytest.raises(ValueError, match="no papers with year 2026.05"):
        digest.run_digest(archive_path, 2026, 5)
