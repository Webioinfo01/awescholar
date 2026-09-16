"""Tests for the read-only reader face (query / related / recommend / stats)."""

import json
import subprocess
import sys

import pytest

from awescholar.reader import (
    load_seed,
    parse_stars,
    query,
    recommend,
    related,
    score_paper,
    stats,
    tokenize,
)

ARCHIVE = {
    "AI Agents": [
        {
            "year": "2025-05-29T00:00:00",
            "title": "CDR-Agent: Intelligent Selection and Execution of Clinical "
                     "Decision Rules Using Large Language Model Agents",
            "team": "Bin Yu",
            "domain": "Emergency medicine clinical decision rules (LLM agent)",
            "venue": "AMIA Symposium",
            "paperUrl": "https://example.com/1",
            "doi": "10.48550/arXiv.2505.23055",
        },
        {
            "year": "2025-02-01",
            "title": "EHRAgent: A Human-Interactive Agent for Electronic Health Records",
            "team": "Ao Liu",
            "domain": "EHR question answering agent",
            "venue": "Nature Medicine",
            "paperUrl": "https://example.com/2",
            "doi": "10.1/ehragent",
        },
    ],
    "Benchmarks": [
        {
            "year": "2025-06-10",
            "title": "MedAgentBench: Evaluating Medical Agents",
            "team": "Chen Wei",
            "domain": "medical agent benchmark",
            "venue": "NeurIPS",
            "githubStars": "1.2k",
            "paperUrl": "https://example.com/3",
            "doi": "10.1/medagentbench",
        },
    ],
    "Reviews": [
        {
            "year": "2024-11-18",
            "title": "A Survey of Large Language Models in Clinical Workflows",
            "team": "Alina Petrova",
            "domain": "clinical LLM survey",
            "venue": "ACM Computing Surveys",
            "paperUrl": "https://example.com/4",
            "doi": "10.1/survey",
        },
    ],
}


@pytest.fixture
def archive_path(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps(ARCHIVE), encoding="utf-8")
    return str(path)


def _run_cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "awescholar.cli", *args],
        capture_output=True, text=True, check=False, cwd=cwd,
    )


# ── tokenize / scoring primitives ────────────────────────────

def test_tokenize_drops_stopwords_and_folds_plurals():
    assert tokenize("The Clinical Decision Rules using agents") == \
        ["clinical", "decision", "rule", "agent"]


def test_parse_stars_handles_suffixes_and_garbage():
    assert parse_stars("") == 0
    assert parse_stars("1.2k") == 1200
    assert parse_stars("3,400") == 3400
    assert parse_stars("n/a") == 0


def test_score_paper_weights_title_over_venue():
    title_score, _ = score_paper({"title": "protein folding", "venue": ""}, ["protein"])
    venue_score, _ = score_paper({"title": "", "venue": "protein"}, ["protein"])
    assert title_score > venue_score > 0


# ── query ────────────────────────────────────────────────────

def test_query_ranks_title_hits_first(archive_path):
    hits, meta = query(archive_path, "clinical decision rules agent")
    assert hits
    assert hits[0]["title"].startswith("CDR-Agent")
    assert "clinical" in hits[0]["matched"]
    assert meta["total"] == 4 and meta["categories"] == 3


def test_query_category_filter_and_unknown_category(archive_path):
    hits, _ = query(archive_path, "agent", category="benchmarks")
    assert {h["category"] for h in hits} == {"Benchmarks"}

    with pytest.raises(ValueError, match="Unknown category"):
        query(archive_path, "agent", category="Nope")


def test_query_uses_abstract_when_present(tmp_path):
    path = tmp_path / "updater_filter.json"
    path.write_text(json.dumps({
        "AI Agents": [{
            "title": "Opaque codename paper",
            "abstract": "We study perturbation prediction in single cell transcriptomics.",
        }]
    }), encoding="utf-8")
    hits, _ = query(str(path), "perturbation single cell")
    assert hits and "perturbation" in hits[0]["matched"]


def test_query_no_hits_returns_empty(archive_path):
    hits, _ = query(archive_path, "quantum cryptography blockchain")
    assert hits == []


# ── related ──────────────────────────────────────────────────

def test_load_seed_by_doi_and_missing_doi(archive_path):
    seed = load_seed(archive_path, doi="10.1/ehragent")
    assert seed["title"].startswith("EHRAgent")

    with pytest.raises(ValueError, match="not found in archive"):
        load_seed(archive_path, doi="10.1/unknown")


def test_load_seed_external_title_and_input(archive_path, tmp_path):
    seed = load_seed(archive_path, title="Some brand new external paper nobody curates")
    assert seed == {"title": "Some brand new external paper nobody curates"}

    seed_file = tmp_path / "seed.json"
    seed_file.write_text(json.dumps({
        "title": "External paper",
        "abstract": "LLM agents for emergency medicine clinical decision support.",
    }), encoding="utf-8")
    seed = load_seed(archive_path, input_path=str(seed_file))
    assert seed["title"] == "External paper"

    multi = tmp_path / "multi.json"
    multi.write_text(json.dumps(ARCHIVE), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        load_seed(archive_path, input_path=str(multi))


def test_related_excludes_seed_and_ranks_domain_neighbors(archive_path):
    seed = load_seed(archive_path, doi="10.48550/arXiv.2505.23055")
    hits, meta = related(archive_path, seed, top=3)
    titles = [h["title"] for h in hits]
    assert not any(t.startswith("CDR-Agent") for t in titles)
    assert meta["seed"].startswith("CDR-Agent")
    assert hits, "expected at least one neighbor"


# ── recommend ────────────────────────────────────────────────

def test_recommend_routes_categories_and_ranks(archive_path):
    hits, meta = recommend(archive_path, "medical agent benchmark", top=3)
    assert meta["routed_categories"] == ["AI Agents", "Benchmarks"]
    assert meta["candidates"] == 3
    assert hits[0]["title"].startswith("MedAgentBench")


def test_recommend_unrouted_field_falls_back_to_all(archive_path):
    hits, meta = recommend(archive_path, "quantum chemistry", top=2)
    assert meta["routed_categories"] == []
    assert meta["candidates"] == 4
    assert len(hits) == 2


# ── stats ────────────────────────────────────────────────────

def test_stats_counts_and_ranges(archive_path):
    data = stats(archive_path)
    assert data["total"] == 4
    assert len(data["categories"]) == 3
    assert data["categories"][0]["name"] == "AI Agents"
    assert data["date_range"] == ["2024-11-18", "2025-06-10"]
    assert data["venues"] == 4 and data["teams"] == 4


def test_stats_default_sorts_by_count_desc(tmp_path):
    """Default stats cover every archive category, biggest first (name tiebreak)."""
    archive = {"Zebra": [{"year": "2023-01-01", "title": "z1", "team": "t", "domain": "d", "venue": "v"}],
               "Alpha": [{"year": "2023-02-01", "title": "a1", "team": "t", "domain": "d", "venue": "v"},
                         {"year": "2023-03-01", "title": "a2", "team": "t", "domain": "d", "venue": "v"}],
               "Middle": [{"year": "2023-04-01", "title": "m1", "team": "t", "domain": "d", "venue": "v"}]}
    path = tmp_path / "data.json"
    path.write_text(json.dumps(archive), encoding="utf-8")
    data = stats(str(path))
    names = [c["name"] for c in data["categories"]]
    assert names == ["Alpha", "Middle", "Zebra"]
    assert data["total"] == 4


def test_stats_category_filter_selects_subset(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps(ARCHIVE), encoding="utf-8")
    data = stats(str(path), categories=["Benchmarks", "Reviews"])
    assert data["total"] == 2
    names = [c["name"] for c in data["categories"]]
    assert names == ["Benchmarks", "Reviews"]
    assert data["categories"][0]["count"] == 1


def test_reader_stats_cli_filters_by_category(archive_path):
    result = _run_cli("reader", "stats", "--archive", archive_path, "--category", "Reviews")
    assert result.returncode == 0
    assert "Reviews" in result.stdout
    assert "AI Agents" not in result.stdout
    assert "Benchmarks" not in result.stdout


# ── CLI ──────────────────────────────────────────────────────

def test_reader_help_lists_subcommands():
    result = _run_cli("reader", "--help")
    assert result.returncode == 0
    for cmd in ("query", "related", "recommend", "stats"):
        assert cmd in result.stdout


def test_reader_query_end_to_end(archive_path):
    result = _run_cli("reader", "query", "--archive", archive_path, "clinical decision agent")
    assert result.returncode == 0
    assert "CDR-Agent" in result.stdout
    assert "Hits" in result.stdout


def test_reader_query_json_is_parseable(archive_path):
    result = _run_cli("reader", "query", "--archive", archive_path, "ehragent", "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hits"][0]["title"].startswith("EHRAgent")


def test_reader_missing_archive_errors():
    result = _run_cli("reader", "stats", "--archive", "/nonexistent/data.json")
    assert result.returncode == 1
    assert "Error" in result.stderr
