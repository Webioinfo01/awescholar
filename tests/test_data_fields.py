"""Tests for data_fields.py — authors list extraction and safe merging."""

from awescholar.data_fields import (
    merge_preserving_nonempty,
    normalize_project_paper_fields,
    normalize_updater_paper_fields,
)


def test_normalize_keeps_authors_list_form():
    entry = normalize_project_paper_fields({
        "title": "Paper A", "team": "Last Author",
        "authors": ["First Author", "Last Author"],
    })
    assert entry["authors"] == ["First Author", "Last Author"]


def test_normalize_extracts_authors_from_db_blob():
    blob = ('{"name": "Yutaka Saito", '
            '"affiliations": ["The University of Tokyo"], '
            '"all": ["First Author", "Yutaka Saito"]}')
    entry = normalize_updater_paper_fields({"title": "Paper A", "authors": blob})
    assert entry["team"] == "Yutaka Saito"
    assert entry["authors"] == ["First Author", "Yutaka Saito"]


def test_normalize_missing_authors_becomes_empty_list():
    entry = normalize_project_paper_fields({"title": "Paper A"})
    assert entry["authors"] == []


def test_merge_does_not_clear_authors_with_empty_list():
    merged = merge_preserving_nonempty(
        {"title": "A", "authors": ["First Author", "Last Author"]},
        {"title": "A", "authors": []},
    )
    assert merged["authors"] == ["First Author", "Last Author"]


def test_merge_replaces_authors_with_nonempty_list():
    merged = merge_preserving_nonempty(
        {"title": "A", "authors": ["Old Author"]},
        {"title": "A", "authors": ["New Author 1", "New Author 2"]},
    )
    assert merged["authors"] == ["New Author 1", "New Author 2"]
