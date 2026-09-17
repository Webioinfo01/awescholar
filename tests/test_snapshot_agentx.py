"""Port of agentx-cli snapshot.test.ts + slug.test.ts, plus a lock on the
real registry: Python `sorted` matches the TS writer's `localeCompare` order.
"""

import copy
import json
import os

import pytest

from awescholar.agentx import snapshot

# Inline copy of agentx-cli/test/fixtures/demo-repo/data/agents-snapshot.json.
FIXTURE = {
    "agents": [
        {
            "slug": "alpha-agent",
            "name": "Alpha Agent",
            "repo": "example/alpha-agent",
            "githubUrl": "https://github.com/example/alpha-agent",
            "homepage": None,
            "paper": "https://doi.org/10.1038/s41586-026-00000-0",
            "paperMeta": {
                "title": "Alpha Agent: an autonomous assistant for biology research",
                "venue": "Nature",
                "doi": "10.1038/s41586-026-00000-0",
                "year": "2026.03",
                "authors": "A. Researcher, B. Author",
                "firstAuthor": "A. Researcher",
                "paperUrl": "https://doi.org/10.1038/s41586-026-00000-0",
                "citations": 4,
            },
            "category": "bio-omics",
            "tags": ["Stanford", "Nature"],
            "language": "Python",
            "stars": 42,
            "pushedAt": "2026-09-01T00:00:00Z",
            "openIssues": 2,
            "license": "MIT",
            "description": "An autonomous assistant for biology research.",
            "status": "active",
            "source": "manual",
            "sourceUrl": None,
        },
        {
            "slug": "beta-agent",
            "name": "Beta Agent",
            "repo": "example/beta-agent",
            "githubUrl": "https://github.com/example/beta-agent",
            "homepage": "https://beta.example.org",
            "paper": None,
            "category": "chem-drug",
            "tags": ["MCP"],
            "language": "TypeScript",
            "stars": 7,
            "pushedAt": "2026-08-15T00:00:00Z",
            "openIssues": 0,
            "license": None,
            "description": "MCP server for molecular workflows.",
            "status": "active",
            "source": "curated",
            "sourceUrl": None,
        },
    ],
    "counts": {"total": 2, "gone": 0},
}

# The live AgentX registry written by the TypeScript CLI; used to lock the
# sorted()-vs-localeCompare equivalence against real data.
REGISTRY = "/Users/peng/Desktop/Project/phd/agentx/website/data/agents-snapshot.json"


def _fixture() -> dict:
    return copy.deepcopy(FIXTURE)


def _load_registry() -> dict:
    if not os.path.exists(REGISTRY):
        pytest.skip("agentx registry checkout not present")
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


# ── snapshot read/write ───────────────────────────────────────


def test_snapshot_path_resolves_data_dir():
    assert snapshot.snapshot_path("/repo") == os.path.join(
        "/repo", "data", "agents-snapshot.json"
    )


def test_round_trips_a_file_written_in_stable_slug_order(tmp_path):
    file = _fixture()
    # Feed agents out of order; write_snapshot must restore slug order.
    file["agents"] = list(reversed(file["agents"]))

    path = str(tmp_path / "data" / "agents-snapshot.json")  # parents get created
    snapshot.write_snapshot(path, file)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    assert [a["slug"] for a in raw["agents"]] == ["alpha-agent", "beta-agent"]
    assert raw["counts"]["total"] == 2

    reread = snapshot.read_snapshot(path)
    assert len(reread["agents"]) == 2
    assert reread["agents"][0]["name"] == "Alpha Agent"


def test_registry_stored_order_matches_python_sorted():
    """Locks write_snapshot's `sorted` against the TS `localeCompare` order.

    The TypeScript writer sorts with `a.slug.localeCompare(b.slug)` (ICU
    collation); this Python port sorts by codepoint. Verified identical on
    the real registry, whose slugs are ASCII lowercase/digits/"-"/"_".
    """
    stored = _load_registry()
    slugs = [a["slug"] for a in stored["agents"]]
    assert slugs == sorted(slugs)


def test_rewrite_preserves_registry_agent_ordering(tmp_path):
    stored = _load_registry()
    path = str(tmp_path / "agents-snapshot.json")
    snapshot.write_snapshot(path, stored)
    with open(path, encoding="utf-8") as f:
        rewritten = json.load(f)
    assert [a["slug"] for a in rewritten["agents"]] == [
        a["slug"] for a in stored["agents"]
    ]
    assert json.dumps(rewritten["agents"], ensure_ascii=False) == json.dumps(
        stored["agents"], ensure_ascii=False
    )


# ── slugify ───────────────────────────────────────────────────


def test_slugify_lowercases_and_dashes_non_alphanumerics():
    assert snapshot.slugify("MedClaw (zteyesreal)") == "medclaw-zteyesreal"


def test_slugify_keeps_unicode_letters_and_trims_dashes():
    assert snapshot.slugify("--Alpha! Beta--") == "alpha-beta"
    assert snapshot.slugify("α-agente") == "α-agente"


def test_slugify_caps_at_64_chars_and_never_returns_empty():
    assert len(snapshot.slugify("a" * 100)) <= 64
    assert snapshot.slugify("!!!") == "agent"


def test_slugify_dashes_underscores_like_the_ts_letter_number_classes():
    # \p{L}\p{N} excludes "_" — str.isalnum() is False for "_" too.
    assert snapshot.slugify("paper_claw") == "paper-claw"


# ── unique_slug ───────────────────────────────────────────────


def test_unique_slug_passes_through_free_slugs_and_registers_them():
    used = set()
    assert snapshot.unique_slug("alpha", used) == "alpha"
    assert "alpha" in used


def test_unique_slug_suffixes_minus2_on_collision():
    assert snapshot.unique_slug("alpha", {"alpha"}) == "alpha-2"


# ── merge_snapshot_agent ──────────────────────────────────────


def test_merge_keeps_falsy_values_and_curated_metadata():
    agent = {
        "name": "Alpha",
        "repo": "example/alpha",
        "githubUrl": None,
        "homepage": "   ",
        "paper": None,
        "category": "others",
        "tags": [],
        "language": "Rust",
        "stars": 5,
        "pushedAt": None,
        "openIssues": 1,
        "license": "MIT",
        "description": "curated description",
        "retiredReason": "idle",
    }
    github = {
        "language": None,
        "stargazers_count": 0,
        "pushed_at": "2026-01-01T00:00:00Z",
        "open_issues_count": 0,
        "archived": False,
        "description": "",
        "homepage": "https://alpha.example.org",
    }

    out = snapshot.merge_snapshot_agent(agent, "alpha", github, "gone", None)

    # TS ?? semantics: 0 / "" / False from GitHub survive instead of falling
    # back; null/absent GitHub fields fall back to the curated record.
    assert out["language"] == "Rust"  # github null -> curated
    assert out["stars"] == 0  # falsy github value survives
    assert out["openIssues"] == 0
    assert out["archived"] is False
    assert out["description"] == ""  # empty string survives ??
    assert out["pushedAt"] == "2026-01-01T00:00:00Z"
    # agent homepage normalizes to null -> github homepage wins.
    assert out["homepage"] == "https://alpha.example.org"
    # license stays null (param) -> curated "MIT" applies.
    assert out["license"] == "MIT"
    assert out["status"] == "gone"
    assert out["autoStableExempt"] is False
    assert out["source"] == "curated"
    assert out["sourceUrl"] is None
    # Graveyard metadata rides along.
    assert out["retiredReason"] == "idle"
    assert "retiredStars" not in out
    # TS object literal field order — JSON diffs stay stable.
    assert list(out) == [
        "slug",
        "name",
        "repo",
        "githubUrl",
        "homepage",
        "paper",
        "paperMeta",
        "category",
        "tags",
        "language",
        "stars",
        "pushedAt",
        "openIssues",
        "archived",
        "license",
        "description",
        "status",
        "autoStableExempt",
        "source",
        "sourceUrl",
        "retiredReason",
    ]


def test_merge_without_github_keeps_curated_values():
    agent = _fixture()["agents"][0]
    out = snapshot.merge_snapshot_agent(agent, "alpha-agent", None, "active", "Apache-2.0")
    assert out["slug"] == "alpha-agent"
    assert out["language"] == "Python"
    assert out["stars"] == 42
    assert out["license"] == "Apache-2.0"
    assert out["description"] == "An autonomous assistant for biology research."
    assert out["homepage"] is None
