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
