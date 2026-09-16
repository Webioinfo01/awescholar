"""Tests for record.py — search_and_add json-file mode, flat JSON helpers."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from awescholar.record import (
    _is_duplicate,
    _load_flat_json,
    _normalize_code_url,
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
        ([{"title": "paper a  with extra spaces", "doi": "10.1/x"}], {"title": "Paper A With Extra Spaces", "doi": "10.1/y"}, True),
    ],
)
def test_is_duplicate(existing, new, expected):
    assert _is_duplicate(existing, new) is expected


# ── search_and_add with json_file ──────────────────────────────

def _mock_paper(title="Test Paper", doi="10.1/test"):
    """Create a mock SemanticScholar paper object."""
    paper = MagicMock()
    paper.title = title
    first, last = MagicMock(), MagicMock()
    first.name = "First Author"
    last.name = "Last Author"
    paper.authors = [first, last]
    paper.publicationDate = "2025-03-15"
    paper.venue = "TestVenue"
    paper.paperId = "abc123"
    paper.externalIds = {"DOI": doi}
    paper.url = "https://example.com/paper"
    paper.journal = None
    paper.year = 2025
    paper.citationCount = 42
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
        assert papers[0]["team"] == "Last Author"
        assert papers[0]["authors"] == ["First Author", "Last Author"]


@patch("builtins.input", side_effect=["Cited Paper", ""])
@patch("awescholar.record.SemanticScholar")
def test_search_and_add_json_file_includes_citations(MockSS, mock_input):
    """Records carry the Semantic Scholar citationCount as `citations`."""
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.search_paper.return_value = _mock_paper(title="Cited Paper", doi="10.1/cited")

    with tempfile.TemporaryDirectory() as tmp:
        json_file = os.path.join(tmp, "papers.json")

        search_and_add(json_file=json_file, by="title")

        with open(json_file) as f:
            papers = json.load(f)
        assert papers[0]["citations"] == 42


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


# ── search_and_add with archive ────────────────────────────────

@patch("builtins.input", side_effect=["My Paper Title", ""])
@patch("awescholar.record.SemanticScholar")
def test_search_and_add_archive_with_category(MockSS, mock_input):
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.search_paper.return_value = _mock_paper(title="My Paper Title", doi="10.1/mp")

    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        with open(archive, "w") as f:
            json.dump({"AI Agents": [], "Reviews": []}, f)

        search_and_add(archive_path=archive, by="title", category="reviews")

        with open(archive) as f:
            data = json.load(f)
        assert data["AI Agents"] == []
        assert len(data["Reviews"]) == 1
        assert data["Reviews"][0]["title"] == "My Paper Title"


@patch("builtins.input", side_effect=["My Paper Title", ""])
@patch("awescholar.record.SemanticScholar")
def test_search_and_add_archive_defaults_to_first_category(MockSS, mock_input):
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.search_paper.return_value = _mock_paper(title="My Paper Title", doi="10.1/mp")

    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        with open(archive, "w") as f:
            json.dump({"AI Agents": [], "Reviews": []}, f)

        search_and_add(archive_path=archive, by="title")

        with open(archive) as f:
            data = json.load(f)
        assert len(data["AI Agents"]) == 1
        assert data["Reviews"] == []


# ── search_and_add non-interactive (queries argument) ─────────

@patch("awescholar.record.SemanticScholar")
def test_search_and_add_queries_skips_input(MockSS):
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.get_paper.return_value = _mock_paper(title="My Paper Title", doi="10.1/mp")

    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        with open(archive, "w") as f:
            json.dump({"AI Agents": [], "Reviews": []}, f)

        search_and_add(archive_path=archive, by="doi", category="AI Agents",
                       queries=["10.1/mp"])

        with open(archive) as f:
            data = json.load(f)
        assert len(data["AI Agents"]) == 1
        assert data["AI Agents"][0]["doi"] == "10.1/mp"


@patch("awescholar.record.SemanticScholar")
def test_search_and_add_queries_dedup_against_archive(MockSS):
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.get_paper.return_value = _mock_paper(title="My Paper Title", doi="10.1/mp")

    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        with open(archive, "w") as f:
            json.dump({"AI Agents": [{"title": "My Paper Title", "doi": "10.1/mp"}]}, f)

        search_and_add(archive_path=archive, by="doi", queries=["10.1/mp"])

        with open(archive) as f:
            data = json.load(f)
        assert len(data["AI Agents"]) == 1


# ── paperUrl normalization ────────────────────────────────────

@patch("awescholar.record.SemanticScholar")
def test_paper_url_prefers_doi_over_s2_url(MockSS):
    """A DOI record's paperUrl is the canonical DOI link, not the S2 page URL."""
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.search_paper.return_value = _mock_paper(title="Doi Paper", doi="10.1/doi")

    with tempfile.TemporaryDirectory() as tmp:
        json_file = os.path.join(tmp, "papers.json")
        search_and_add(json_file=json_file, by="title", queries=["Doi Paper"])
        with open(json_file) as f:
            papers = json.load(f)
        assert papers[0]["paperUrl"] == "https://doi.org/10.1/doi"


@patch("awescholar.record.SemanticScholar")
def test_paper_url_falls_back_to_s2_url_when_no_doi(MockSS):
    """Without a DOI, paperUrl falls back to the Semantic Scholar page URL."""
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    paper = _mock_paper(title="No Doi Paper", doi="")
    mock_client.search_paper.return_value = paper

    with tempfile.TemporaryDirectory() as tmp:
        json_file = os.path.join(tmp, "papers.json")
        search_and_add(json_file=json_file, by="title", queries=["No Doi Paper"])
        with open(json_file) as f:
            papers = json.load(f)
        assert papers[0]["paperUrl"] == paper.url


# ── code_url / stars_style ────────────────────────────────────

def test_normalize_code_url_shorthand():
    assert _normalize_code_url("owner/repo") == "https://github.com/owner/repo"


@patch("awescholar.record.SemanticScholar")
def test_code_url_shorthand_and_badge_stars(MockSS):
    """owner/repo shorthand becomes a full github URL; badge style writes shields URL."""
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.search_paper.return_value = _mock_paper(title="Code Paper", doi="10.1/code")

    with tempfile.TemporaryDirectory() as tmp:
        json_file = os.path.join(tmp, "papers.json")
        search_and_add(json_file=json_file, by="title", queries=["Code Paper"],
                       code_url="owner/repo", stars_style="badge")
        with open(json_file) as f:
            papers = json.load(f)
        assert papers[0]["codeUrl"] == "https://github.com/owner/repo"
        assert papers[0]["githubStars"] == "https://img.shields.io/github/stars/owner/repo"


@patch("awescholar.record.SemanticScholar")
def test_numeric_style_leaves_github_stars_empty(MockSS):
    """Default numeric style does not touch githubStars even when codeUrl is set."""
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.search_paper.return_value = _mock_paper(title="Num Paper", doi="10.1/num")

    with tempfile.TemporaryDirectory() as tmp:
        json_file = os.path.join(tmp, "papers.json")
        search_and_add(json_file=json_file, by="title", queries=["Num Paper"],
                       code_url="owner/repo")
        with open(json_file) as f:
            papers = json.load(f)
        assert papers[0]["codeUrl"] == "https://github.com/owner/repo"
        assert papers[0]["githubStars"] == ""


# ── annotate ──────────────────────────────────────────────────

@patch("awescholar.pipeline.run_annotate")
@patch("awescholar.record.SemanticScholar")
def test_annotate_fills_domain_and_strips_abstract(MockSS, mock_run_annotate):
    """Annotate fills domain from run_annotate and the abstract key is not persisted."""
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    paper = _mock_paper(title="Ann Paper", doi="10.1/ann")
    paper.abstract = "An abstract."
    mock_client.search_paper.return_value = paper
    mock_run_annotate.return_value = {"cat": [{"doi": "10.1/ann", "domain": "AI"}]}

    with tempfile.TemporaryDirectory() as tmp:
        json_file = os.path.join(tmp, "papers.json")
        search_and_add(json_file=json_file, by="title", queries=["Ann Paper"],
                       annotate=True, annotate_model="m", annotate_api_key="k")
        with open(json_file) as f:
            papers = json.load(f)
        assert papers[0]["domain"] == "AI"
        assert "abstract" not in papers[0]
        assert papers[0]["doi"] == "10.1/ann"


@patch("awescholar.pipeline.run_annotate", side_effect=RuntimeError("LLM boom"))
@patch("awescholar.record.SemanticScholar")
def test_annotate_failure_still_saves_record(MockSS, mock_run_annotate):
    """run_annotate raising must not lose the added record; domain stays empty."""
    mock_client = MagicMock()
    MockSS.return_value = mock_client
    mock_client.search_paper.return_value = _mock_paper(title="Fail Paper", doi="10.1/fail")

    with tempfile.TemporaryDirectory() as tmp:
        json_file = os.path.join(tmp, "papers.json")
        search_and_add(json_file=json_file, by="title", queries=["Fail Paper"],
                       annotate=True, annotate_model="m", annotate_api_key="k")
        with open(json_file) as f:
            papers = json.load(f)
        assert papers[0]["title"] == "Fail Paper"
        assert papers[0]["domain"] == ""
        assert "abstract" not in papers[0]
