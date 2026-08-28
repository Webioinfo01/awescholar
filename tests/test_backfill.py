"""Tests for backfill.py — affiliation/team backfill from Semantic Scholar."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from awescholar.backfill import backfill_affiliations


def _write_archive(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_archive(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class FakeAuthorRef:
    def __init__(self, author_id, name):
        self.authorId = author_id
        self.name = name


class FakeAuthorDetail:
    def __init__(self, author_id, name, affiliations):
        self.authorId = author_id
        self.name = name
        self.affiliations = affiliations


class FakePaper:
    def __init__(self, doi, authors):
        self.externalIds = {"DOI": doi}
        self.authors = authors


def _patch_scholar(papers, author_details):
    """Patch SemanticScholar in backfill with a client serving the fixtures."""
    client = MagicMock()

    def get_papers(ids, fields=None, **kwargs):
        wanted = {i.removeprefix("DOI:") for i in ids}
        return [p for p in papers if p.externalIds["DOI"] in wanted]

    def get_authors(ids, fields=None, **kwargs):
        return [author_details[i] for i in ids if i in author_details]

    client.get_papers.side_effect = get_papers
    client.get_authors.side_effect = get_authors
    return patch("awescholar.backfill.SemanticScholar", return_value=client)


def test_backfill_fills_empty_affiliation_and_team():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        _write_archive(archive, {
            "AI Agents": [{"doi": "10.1/a", "title": "Paper A", "team": "", "affiliation": ""}]
        })
        papers = [FakePaper("10.1/a", [FakeAuthorRef("A1", "First"), FakeAuthorRef("A2", "Qi Liu")])]
        details = {"A2": FakeAuthorDetail("A2", "Qi Liu", ["Stanford University"])}
        with _patch_scholar(papers, details):
            stats = backfill_affiliations(archive, no_backup=True)

        entry = _read_archive(archive)["AI Agents"][0]
        assert entry["team"] == "Qi Liu"
        assert entry["affiliation"] == "Stanford University"
        assert stats["filled_affiliations"] == 1
        assert stats["filled_teams"] == 1


def test_backfill_never_overwrites_existing_values():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        _write_archive(archive, {
            "AI Agents": [{
                "doi": "10.1/a", "title": "Paper A",
                "team": "Human Curator", "affiliation": "MIT",
            }]
        })
        papers = [FakePaper("10.1/a", [FakeAuthorRef("A1", "Someone Else")])]
        details = {"A1": FakeAuthorDetail("A1", "Someone Else", ["Stanford University"])}
        with _patch_scholar(papers, details):
            backfill_affiliations(archive, no_backup=True)

        entry = _read_archive(archive)["AI Agents"][0]
        assert entry["team"] == "Human Curator"
        assert entry["affiliation"] == "MIT"


def test_backfill_reuses_trusted_team_name_from_other_entries():
    """The fetched last author is already recorded (with a curated name) in
    another entry — reuse that name instead of the fetched form, and take the
    affiliation from that same author."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        _write_archive(archive, {
            "AI Agents": [
                {"doi": "10.1/old", "title": "Old Paper", "team": "Qi Liu",
                 "affiliation": "Princeton University"},
                {"doi": "10.1/new", "title": "New Paper", "team": "", "affiliation": ""},
            ]
        })
        papers = [
            FakePaper("10.1/old", [FakeAuthorRef("A1", "Ignored")]),
            # last author "QI LIU" normalizes equal to the trusted "Qi Liu";
            # second author "liu qi" is a different-looking name that must NOT match
            FakePaper("10.1/new", [FakeAuthorRef("A2", "liu qi"), FakeAuthorRef("A3", "QI LIU")]),
        ]
        details = {
            "A3": FakeAuthorDetail("A3", "Q. Liu", ["Broad Institute"]),
            "A2": FakeAuthorDetail("A2", "Qi Liu", ["Harvard"]),
        }
        with _patch_scholar(papers, details):
            stats = backfill_affiliations(archive, no_backup=True)

        entry = _read_archive(archive)["AI Agents"][1]
        assert entry["team"] == "Qi Liu"
        assert entry["affiliation"] == "Broad Institute"
        assert stats["reused_trusted"] == 1


def test_backfill_falls_back_to_second_author_trusted_match():
    """No last-author match: a trusted match on the second-to-last author wins,
    and the affiliation follows that person, not the last author."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        _write_archive(archive, {
            "Reviews": [
                {"doi": "10.1/known", "title": "Known", "team": "Jane Roe", "affiliation": "MIT"},
                {"doi": "10.1/target", "title": "Target", "team": "", "affiliation": ""},
            ]
        })
        papers = [
            FakePaper("10.1/known", [FakeAuthorRef("B1", "Jane Roe")]),
            FakePaper("10.1/target", [FakeAuthorRef("B2", "Jane Roe"), FakeAuthorRef("B3", "Nobody")]),
        ]
        details = {
            "B2": FakeAuthorDetail("B2", "Jane Roe", ["ETH Zurich"]),
            "B3": FakeAuthorDetail("B3", "Nobody", ["Nowhere College"]),
        }
        with _patch_scholar(papers, details):
            backfill_affiliations(archive, no_backup=True)

        entry = _read_archive(archive)["Reviews"][1]
        assert entry["team"] == "Jane Roe"
        assert entry["affiliation"] == "ETH Zurich"


def test_backfill_skips_entries_without_doi():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        _write_archive(archive, {
            "AI Agents": [{"title": "No DOI Paper", "team": "", "affiliation": ""}]
        })
        with _patch_scholar([], {}):
            stats = backfill_affiliations(archive, no_backup=True)

        assert stats["candidates"] == 0
        entry = _read_archive(archive)["AI Agents"][0]
        assert entry["team"] == ""
        assert entry["affiliation"] == ""


def test_backfill_handles_missing_paper_and_author_data():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        _write_archive(archive, {
            "AI Agents": [
                {"doi": "10.1/gone", "title": "Not On SS", "team": "", "affiliation": ""},
                {"doi": "10.1/bare", "title": "Author Without Data", "team": "", "affiliation": ""},
            ]
        })
        papers = [
            FakePaper("10.1/bare", [FakeAuthorRef("C1", "Anonymous")]),
            # 10.1/gone is absent from the fixtures — simulates SS 404
        ]
        with _patch_scholar(papers, {}):
            stats = backfill_affiliations(archive, no_backup=True)

        data = _read_archive(archive)
        assert data["AI Agents"][0]["team"] == ""       # missing paper untouched
        assert data["AI Agents"][1]["team"] == "Anonymous"  # name from paper list
        assert data["AI Agents"][1]["affiliation"] == ""    # no affiliation data available
        assert stats["papers_missing"] == 1
        assert stats["authors_missing"] == 1


def test_backfill_creates_backup_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "data.json")
        _write_archive(archive, {
            "AI Agents": [{"doi": "10.1/a", "title": "Paper A", "team": "", "affiliation": ""}]
        })
        papers = [FakePaper("10.1/a", [FakeAuthorRef("A1", "Qi Liu")])]
        details = {"A1": FakeAuthorDetail("A1", "Qi Liu", ["Stanford University"])}
        with _patch_scholar(papers, details):
            backfill_affiliations(archive)

        backups = [f for f in os.listdir(tmp) if f.startswith("data.json.") and f.endswith(".bak")]
        assert len(backups) == 1
