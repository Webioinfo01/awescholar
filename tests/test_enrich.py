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
    resolve_repo,
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


def test_llm_pick_payload_carries_repo_dates_for_collision_checks():
    """Without created/pushed dates the LLM cannot spot acronym collisions
    (an old tool sharing the paper's system name)."""
    paper = {"title": "GRAPE: Heterogeneous Graph Learning", "year": 2025}
    candidates = [
        {
            "full_name": "maxiaoba/GRAPE",
            "stargazers_count": 152,
            "created_at": "2019-12-05T17:00:00Z",
            "pushed_at": "2021-03-25T17:43:17Z",
            "topics": ["graphs"],
            "description": "Handling Missing Data with Graph Representation Learning",
        }
    ]
    with patch("awescholar.enrich.complete") as mock_complete:
        from awescholar.enrich import RepoPick
        mock_complete.return_value = RepoPick(repo="", reason="collision")
        assert _llm_pick(paper, candidates, "m", "key", None) is None
        payload = json.loads(mock_complete.call_args.args[2])
        sent = payload["candidates"][0]
        assert sent["created"] == "2019-12-05"
        assert sent["pushed"] == "2021-03-25"
        assert sent["topics"] == ["graphs"]
        assert "created around or after the paper" in mock_complete.call_args.args[1]


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


def test_system_name_extraction():
    from awescholar.enrich import _system_name
    assert _system_name("MetaBeeAI: an AI pipeline for reviews") == "MetaBeeAI"
    assert _system_name("TxAgent — therapeutic reasoning") == "TxAgent"
    assert _system_name("A study of agents in biology") == ""
    assert _system_name("Some Extremely Long System Name With Many Words: x") == ""
    assert _system_name("") == ""


def test_resolve_repo_searches_system_name_before_full_title():
    """System-name query finds repos the full-title phrase search misses."""
    paper = {"title": "MetaBeeAI: an AI pipeline for reviews"}
    metabeeai = _repo("MetaBeeAI/MetaBeeAI", description="Main MetaBeeAI pipeline")
    seen_queries = []

    def fake_search(q, t, per_page=5):
        seen_queries.append(q)
        if "MetaBeeAI" in q and "pipeline for reviews" not in q:
            return [metabeeai]
        return []

    with patch("awescholar.enrich.search_repositories", side_effect=fake_search):
        pick = resolve_repo(paper, token=None)
    assert pick["full_name"] == "MetaBeeAI/MetaBeeAI"
    assert len(seen_queries) == 1  # never fell through to the full-title query


def test_resolve_repo_falls_through_when_first_round_rejects():
    """An arXiv round that surfaces only wrong candidates must not end the
    search — the system-name round still gets its chance."""
    paper = {"title": "MetaBeeAI: an AI pipeline for reviews",
             "paperUrl": "https://arxiv.org/abs/2505.00001"}
    good = _repo("MetaBeeAI/MetaBeeAI", description="Main MetaBeeAI pipeline")
    seen_queries = []

    def fake_search(q, t, per_page=5):
        seen_queries.append(q)
        if q.startswith('"2505'):
            return [_repo("x/awesome-bio-list")]  # cites the ID, is not the code
        if "MetaBeeAI" in q and "pipeline for reviews" not in q:
            return [good]
        return []

    with patch("awescholar.enrich.search_repositories", side_effect=fake_search):
        pick = resolve_repo(paper, token=None)
    assert pick["full_name"] == "MetaBeeAI/MetaBeeAI"
    assert len(seen_queries) == 2  # arXiv round rejected, system-name round won


def test_popularity_accepts_decisive_star_lead_on_bare_repos():
    """BioMaster pattern: real repo, empty description, 113 stars vs 0."""
    title = _title_tokens("BioMaster: Multi-agent System for Automated Bioinformatics")
    candidates = [_repo("ai4nucleome/BioMaster", stars=113),
                  _repo("Vincentcchu/BioMaster", stars=0)]
    assert _auto_pick(title, "", candidates)["full_name"] == "ai4nucleome/BioMaster"


def test_popularity_rejects_small_star_counts_and_narrow_leads():
    title = _title_tokens("BioMaster: Multi-agent System for Automated Bioinformatics")
    too_few = [_repo("ai4nucleome/BioMaster", stars=10), _repo("y/BioMaster")]
    assert _auto_pick(title, "", too_few) is None
    narrow = [_repo("ai4nucleome/BioMaster", stars=100), _repo("y/BioMaster", stars=40)]
    assert _auto_pick(title, "", narrow) is None


def test_popularity_rejects_repos_created_before_the_paper():
    """ruby-grape/grape (2010) colliding with a 2025 GRAPE paper is not code."""
    title = _title_tokens("GRAPE: Heterogeneous Graph Learning for Genetic Perturbation")
    candidates = [_repo("ruby-grape/grape", stars=10005)]
    candidates[0]["created_at"] = "2010-08-02T00:00:00Z"
    assert _auto_pick(title, "", candidates, paper_year=2025) is None
    # same repo created after the paper passes
    candidates[0]["created_at"] = "2025-03-01T00:00:00Z"
    assert _auto_pick(title, "", candidates, paper_year=2025)["full_name"] == "ruby-grape/grape"
    # no creation date recorded: popularity path stays closed
    del candidates[0]["created_at"]
    assert _auto_pick(title, "", candidates, paper_year=2025) is None


# ── enrich_archive (AgentX mode) ─────────────────────────────

def _agentx_repo(full_name="x/agent", **overrides):
    base = {
        "name": full_name.split("/", 1)[1],
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "stargazers_count": 99, "language": "Python",
        "pushed_at": "2026-09-10T00:00:00Z", "open_issues_count": 7,
        "license": {"spdx_id": "MIT"}, "description": "An agent",
        "homepage": "https://project.example", "archived": False,
    }
    base.update(overrides)
    return base


def _write_snapshot(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_snapshot(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_enrich_agentx_updates_only_github_fields_and_preserves_status():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents-snapshot.json")
        _write_snapshot(path, {
            "agents": [{
                "slug": "agentlaboratory", "name": "AgentLaboratory",
                "repo": "SamuelSchmidgall/AgentLaboratory",
                "githubUrl": "https://github.com/SamuelSchmidgall/AgentLaboratory",
                "homepage": "https://lab.example",
                "paper": "https://arxiv.org/abs/2501.04227",
                "paperMeta": {"firstAuthor": "Samuel Schmidgall", "authors": "Samuel Schmidgall, Yusheng Su", "citations": 10},
                "category": "autonomous-research", "tags": ["biology", "llm"],
                "stars": 5846, "pushedAt": "2025-08-20T21:46:43Z", "openIssues": 59,
                "language": "Python", "license": "MIT",
                "description": "Old description", "status": "active",
                "source": "awescholar", "sourceUrl": None,
            }],
            "counts": {"total": 1, "gone": 0},
        })

        repo = _agentx_repo("SamuelSchmidgall/AgentLaboratory",
                            stargazers_count=6001,
                            pushed_at="2026-09-12T08:00:00Z",
                            open_issues_count=12,
                            description="Fresh description")

        with patch("awescholar.enrich.fetch_repo", return_value=repo):
            stats = enrich_archive(path, token="t", mode="agentx", no_backup=True)

        data = _read_snapshot(path)
        agent = data["agents"][0]
        # GitHub-derived fields refreshed
        assert agent["stars"] == 6001
        assert agent["pushedAt"] == "2026-09-12T08:00:00Z"
        assert agent["openIssues"] == 12
        assert agent["language"] == "Python"
        assert agent["description"] == "Fresh description"
        assert agent["license"] == "MIT"
        assert agent["archived"] is False
        # Curated-first homepage preserved
        assert agent["homepage"] == "https://lab.example"
        # Status and curated fields untouched
        assert agent["status"] == "active"
        assert agent["slug"] == "agentlaboratory"
        assert agent["repo"] == "SamuelSchmidgall/AgentLaboratory"
        assert agent["githubUrl"] == "https://github.com/SamuelSchmidgall/AgentLaboratory"
        assert agent["paper"] == "https://arxiv.org/abs/2501.04227"
        assert agent["paperMeta"]["firstAuthor"] == "Samuel Schmidgall"
        assert agent["category"] == "autonomous-research"
        assert agent["tags"] == ["biology", "llm"]
        assert agent["source"] == "awescholar"
        # top-level counts untouched
        assert data["counts"] == {"total": 1, "gone": 0}
        assert stats == {"refreshed": 1, "missing_repos": 0, "skipped_no_repo": 0}


def test_enrich_agentx_curated_homepage_wins_over_repo_homepage():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents-snapshot.json")
        _write_snapshot(path, {
            "agents": [{
                "slug": "lab", "name": "Lab", "repo": "x/lab",
                "githubUrl": "https://github.com/x/lab", "homepage": "https://lab.example",
                "status": "active",
            }],
            "counts": {"total": 1, "gone": 0},
        })
        repo = _agentx_repo("x/lab", homepage="https://project.example")

        with patch("awescholar.enrich.fetch_repo", return_value=repo):
            enrich_archive(path, token="t", mode="agentx", no_backup=True)

        agent = _read_snapshot(path)["agents"][0]
        assert agent["homepage"] == "https://lab.example"


def test_enrich_agentx_fills_homepage_when_curated_empty():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents-snapshot.json")
        _write_snapshot(path, {
            "agents": [{"slug": "lab", "name": "Lab", "repo": "x/lab",
                        "githubUrl": "https://github.com/x/lab",
                        "homepage": "", "status": "active"}],
            "counts": {"total": 1, "gone": 0},
        })
        repo = _agentx_repo("x/lab", homepage="https://project.example")

        with patch("awescholar.enrich.fetch_repo", return_value=repo):
            enrich_archive(path, token="t", mode="agentx", no_backup=True)

        agent = _read_snapshot(path)["agents"][0]
        assert agent["homepage"] == "https://project.example"


def test_enrich_agentx_leaves_null_homepage_alone():
    """null is the registry's "deliberately no homepage" marker, not a fill
    request — only an explicit empty string asks for the GitHub homepage."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents-snapshot.json")
        _write_snapshot(path, {
            "agents": [{"slug": "lab", "name": "Lab", "repo": "x/lab",
                        "githubUrl": "https://github.com/x/lab",
                        "homepage": None, "status": "active"}],
            "counts": {"total": 1, "gone": 0},
        })
        repo = _agentx_repo("x/lab", homepage="https://project.example")

        with patch("awescholar.enrich.fetch_repo", return_value=repo):
            enrich_archive(path, token="t", mode="agentx", no_backup=True)

        agent = _read_snapshot(path)["agents"][0]
        assert agent["homepage"] is None


def test_enrich_agentx_persists_owner_archived_flag():
    """archived feeds the registry's same-run owner-archived → gone policy."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents-snapshot.json")
        _write_snapshot(path, {
            "agents": [{"slug": "a", "name": "A", "repo": "x/a",
                        "status": "active"}],
            "counts": {"total": 1, "gone": 0},
        })
        repo = _agentx_repo("x/a", archived=True)

        with patch("awescholar.enrich.fetch_repo", return_value=repo):
            enrich_archive(path, token="t", mode="agentx", no_backup=True)

        agent = _read_snapshot(path)["agents"][0]
        assert agent["archived"] is True
        assert agent["status"] == "active"  # lifecycle stays with the registry


def test_enrich_agentx_skips_agents_without_repo():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents-snapshot.json")
        _write_snapshot(path, {
            "agents": [
                {"slug": "no-repo", "name": "NoRepo", "repo": "",
                 "status": "active"},
                {"slug": "real", "name": "Real", "repo": "x/real",
                 "status": "active"},
            ],
            "counts": {"total": 2, "gone": 0},
        })

        def fake_fetch(owner_repo, token):
            assert owner_repo == "x/real", f"unexpected fetch: {owner_repo!r}"
            return _agentx_repo("x/real", stargazers_count=10)

        with patch("awescholar.enrich.fetch_repo", side_effect=fake_fetch):
            stats = enrich_archive(path, token="t", mode="agentx", no_backup=True)

        agents = {a["slug"]: a for a in _read_snapshot(path)["agents"]}
        assert "stars" not in agents["no-repo"]
        assert agents["real"]["stars"] == 10
        assert stats == {"refreshed": 1, "missing_repos": 0, "skipped_no_repo": 1}


def test_enrich_agentx_does_not_touch_status_on_missing_repo():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents-snapshot.json")
        _write_snapshot(path, {
            "agents": [{"slug": "gone", "name": "Gone", "repo": "x/gone",
                        "stars": 999, "status": "active"}],
            "counts": {"total": 1, "gone": 0},
        })

        with patch("awescholar.enrich.fetch_repo", return_value=None):
            stats = enrich_archive(path, token="t", mode="agentx", no_backup=True)

        agent = _read_snapshot(path)["agents"][0]
        assert agent["status"] == "active"
        assert agent["stars"] == 999  # unchanged on fetch failure
        assert stats == {"refreshed": 0, "missing_repos": 1, "skipped_no_repo": 0}


def test_enrich_agentx_noassertion_license_preserves_existing():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents-snapshot.json")
        _write_snapshot(path, {
            "agents": [{"slug": "a", "name": "A", "repo": "x/a",
                        "license": "MIT", "status": "active"}],
            "counts": {"total": 1, "gone": 0},
        })
        repo = _agentx_repo("x/a", license={"spdx_id": "NOASSERTION"})

        with patch("awescholar.enrich.fetch_repo", return_value=repo):
            enrich_archive(path, token="t", mode="agentx", no_backup=True)

        agent = _read_snapshot(path)["agents"][0]
        assert agent["license"] == "MIT"


def test_enrich_agentx_noassertion_fills_when_license_curated_empty():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents-snapshot.json")
        _write_snapshot(path, {
            "agents": [{"slug": "a", "name": "A", "repo": "x/a",
                        "license": None, "status": "active"}],
            "counts": {"total": 1, "gone": 0},
        })
        repo = _agentx_repo("x/a", license={"spdx_id": "NOASSERTION"})

        with patch("awescholar.enrich.fetch_repo", return_value=repo):
            enrich_archive(path, token="t", mode="agentx", no_backup=True)

        agent = _read_snapshot(path)["agents"][0]
        assert agent["license"] is None


def test_enrich_agentx_creates_backup_by_default_and_respects_no_backup():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "agents-snapshot.json")
        _write_snapshot(path, {
            "agents": [{"slug": "a", "name": "A", "repo": "x/a",
                        "stars": 1, "status": "active"}],
            "counts": {"total": 1, "gone": 0},
        })
        with patch("awescholar.enrich.fetch_repo",
                   return_value=_agentx_repo("x/a", stargazers_count=42)):
            enrich_archive(path, token="t", mode="agentx")  # backup on by default

        assert any(f.startswith("agents-snapshot.json.") and f.endswith(".bak")
                   for f in os.listdir(tmp))

        path2 = os.path.join(tmp, "agents-snapshot2.json")
        _write_snapshot(path2, {
            "agents": [{"slug": "a", "name": "A", "repo": "x/a",
                        "stars": 1, "status": "active"}],
            "counts": {"total": 1, "gone": 0},
        })
        with patch("awescholar.enrich.fetch_repo",
                   return_value=_agentx_repo("x/a", stargazers_count=42)):
            enrich_archive(path2, token="t", mode="agentx", no_backup=True)

        backups = [f for f in os.listdir(tmp) if f.endswith(".bak")
                   and f.startswith("agents-snapshot2.json")]
        assert backups == []


def test_enrich_agentx_rejects_category_dict_shape():
    """Passing an awesome-list archive without the --agentx CLI flag is the
    expected mistake; the function must raise a clear error."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "data.json")
        _write_archive(path, {"AI Agents": [{
            "year": "2025.01", "title": "T", "codeUrl": "",
        }]})

        import pytest
        with pytest.raises(ValueError, match="--agentx"):
            enrich_archive(path, token=None, mode="agentx", no_backup=True)


def test_enrich_archive_mode_unchanged():
    """Regression guard: dispatching to archive mode preserves the existing
    behavior even when callers happen to also pass mode='archive' explicitly."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "data.json")
        _write_archive(path, {"AI Agents": [{
            "year": "2025.01", "title": "T", "codeUrl": "https://github.com/a/b",
            "githubStars": "",
        }]})

        with patch("awescholar.enrich.search_repositories", return_value=[]), \
             patch("awescholar.enrich.fetch_repo",
                   return_value={"stargazers_count": 42}):
            stats = enrich_archive(path, token=None, mode="archive", no_backup=True)

        paper = _read_archive(path)["AI Agents"][0]
        assert paper["githubStars"] == 42
        assert stats["refreshed"] == 1
        assert stats["resolved"] == 0

