"""Tests for papers.py — clue extraction, arXiv/DOI helpers, title matching, venue tier."""

import pytest

from awescholar.agentx import papers

# --- extract_paper_clue ------------------------------------------------------


def test_prefers_doi_in_paper_url():
    assert papers.extract_paper_clue(
        {"paper": "https://doi.org/10.1038/s41586-026-00000-0"}
    ) == papers.PaperClue(kind="doi", value="10.1038/s41586-026-00000-0")


def test_maps_nature_article_pages_to_doi():
    assert papers.extract_paper_clue(
        {"paper": "https://www.nature.com/articles/s43588-026-01049-y"}
    ) == papers.PaperClue(kind="doi", value="10.1038/s43588-026-01049-y")


def test_reads_arxiv_ids_from_paper_urls_and_description_mentions():
    assert papers.extract_paper_clue(
        {"paper": "https://arxiv.org/abs/2505.20286v2"}
    ) == papers.PaperClue(kind="arxiv", value="2505.20286")
    assert papers.extract_paper_clue(
        {"description": "Implementation of the paper arXiv 2505.20286"}
    ) == papers.PaperClue(kind="arxiv", value="2505.20286")


def test_falls_back_to_quoted_title():
    assert papers.extract_paper_clue(
        {
            "description": (
                'We built it for "Some Agents for Scientific Discovery" (2026).'
            ),
        }
    ) == papers.PaperClue(kind="title", value="Some Agents for Scientific Discovery")


def test_returns_none_without_precise_clue():
    assert papers.extract_paper_clue({"description": "A toolkit for bioinformatics."}) is None
    assert papers.extract_paper_clue({}) is None


def test_nature_doi_already_prefixed_is_preserved():
    assert papers.extract_paper_clue(
        {"paper": "https://www.nature.com/articles/10.1038/s43588-026-01049-y"}
    ) == papers.PaperClue(kind="doi", value="10.1038/s43588-026-01049-y")


def test_arxiv_from_homepage():
    assert papers.extract_paper_clue(
        {"homepage": "https://arxiv.org/pdf/2501.04227v3"}
    ) == papers.PaperClue(kind="arxiv", value="2501.04227")


def test_quoted_title_skips_short_fragments_and_urls():
    assert papers.extract_paper_clue(
        {"description": 'See "short" and "http://example.com" here.'}
    ) is None


# --- arxivIdToDoi / cluePaperUrl ---------------------------------------------


def test_arxiv_id_to_doi():
    assert papers.arxiv_id_to_doi("2505.20286") == "10.48550/arXiv.2505.20286"


def test_builds_canonical_urls():
    assert papers.clue_paper_url(
        papers.PaperClue(kind="doi", value="10.1/x"), None
    ) == "https://doi.org/10.1/x"
    assert papers.clue_paper_url(
        papers.PaperClue(kind="arxiv", value="2505.20286"), None
    ) == "https://arxiv.org/abs/2505.20286"
    assert papers.clue_paper_url(
        papers.PaperClue(kind="title", value="x"),
        {"paperUrl": "https://a.b/c"},
    ) == "https://a.b/c"


def test_clue_paper_url_title_without_meta_returns_none():
    assert papers.clue_paper_url(
        papers.PaperClue(kind="title", value="x"), None
    ) is None


# --- bestTitleMatch ----------------------------------------------------------


@pytest.fixture
def sample_records():
    return [
        {"title": "Agent Laboratory: Using LLM Agents as Research Assistants"},
        {"title": "Something Completely Different About Proteins"},
    ]


def test_matches_truncated_clue_against_best_covering_record(sample_records):
    result = papers.best_title_match(
        "Agent Laboratory LLM Agents Research Assistants", sample_records
    )
    assert result is not None
    assert "Agent Laboratory" in result["title"]


def test_requires_phrase(sample_records):
    assert papers.best_title_match("proteins", sample_records) is None
    assert papers.best_title_match(
        "unrelated words entirely absent from titles", sample_records
    ) is None


def test_requires_covering_ratio(sample_records):
    assert papers.best_title_match(
        "completely different agents", sample_records, threshold=0.9
    ) is None


# --- venueTier ---------------------------------------------------------------


def test_classifies_journals_conferences_and_preprints():
    assert papers.venue_tier("Nature Communications") == "journal"
    assert papers.venue_tier("Findings of EMNLP 2025") == "conference"
    assert papers.venue_tier("arXiv") == "preprint"
    assert papers.venue_tier("bioRxiv") == "preprint"


def test_returns_none_for_non_venues():
    assert papers.venue_tier("") is None
    assert papers.venue_tier("Project homepage blog") is None
    assert papers.venue_tier("Company website") is None
