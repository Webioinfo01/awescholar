"""Tests for enrich.py — repo matching heuristics and archive enrichment."""

import json
import os
import tempfile
from unittest.mock import patch

from awescholar.enrich import (
    _auto_pick,
    _llm_pick,
    _repo_tokens,
    _score_candidate,
    _title_tokens,
    enrich_archive,
)


def _repo(full_name, description="", stars=0):
    name = full_name.split("/")[1]
    return {"full_name": full_name, "name": name, "description": description,
            "stargazers_count": stars, "html_url": f"https://github.com/{full_name}"}


# ── tokenization ──────────────────────────────────────────────

def test_repo_tokens_splits_camel_and_separators():
    assert _repo_tokens("AgentLaboratory") == {"agent", "laboratory", "agentlaboratory"}
    assert _repo_tokens("scikit-learn") == {"scikit", "learn", "scikitlearn"}
    assert _repo_tokens("scGPT") == {"sc", "gpt", "scgpt"}


def test_title_tokens_drops_stopwords_and_short_words():
    tokens = _title_tokens("A New Approach for Using Agents in Biology")
    assert "using" not in tokens
    assert "approach" not in tokens
    assert "new" not in tokens
    assert tokens == {"agents", "biology"}


def test_title_tokens_camel_splits_compound_names():
    """Compound system names in titles must match repo-style tokenization."""
    assert _title_tokens("BioAgent rules") >= {"bio", "agent", "bioagent", "rules"}


# ── scoring ───────────────────────────────────────────────────

def test_name_subset_alone_does_not_auto_accept():
    title = _title_tokens("BioAgent: an agent for biology")
    assert _score_candidate(title, "", _repo("x/BioAgent")) == 4


def test_generic_only_repo_name_earns_no_subset_bonus():
    title = _title_tokens("A Framework for Agents in Medicine")
    assert _score_candidate(title, "", _repo("x/agents")) < 4


def test_name_subset_plus_arxiv_citation_auto_accepts():
    title = _title_tokens("DeepScience: automated discovery")
    repo = _repo("x/deepscience", description="Code for arXiv:2501.04227")
    assert _score_candidate(title, "2501.04227", repo) >= 5


def test_arxiv_citation_alone_does_not_auto_accept():
    """A list repo that merely cites the paper must not win on its own."""
    title = _title_tokens("DeepScience: automated discovery")
    repo = _repo("x/awesome-bioagents", description="Covers arXiv:2501.04227")
    assert _score_candidate(title, "2501.04227", repo) < 5


# ── auto pick ─────────────────────────────────────────────────

def test_auto_pick_takes_corroborated_winner():
    title = _title_tokens("BioAgent: an agent for biology")
    candidates = [
        _repo("x/BioAgent", description="Official code for arXiv:2501.04227"),
        _repo("y/something-else"),
    ]
    assert _auto_pick(title, "2501.04227", candidates)["full_name"] == "x/BioAgent"


def test_auto_pick_rejects_name_only_match_without_corroboration():
    title = _title_tokens("BioAgent: an agent for biology")
    candidates = [_repo("x/BioAgent", stars=10)]
    assert _auto_pick(title, "", candidates) is None


def test_auto_pick_rejects_close_race():
    title = _title_tokens("BioAgent: an agent for biology")
    candidates = [_repo("x/BioAgent"), _repo("y/bioagent-toolkit")]
    # both names derive from the title: no margin, no auto pick
    assert _auto_pick(title, "", candidates) is None


def test_auto_pick_rejects_below_threshold():
    title = _title_tokens("A Framework for Agents in Medicine")
    assert _auto_pick(title, "", [_repo("x/unrelated")]) is None


# ── LLM pick ──────────────────────────────────────────────────

def test_llm_pick_returns_matching_candidate():
    paper = {"title": "T"}
    candidates = [_repo("x/BioAgent"), _repo("y/other")]
    with patch("awescholar.enrich.complete") as mock_complete:
        from awescholar.enrich import RepoPick
        mock_complete.return_value = RepoPick(repo="x/BioAgent", reason="official")
        assert _llm_pick(paper, candidates, "m", "key", None)["full_name"] == "x/BioAgent"


def test_llm_pick_ignores_hallucinated_repo():
    paper = {"title": "T"}
    candidates = [_repo("x/BioAgent")]
    with patch("awescholar.enrich.complete") as mock_complete:
        from awescholar.enrich import RepoPick
        mock_complete.return_value = RepoPick(repo="not/in-candidates", reason="")
        assert _llm_pick(paper, candidates, "m", "key", None) is None


def test_llm_pick_empty_repo_means_none():
    paper = {"title": "T"}
    with patch("awescholar.enrich.complete") as mock_complete:
        from awescholar.enrich import RepoPick
        mock_complete.return_value = RepoPick(repo="", reason="no official code")
        assert _llm_pick(paper, [_repo("x/BioAgent")], "m", "key", None) is None


# ── enrich_archive ────────────────────────────────────────────

def _write_archive(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_archive(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_enrich_resolves_repo_and_writes_numeric_stars():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "data.json")
        _write_archive(path, {"AI Agents": [{
            "year": "2025.01", "title": "BioAgent: an agent for biology",
            "paperUrl": "https://arxiv.org/abs/2501.04227", "doi": "",
        }]})

        repo = _repo("x/BioAgent", description="Code for arXiv:2501.04227", stars=17)

        with patch("awescholar.enrich.search_repositories",
                   side_effect=lambda q, t, per_page=5: [repo]), \
             patch("awescholar.enrich.fetch_repo", return_value=None):
            stats = enrich_archive(path, token=None, no_backup=True)

        paper = _read_archive(path)["AI Agents"][0]
        assert paper["codeUrl"] == "https://github.com/x/BioAgent"
        assert paper["githubStars"] == 17
        assert stats["resolved"] == 1


def test_enrich_never_overwrites_existing_codeurl():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "data.json")
        _write_archive(path, {"AI Agents": [{
            "year": "2025.01", "title": "BioAgent: an agent for biology",
            "codeUrl": "https://gitlab.com/keep/me", "githubStars": "",
        }]})

        with patch("awescholar.enrich.search_repositories", return_value=[_repo("x/BioAgent")]), \
             patch("awescholar.enrich.fetch_repo", return_value=None):
            enrich_archive(path, token=None, no_backup=True)

        paper = _read_archive(path)["AI Agents"][0]
        assert paper["codeUrl"] == "https://gitlab.com/keep/me"


def test_enrich_refreshes_stars_and_migrates_badge_urls():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "data.json")
        _write_archive(path, {"AI Agents": [
            {"year": "2025.01", "title": "Known", "codeUrl": "https://github.com/a/b",
             "githubStars": "https://img.shields.io/github/stars/a/b"},
            {"year": "2025.02", "title": "Badge only", "codeUrl": "",
             "githubStars": "https://img.shields.io/github/stars/c/d"},
        ]})

        with patch("awescholar.enrich.search_repositories", return_value=[]), \
             patch("awescholar.enrich.fetch_repo",
                   return_value={"stargazers_count": 99}):
            stats = enrich_archive(path, token=None, no_backup=True)

        papers = _read_archive(path)["AI Agents"]
        assert papers[0]["githubStars"] == 99
        # the badge URL itself reveals the repo: codeUrl filled, stars refreshed
        assert papers[1]["codeUrl"] == "https://github.com/c/d"
        assert papers[1]["githubStars"] == 99
        assert stats["refreshed"] == 2


def test_enrich_respects_limit_and_backup():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "data.json")
        _write_archive(path, {"AI Agents": [
            {"year": "2025.01", "title": "One"},
            {"year": "2025.02", "title": "Two"},
        ]})

        with patch("awescholar.enrich.search_repositories", return_value=[]), \
             patch("awescholar.enrich.fetch_repo", return_value=None):
            stats = enrich_archive(path, token=None, limit=1)

        assert stats["resolve_candidates"] == 1
        backups = [f for f in os.listdir(tmp) if f.endswith(".bak")]
        assert len(backups) == 1


def test_arxiv_search_hit_with_name_subset_auto_accepts():
    """GitHub matched the arXiv ID in the repo's README via the search index —
    that counts as the repo citing the paper even without fetching the README."""
    title = _title_tokens("BioAgent: an agent for biology")
    repo = _repo("x/BioAgent")  # description does not mention the arXiv ID
    repo["_arxiv_via_search"] = True
    assert _score_candidate(title, "2501.04227", repo, arxiv_via_search=True) >= 5


def test_owner_match_plus_name_subset_auto_accepts():
    """MetaBeeAI pattern: a dedicated org shipping the same-named repo."""
    title = _title_tokens("MetaBeeAI: an AI pipeline for full-text systematic reviews")
    repo = _repo("MetaBeeAI/MetaBeeAI", description="Main MetaBeeAI pipeline")
    assert _score_candidate(title, "", repo) >= 5


def test_description_restatement_plus_name_subset_auto_accepts():
    """AgentMol pattern: the description restates the paper title."""
    title = _title_tokens(
        "AgentMol: Multi-Model AI System for Automatic Drug-Target Identification")
    repo = _repo("golempharm/agentmol",
                 description="AgentMol: multimodel AI system for automatic drug-target identification")
    assert _score_candidate(title, "", repo) >= 5


def test_supporting_signals_alone_stay_below_bar():
    title = _title_tokens("BioAgent: an agent for biology")
    assert _score_candidate(title, "", _repo("x/BioAgent", description="BioAgent agent bio")) < 5
