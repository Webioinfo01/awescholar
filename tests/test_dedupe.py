"""Tests for near-duplicate hold-back during merge and dedupe resolution."""

import json
import os
import subprocess
import sys
import tempfile

from awescholar.archive import apply_dedupe_review, merge_new_to_archive

ARCHIVE = {
    "AI Agents": [
        {
            "year": "2025-05-29",
            "title": "CDR-Agent: Intelligent Selection and Execution of Clinical "
                     "Decision Rules Using Large Language Model Agents",
            "team": "Bin Yu",
            "doi": "10.48550/arXiv.2505.23055",
            "venue": "arXiv",
        }
    ]
}

# Same paper after journal publication: different DOI, near-identical title.
PUBLISHED = {
    "AI Agents": [
        {
            "year": "2025-08-01",
            "title": "CDR-Agent: Intelligent Selection and Execution of Clinical "
                     "Decision Rules Using LLM Agents",
            "team": "Bin Yu",
            "doi": "10.1093/jamia/ocaa123",
            "venue": "JAMIA",
        }
    ]
}

UNRELATED = {"AI Agents": [{"year": "2025-07-15", "title": "ProteinAgent: de novo design",
                            "team": "Li Na", "doi": "10.1/pa"}]}


def _write(path: str, data) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def _read(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _setup(tmp, new_data, archive_data=ARCHIVE):
    new = _write(os.path.join(tmp, "new.json"), new_data)
    archive = os.path.join(tmp, "data.json")
    _write(archive, archive_data)
    return new, archive


def test_near_duplicate_held_back_with_review_file():
    with tempfile.TemporaryDirectory() as tmp:
        new, archive = _setup(tmp, PUBLISHED)
        merge_new_to_archive(new, archive)
        review_path = os.path.join(tmp, "dedupe_review.json")

        assert len(_read(archive)["AI Agents"]) == 1, "duplicate must not be appended"
        review = _read(review_path)
        assert len(review) == 1
        assert review[0]["title_similarity"] >= 0.90
        assert review[0]["shared_team"] is True
        assert review[0]["existing"]["category"] == "AI Agents"


def test_unrelated_papers_merge_without_review():
    with tempfile.TemporaryDirectory() as tmp:
        new, archive = _setup(tmp, UNRELATED)
        merge_new_to_archive(new, archive)

        assert len(_read(archive)["AI Agents"]) == 2
        assert not os.path.exists(os.path.join(tmp, "dedupe_review.json"))


def test_no_dedupe_flag_restores_append_behavior():
    with tempfile.TemporaryDirectory() as tmp:
        new, archive = _setup(tmp, PUBLISHED)
        merge_new_to_archive(new, archive, dedupe=False)

        assert len(_read(archive)["AI Agents"]) == 2
        assert not os.path.exists(os.path.join(tmp, "dedupe_review.json"))


def test_stale_review_file_cleared_by_clean_merge():
    with tempfile.TemporaryDirectory() as tmp:
        new, archive = _setup(tmp, UNRELATED)
        stale = _write(os.path.join(tmp, "dedupe_review.json"), [{"incoming": {}, "existing": {}}])
        merge_new_to_archive(new, archive)
        assert not os.path.exists(stale), "clean merge must clear the stale review file"


def test_apply_dedupe_keep_published_replaces_with_journal_version():
    with tempfile.TemporaryDirectory() as tmp:
        new, archive = _setup(tmp, PUBLISHED)
        merge_new_to_archive(new, archive)
        review = os.path.join(tmp, "dedupe_review.json")

        applied = apply_dedupe_review(review, archive, keep="published")

        entry = _read(archive)["AI Agents"][0]
        assert entry["venue"] == "JAMIA"
        assert entry["doi"] == "10.1093/jamia/ocaa123"
        assert applied[0]["resolution"] == "kept incoming (published)"
        assert not os.path.exists(review)


def test_apply_dedupe_keep_older_existing_wins():
    with tempfile.TemporaryDirectory() as tmp:
        # Archive holds the newer published version; incoming is the older preprint.
        newer_archive = {"AI Agents": [dict(ARCHIVE["AI Agents"][0], venue="JAMIA",
                                            doi="10.1093/jamia/ocaa123", year="2025-08-01")]}
        incoming = {"AI Agents": [dict(PUBLISHED["AI Agents"][0], venue="arXiv",
                                       doi="10.48550/arXiv.2505.23055", year="2025-05-29")]}
        new, archive = _setup(tmp, incoming, newer_archive)
        merge_new_to_archive(new, archive)
        review = os.path.join(tmp, "dedupe_review.json")

        apply_dedupe_review(review, archive, keep="published")

        entry = _read(archive)["AI Agents"][0]
        assert entry["venue"] == "JAMIA", "existing journal version must survive"
        assert not os.path.exists(review)


def test_apply_dedupe_keep_both_appends():
    with tempfile.TemporaryDirectory() as tmp:
        new, archive = _setup(tmp, PUBLISHED)
        merge_new_to_archive(new, archive)
        review = os.path.join(tmp, "dedupe_review.json")

        apply_dedupe_review(review, archive, keep="both")

        papers = _read(archive)["AI Agents"]
        assert len(papers) == 2
        assert {p["doi"] for p in papers} == {"10.48550/arXiv.2505.23055", "10.1093/jamia/ocaa123"}


def test_apply_dedupe_keep_newer_uses_year():
    with tempfile.TemporaryDirectory() as tmp:
        new, archive = _setup(tmp, PUBLISHED)  # 2025-08 newer than archive 2025-05
        merge_new_to_archive(new, archive)
        review = os.path.join(tmp, "dedupe_review.json")

        apply_dedupe_review(review, archive, keep="newer")

        entry = _read(archive)["AI Agents"][0]
        assert entry["year"] == "2025-08"
        assert entry["venue"] == "JAMIA"


def test_cli_update_and_dedupe_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        new, archive = _setup(tmp, {**PUBLISHED, "AI Agents": PUBLISHED["AI Agents"] + UNRELATED["AI Agents"]})
        result = subprocess.run(
            [sys.executable, "-m", "awescholar.cli", "updater", "update",
             "--direction", "new2old", "--input", new, "--archive", archive],
            capture_output=True, text=True, check=False, cwd=tmp,
        )
        assert result.returncode == 0, result.stderr
        assert "1 added" in result.stdout and "1 possible duplicates held back" in result.stdout

        review = os.path.join(tmp, "dedupe_review.json")
        result = subprocess.run(
            [sys.executable, "-m", "awescholar.cli", "updater", "dedupe",
             "--review", review, "--archive", archive, "--keep", "newer"],
            capture_output=True, text=True, check=False, cwd=tmp,
        )
        assert result.returncode == 0, result.stderr
        papers = _read(archive)["AI Agents"]
        assert len(papers) == 2, "unrelated paper + resolved duplicate"
        assert not os.path.exists(review)


# ── the retitled pair: roster overlap carries a weak title ─────

_DXD_ROSTER = ["Shicheng Xu", "Xin Huang", "Zihao Wei", "Liang Pang",
               "Huawei Shen", "Xueqi Cheng"]

RETTITLED_ARCHIVE = {
    "AI Agents": [
        {
            "year": "2025.08",
            "title": "Reverse Physician-AI Relationship: Full-process Clinical "
                     "Diagnosis Driven by a Large Language Model",
            "team": "Xueqi Cheng", "authors": _DXD_ROSTER,
            "doi": "10.48550/arXiv.2508.10492", "venue": "arXiv",
        }
    ]
}

RETTITLED_PUBLISHED = {
    "AI Agents": [
        {
            "year": "2026.04",
            "title": "DxDirector: an agentic large language model driving the "
                     "full-process clinical diagnosis",
            "team": "Xueqi Cheng", "authors": _DXD_ROSTER,
            "doi": "10.1038/s41467-026-71928-5", "venue": "Nature Communications",
        }
    ]
}


def test_rettitled_pair_held_back_by_roster_overlap():
    """A journal that renames the work breaks every title threshold; the
    surviving author roster must still hold the pair for review instead of
    blindly appending a duplicate."""
    with tempfile.TemporaryDirectory() as tmp:
        new, archive = _setup(tmp, RETTITLED_PUBLISHED, RETTITLED_ARCHIVE)
        merge_new_to_archive(new, archive)
        review = _read(os.path.join(tmp, "dedupe_review.json"))
        assert len(review) == 1
        assert review[0]["title_similarity"] < 0.80  # the old gate missed this
        assert review[0]["shared_authors"] >= 0.8
        assert len(_read(archive)["AI Agents"]) == 1  # nothing appended


def test_weak_title_with_thin_roster_merges_normally():
    """Single-author records cannot trust surname overlap — a weak title with
    no roster evidence still merges as a new paper."""
    thin = {
        "AI Agents": [{
            "year": "2026.01", "title": "DxDirector: an agentic clinical model",
            "team": "S. Solo", "authors": ["S. Solo"],
            "doi": "10.1038/thin", "venue": "Nature Communications",
        }]
    }
    with tempfile.TemporaryDirectory() as tmp:
        new, archive = _setup(tmp, thin, RETTITLED_ARCHIVE)
        merge_new_to_archive(new, archive)
        assert len(_read(archive)["AI Agents"]) == 2
        assert not os.path.exists(os.path.join(tmp, "dedupe_review.json"))


# ── codeUrl collision hold-back ────────────────────────────────

def test_code_collision_holds_back_retitled_published_version(tmp_path):
    """A retitled published version pointing at the same official repo as an
    archived preprint is held back with a codeUrl_collision marker — the
    signal that survives title rewrites."""
    archive = tmp_path / "data.json"
    archive.write_text(json.dumps({
        "AI Agents": [{
            "year": "2025.06", "title": "Agentomics-ML: Autonomous Machine Learning",
            "doi": "10.48550/arXiv.2506.05542", "venue": "arXiv",
            "codeUrl": "https://github.com/BioGeMT/agentomics-ml",
        }],
    }))
    incoming = tmp_path / "new.json"
    incoming.write_text(json.dumps({
        "AI Agents": [{
            "year": "2026.01",
            "title": "Agentomics: an agentic system for biomedical machine learning tasks",
            "doi": "10.1093/bioinformatics/btag250", "venue": "Bioinformatics",
            "codeUrl": "https://github.com/BioGeMT/agentomics-ml",
        }],
    }))

    merge_new_to_archive(str(incoming), str(archive))

    merged = json.loads(archive.read_text())
    assert len(merged["AI Agents"]) == 1, "collision held back, not appended"
    review = tmp_path / "dedupe_review.json"
    assert review.exists()
    item = json.loads(review.read_text())[0]
    assert item["codeUrl_collision"] == "https://github.com/BioGeMT/agentomics-ml"


def test_code_collision_not_flagged_without_dedupe(tmp_path):
    archive = tmp_path / "data.json"
    archive.write_text(json.dumps({
        "AI Agents": [{"year": "2025", "title": "A", "codeUrl": "https://github.com/o/r"}],
    }))
    incoming = tmp_path / "new.json"
    incoming.write_text(json.dumps({
        "AI Agents": [{"year": "2026", "title": "B", "codeUrl": "https://github.com/o/r"}],
    }))

    merge_new_to_archive(str(incoming), str(archive), dedupe=False)

    merged = json.loads(archive.read_text())
    assert len(merged["AI Agents"]) == 2
    assert not (tmp_path / "dedupe_review.json").exists()
