"""Tests for agentx_export.py — candidate shaping and snapshot compatibility."""

import json
import os
import tempfile

from awescholar.agentx_export import agentx_slugify, export_agentx


def test_agentx_slugify_mirrors_agentx_rules():
    assert agentx_slugify("AgentLaboratory") == "agentlaboratory"
    assert agentx_slugify("Bio Agent! Toolkit") == "bio-agent-toolkit"
    assert agentx_slugify("  --leading--and--trailing--  ") == "leading-and-trailing"
    assert agentx_slugify("x" * 100) == "x" * 64
    assert agentx_slugify("!!!") == "agent"
    assert agentx_slugify("") == "agent"


def _paper(**overrides):
    base = {
        "year": "2025.06", "title": "Agent Laboratory", "team": "Samuel Schmidgall, Yusheng Su",
        "team website": "https://lab.example", "affiliation": "MIT", "domain": "agents",
        "venue": "EMNLP", "paperUrl": "https://arxiv.org/abs/2501.04227",
        "codeUrl": "https://github.com/SamuelSchmidgall/AgentLaboratory",
        "githubStars": 5846, "citations": 10, "doi": "10.18653/v1/x",
    }
    base.update(overrides)
    return base


def test_export_writes_agentx_snapshot_shape():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        out = os.path.join(tmp, "candidates.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump({"AI Agents": [_paper()]}, f)

        export_agentx(archive, out, token=None, status_cb=lambda *_: None)

        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        assert set(data) == {"agents", "counts"}
        assert data["counts"] == {"total": 1, "graveyard": 0}

        agent = data["agents"][0]
        assert agent["slug"] == "agentlaboratory"
        assert agent["name"] == "AgentLaboratory"
        assert agent["repo"] == "SamuelSchmidgall/AgentLaboratory"
        assert agent["githubUrl"] == "https://github.com/SamuelSchmidgall/AgentLaboratory"
        assert agent["homepage"] == "https://lab.example"
        assert agent["paper"] == "https://arxiv.org/abs/2501.04227"
        assert agent["stars"] == 5846  # archive value when no token/live fetch
        assert agent["status"] == "active"
        assert agent["source"] == "awescholar"
        assert agent["paperMeta"]["firstAuthor"] == "Samuel Schmidgall"
        assert agent["paperMeta"]["authors"] == "Samuel Schmidgall, Yusheng Su"
        assert agent["paperMeta"]["citations"] == 10


def test_export_skips_papers_without_github_repo_and_dedupes():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        out = os.path.join(tmp, "candidates.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump({
                "AI Agents": [
                    _paper(title="First entry"),
                    _paper(title="Same repo elsewhere", doi="10.2/y"),
                    _paper(title="No code", codeUrl=""),
                    _paper(title="Gitlab only", codeUrl="https://gitlab.com/a/b"),
                ],
            }, f)

        stats = export_agentx(archive, out, token=None, status_cb=lambda *_: None)

        with open(out, encoding="utf-8") as f:
            agents = json.load(f)["agents"]
        assert len(agents) == 1
        assert stats["skipped_no_repo"] == 2
        assert stats["deduped_repos"] == 1


def test_export_applies_category_map_with_default_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        out = os.path.join(tmp, "candidates.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump({
                "AI Agents": [_paper()],
                "Reviews": [_paper(title="Review one", codeUrl="https://github.com/a/review1")],
            }, f)

        export_agentx(archive, out, token=None,
                      category_map={"AI Agents": "autonomous-research"},
                      default_category="platforms", status_cb=lambda *_: None)

        with open(out, encoding="utf-8") as f:
            agents = json.load(f)["agents"]
        by_repo = {a["repo"]: a["category"] for a in agents}
        assert by_repo["SamuelSchmidgall/AgentLaboratory"] == "autonomous-research"
        assert by_repo["a/review1"] == "platforms"


def test_export_paper_url_falls_back_to_doi():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        out = os.path.join(tmp, "candidates.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump({"Reviews": [_paper(title="No arxiv",
                                          paperUrl="", doi="10.3/z")]}, f)

        export_agentx(archive, out, token=None, status_cb=lambda *_: None)

        with open(out, encoding="utf-8") as f:
            agent = json.load(f)["agents"][0]
        assert agent["paper"] == "https://doi.org/10.3/z"


def test_export_live_metrics_when_repo_fetched():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        out = os.path.join(tmp, "candidates.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump({"AI Agents": [_paper()]}, f)

        repo = {
            "name": "AgentLaboratory", "stargazers_count": 6000, "language": "Python",
            "pushed_at": "2026-09-01T00:00:00Z", "open_issues_count": 3,
            "license": {"spdx_id": "MIT"}, "description": "Automated research",
            "homepage": "https://project.example",
        }
        from unittest.mock import patch
        with patch("awescholar.agentx_export.fetch_repo", return_value=repo):
            export_agentx(archive, out, token="t", status_cb=lambda *_: None)

        with open(out, encoding="utf-8") as f:
            agent = json.load(f)["agents"][0]
        assert agent["stars"] == 6000
        assert agent["language"] == "Python"
        assert agent["license"] == "MIT"
        assert agent["pushedAt"] == "2026-09-01T00:00:00Z"


def test_export_slug_collision_appends_suffix():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        out = os.path.join(tmp, "candidates.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump({"AI Agents": [
                _paper(title="A", codeUrl="https://github.com/one/AgentLaboratory"),
                _paper(title="B", codeUrl="https://github.com/two/AgentLaboratory"),
            ]}, f)

        export_agentx(archive, out, token=None, status_cb=lambda *_: None)

        with open(out, encoding="utf-8") as f:
            agents = json.load(f)["agents"]
        slugs = sorted(a["slug"] for a in agents)
        assert slugs == ["agentlaboratory", "agentlaboratory-2"]


def test_export_tolerates_legacy_badge_url_stars():
    """Archives enriched before the numeric migration store badge URLs."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        out = os.path.join(tmp, "candidates.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump({"AI Agents": [_paper(
                githubStars="https://img.shields.io/github/stars/SamuelSchmidgall/AgentLaboratory",
            )]}, f)

        export_agentx(archive, out, token=None, status_cb=lambda *_: None)

        with open(out, encoding="utf-8") as f:
            agent = json.load(f)["agents"][0]
        assert agent["stars"] == 0


def test_export_scopes_to_requested_categories():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        out = os.path.join(tmp, "candidates.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump({
                "AI Agents": [_paper()],
                "Foundation models": [_paper(title="A big model",
                                             codeUrl="https://github.com/a/bigmodel")],
            }, f)

        export_agentx(archive, out, token=None, categories=["ai agents"],
                      status_cb=lambda *_: None)

        with open(out, encoding="utf-8") as f:
            agents = json.load(f)["agents"]
        assert [a["repo"] for a in agents] == ["SamuelSchmidgall/AgentLaboratory"]


def test_export_excludes_repos_from_existing_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        out = os.path.join(tmp, "candidates.json")
        snapshot = os.path.join(tmp, "agents-snapshot.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump({
                "AI Agents": [
                    _paper(),
                    _paper(title="New agent", codeUrl="https://github.com/a/newagent"),
                ],
            }, f)
        with open(snapshot, "w", encoding="utf-8") as f:
            json.dump({"agents": [{"repo": "samuelschmidgall/agentlaboratory"}]}, f)

        stats = export_agentx(archive, out, token=None, exclude_snapshot=snapshot,
                              status_cb=lambda *_: None)

        with open(out, encoding="utf-8") as f:
            agents = json.load(f)["agents"]
        assert [a["repo"] for a in agents] == ["a/newagent"]
        assert stats["excluded_snapshot"] == 1


def test_export_warns_for_mapped_category_missing_from_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        out = os.path.join(tmp, "candidates.json")
        snapshot = os.path.join(tmp, "agents-snapshot.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump({"AI Agents": [_paper()]}, f)
        with open(snapshot, "w", encoding="utf-8") as f:
            json.dump({"agents": [
                {"repo": "some/one", "category": "bio-omics"},
                {"repo": "some/two", "category": "platforms"},
            ]}, f)

        warnings = []
        status_cb = lambda *msgs: warnings.extend(msgs)
        export_agentx(archive, out, token=None, exclude_snapshot=snapshot,
                      category_map={"AI Agents": "autonomous-research"},
                      status_cb=status_cb)

        assert any("autonomous-research" in w for w in warnings)

        # A mapped slug present in the snapshot produces no warning.
        warnings.clear()
        export_agentx(archive, out, token=None, exclude_snapshot=snapshot,
                      category_map={"AI Agents": "bio-omics"},
                      status_cb=status_cb)
        assert not any("Warning:" in w for w in warnings)


def test_export_no_validation_without_snapshot():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        out = os.path.join(tmp, "candidates.json")
        with open(archive, "w", encoding="utf-8") as f:
            json.dump({"AI Agents": [_paper()]}, f)

        warnings = []
        export_agentx(archive, out, token=None,
                      category_map={"AI Agents": "totally-unknown"},
                      status_cb=lambda *a: warnings.append(a))

        assert not any("Warning:" in str(w) for w in warnings)
