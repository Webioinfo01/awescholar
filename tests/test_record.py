"""Tests for record.py — search_and_add json-file mode, flat JSON helpers."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from awescholar.record import (
    _is_duplicate,
    _load_flat_json,
    _save_flat_json,
    search_and_add,
)

# ── _load_flat_json / _save_flat_json ──────────────────────────

def test_load_flat_json_returns_empty_list_for_missing():
    result = _load_flat_json("/nonexistent/path.json")
    assert result == []


def test_save_and_load_flat_json_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "papers.json")
        papers = [{"title": "A", "doi": "10.1/a"}, {"title": "B", "doi": "10.1/b"}]

        _save_flat_json(path, papers)
        loaded = _load_flat_json(path)

        assert len(loaded) == 2
        assert loaded[0]["title"] == "A"
        assert loaded[1]["doi"] == "10.1/b"


def test_load_flat_json_flattens_dict_format():
    """If file is a categorized dict, flatten to list."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "papers.json")
        data = {"cat1": [{"title": "A"}], "cat2": [{"title": "B"}]}
        with open(path, "w") as f:
            json.dump(data, f)

        result = _load_flat_json(path)

        assert len(result) == 2
        titles = {p["title"] for p in result}
        assert titles == {"A", "B"}


# ── _is_duplicate ──────────────────────────────────────────────

@pytest.mark.parametrize(
    ("existing", "new", "expected"),
    [
        ([{"title": "Paper A", "doi": "10.1/a"}], {"title": "Paper A", "doi": "10.1/other"}, True),
        ([{"title": "Different Title", "doi": "10.1/a"}], {"title": "Paper A", "doi": "10.1/a"}, True),
        ([{"title": "Paper A", "doi": "10.1/a"}], {"title": "Paper B", "doi": "10.1/b"}, False),
    ],
)
def test_is_duplicate(existing, new, expected):
    assert _is_duplicate(existing, new) is expected


# ── search_and_add with json_file ──────────────────────────────

def _mock_paper(title="Test Paper", doi="10.1/test"):
    """Create a mock SemanticScholar paper object."""
    paper = MagicMock()
    paper.title = title
    paper.authors = [MagicMock(name="Author")]
    paper.authors[-1].name = "Last Author"
    paper.publicationDate = "2025-03-15"
    paper.venue = "TestVenue"
    paper.paperId = "abc123"
    paper.externalIds = {"DOI": doi}
    paper.url = "https://example.com/paper"
    paper.journal = None
    paper.year = 2025
    return paper


@patch("builtins.input", side_effect=["My Paper Title", ""])
@patch("awescholar.record.SemanticScholar")
def test_search_and_add_json_file_creates_flat_list(MockSS, mock_input):
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.search_paper.return_value = _mock_paper(title="My Paper Title", doi="10.1/mp")

    with tempfile.TemporaryDirectory() as tmp:
        json_file = os.path.join(tmp, "papers.json")

        search_and_add(json_file=json_file, by="title")

        assert os.path.exists(json_file)
        with open(json_file) as f:
            papers = json.load(f)
        assert isinstance(papers, list)
        assert len(papers) == 1
        assert papers[0]["title"] == "My Paper Title"
        assert papers[0]["doi"] == "10.1/mp"


@patch("builtins.input", side_effect=["Duplicate Paper", ""])
@patch("awescholar.record.SemanticScholar")
def test_search_and_add_json_file_dedup(MockSS, mock_input):
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.search_paper.return_value = _mock_paper(title="Duplicate Paper", doi="10.1/dup")

    with tempfile.TemporaryDirectory() as tmp:
        json_file = os.path.join(tmp, "papers.json")
        # Pre-populate with existing paper
        _save_flat_json(json_file, [{"title": "Duplicate Paper", "doi": "10.1/dup"}])

        search_and_add(json_file=json_file, by="title")

        with open(json_file) as f:
            papers = json.load(f)
        # Should still be 1 paper (deduped)
        assert len(papers) == 1


@patch("builtins.input", side_effect=["Paper A", "Paper B", ""])
@patch("awescholar.record.SemanticScholar")
def test_search_and_add_json_file_appends_multiple(MockSS, mock_input):
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.search_paper.side_effect = [
        _mock_paper(title="Paper A", doi="10.1/a"),
        _mock_paper(title="Paper B", doi="10.1/b"),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        json_file = os.path.join(tmp, "papers.json")

        search_and_add(json_file=json_file, by="title")

        with open(json_file) as f:
            papers = json.load(f)
        assert len(papers) == 2
        assert papers[0]["title"] == "Paper A"
        assert papers[1]["title"] == "Paper B"


@patch("builtins.input", side_effect=[""])
@patch("awescholar.record.SemanticScholar")
def test_search_and_add_json_file_empty_input(MockSS, mock_input):
    """No queries entered — file should not be created."""
    with tempfile.TemporaryDirectory() as tmp:
        json_file = os.path.join(tmp, "papers.json")

        search_and_add(json_file=json_file, by="title")

        assert not os.path.exists(json_file)
