"""Tests for preprint detection and the publish-scan workflow."""

import json

from awescholar.archive import is_preprint
from awescholar.publish_scan import (
    apply_review,
    find_preprints,
    publish_scan,
    scan_archive,
)


def _preprint(**over):
    p = {
        "year": "2026.01", "title": "A benchmark for AI biologists",
        "team": "J. Smith", "venue": "bioRxiv",
        "paperUrl": "https://doi.org/10.1101/2026.01.01.000001",
        "doi": "10.1101/2026.01.01.000001", "citations": 0,
    }
    p.update(over)
    return p


def _published(**over):
    p = {
        "year": "2026.06", "title": "A benchmark for AI biologists",
        "team": "J. Smith", "authors": ["Anna Smith", "John Doe", "J. Smith"],
        "venue": "Nature Methods", "paperUrl": "https://doi.org/10.1038/x",
        "doi": "10.1038/x", "citations": 7,
    }
    p.update(over)
    return p


# ── is_preprint: the non-arXiv blind spot ─────────────────────

def test_is_preprint_covers_non_arxiv_servers():
    for doi in ("10.1101/2026.01.01.1", "10.64898/2026.07.21.739769",
                "10.21203/rs.3.x", "10.20944/preprints202601.0001",
                "10.26434/chemrxiv.2026", "10.22541/au.2026.1", "10.2139/ssrn.123",
                "10.48550/arXiv.2505.1"):
        assert is_preprint({"doi": doi, "venue": ""}), doi
    for venue in ("bioRxiv", "medRxiv", "arXiv", "ArXiv.org", "ChemRxiv",
                  "Research Square", "Preprints.org", "SSRN"):
        assert is_preprint({"doi": "", "venue": venue}), venue


def test_is_preprint_passes_published_records():
    for paper in (
        {"doi": "10.1038/s41551-026-01769-6", "venue": "Nature Biomedical Engineering"},
        {"doi": "10.1038/x", "venue": ""},  # journal DOI, venue unknown
        {"doi": "", "venue": "Bioinformatics"},  # no DOI but a journal venue
    ):
        assert not is_preprint(paper), paper


# ── find_preprints ────────────────────────────────────────────

def test_find_preprints_scopes_and_preserves_order():
    archive = {
        "AI Agents": [_preprint(), {"title": "published", "venue": "Nature", "doi": "10.1/x"}],
        "Reviews": [_preprint(title="Another preprint", doi="10.1101/2", venue="bioRxiv")],
    }
    hits = find_preprints(archive)
    assert [(h["category"], h["index"]) for h in hits] == [("AI Agents", 0), ("Reviews", 0)]

    scoped = find_preprints(archive, only=["Another preprint"])
    assert [(h["category"], h["index"]) for h in scoped] == [("Reviews", 0)]


# ── scan: which records count as the published version ────────

def _fake_sch(monkeypatch, by_doi=None, by_title=None, by_crossref=None):
    monkeypatch.setattr("awescholar.publish_scan.search_by_doi", by_doi or (lambda doi, sch: None))
    monkeypatch.setattr(
        "awescholar.publish_scan._title_candidates",
        by_title or (lambda title, sch: []))
    monkeypatch.setattr(
        "awescholar.publish_scan._crossref_candidates",
        by_crossref or (lambda title: []))
    monkeypatch.setattr("awescholar.publish_scan._get_client", lambda key: object())


def test_scan_upgrades_doi_record_and_title_twin(monkeypatch, tmp_path):
    archive_path = tmp_path / "data.json"
    no_doi = _preprint(title="XunZi an AI biologist reveals targets",
                       doi="", paperUrl="")
    archive_path.write_text(json.dumps({
        "AI Agents": [_preprint(), no_doi, _preprint(doi="10.1101/still-preprint")],
    }), encoding="utf-8")

    def fake_by_doi(doi, sch):
        if doi == "10.1101/2026.01.01.000001":
            return _published(abstract="stripped before review")
        return _preprint(doi=doi)  # S2 still reports the preprint itself

    def fake_by_title(title, sch):
        if "XunZi" in title:
            return [_published(title="XunZi, an AI biologist, reveals targets",
                               doi="10.1038/y", venue="Nat Biomed Eng")]
        return []

    _fake_sch(monkeypatch, by_doi=fake_by_doi, by_title=fake_by_title)

    review = scan_archive(str(archive_path))

    assert [r["evidence"]["match"] for r in review] == ["doi", "title"]
    assert "abstract" not in review[0]["published"]
    assert review[1]["evidence"]["title_similarity"] >= 0.90
    assert len(review) == 2  # the still-preprint entry is not queued


def test_scan_title_twin_requires_similarity(monkeypatch, tmp_path):
    archive_path = tmp_path / "data.json"
    archive_path.write_text(json.dumps({
        "AI Agents": [_preprint(title="Totally different subject", doi="")],
    }), encoding="utf-8")

    _fake_sch(monkeypatch, by_title=lambda title, sch: [_published()])

    assert scan_archive(str(archive_path)) == []


def test_scan_no_title_search_flag(monkeypatch, tmp_path):
    archive_path = tmp_path / "data.json"
    archive_path.write_text(json.dumps({"AI Agents": [_preprint(doi="")]}), encoding="utf-8")

    called = []
    _fake_sch(monkeypatch, by_title=lambda title, sch: called.append(title) or [_published()])

    assert scan_archive(str(archive_path), use_title_search=False) == []
    assert called == []


# ── apply: in-place upgrade semantics ─────────────────────────

def test_apply_review_upgrades_in_place_and_preserves_curation(tmp_path):
    archive_path = tmp_path / "data.json"
    entry = {**_preprint(), "codeUrl": "https://github.com/o/r",
             "githubStars": 12, "domain": "AI biologist benchmark",
             "affiliation": "Nowhere University"}
    archive_path.write_text(json.dumps({"AI Agents": [entry]}), encoding="utf-8")

    review_path = tmp_path / "publish_review.json"
    review_path.write_text(json.dumps([{
        "category": "AI Agents", "index": 0,
        "existing": entry, "published": _published(),
        "evidence": {"match": "doi"},
    }]), encoding="utf-8")

    applied = apply_review(str(review_path), str(archive_path))

    assert [a["resolution"] for a in applied] == ["upgraded to published version"]
    upgraded = json.loads(archive_path.read_text(encoding="utf-8"))["AI Agents"][0]
    assert upgraded["venue"] == "Nature Methods"
    assert upgraded["doi"] == "10.1038/x"
    assert upgraded["paperUrl"] == "https://doi.org/10.1038/x"
    assert upgraded["citations"] == 7
    assert upgraded["authors"] == ["Anna Smith", "John Doe", "J. Smith"]
    # curation fields survive
    assert upgraded["codeUrl"] == "https://github.com/o/r"
    assert upgraded["githubStars"] == 12
    assert upgraded["domain"] == "AI biologist benchmark"
    assert upgraded["affiliation"] == "Nowhere University"
    # review file consumed, backup written
    assert not review_path.exists()
    assert list(tmp_path.glob("data.json.*.bak"))


def test_apply_review_skips_stale_index(tmp_path):
    archive_path = tmp_path / "data.json"
    archive_path.write_text(json.dumps({"AI Agents": []}), encoding="utf-8")
    review_path = tmp_path / "publish_review.json"
    review_path.write_text(json.dumps([{
        "category": "AI Agents", "index": 5,
        "existing": _preprint(), "published": _published(),
        "evidence": {"match": "doi"},
    }]), encoding="utf-8")

    applied = apply_review(str(review_path), str(archive_path), no_backup=True)
    assert "skipped" in applied[0]["resolution"]
    assert json.loads(archive_path.read_text(encoding="utf-8")) == {"AI Agents": []}


# ── orchestrator: dry run vs one-shot apply ───────────────────

def test_publish_scan_dry_run_then_one_shot_apply(monkeypatch, tmp_path, capsys):
    archive_path = tmp_path / "data.json"
    archive_path.write_text(json.dumps({"AI Agents": [_preprint()]}), encoding="utf-8")

    _fake_sch(monkeypatch, by_doi=lambda doi, sch: _published())

    review_path = tmp_path / "publish_review.json"
    stats = publish_scan(str(archive_path), review_path=str(review_path))
    assert stats["scanned"] == 1 and stats["applied"] == []
    assert review_path.exists()
    out = capsys.readouterr().out
    assert "Apply : awescholar updater publish-scan" in out
    # dry run did not touch the archive
    assert json.loads(archive_path.read_text(encoding="utf-8"))["AI Agents"][0]["venue"] == "bioRxiv"

    # one-shot apply in the same invocation
    stats = publish_scan(str(archive_path), apply=True,
                         review_path=str(tmp_path / "r2.json"), no_backup=True)
    assert len(stats["applied"]) == 1
    assert json.loads(archive_path.read_text(encoding="utf-8"))["AI Agents"][0]["venue"] == "Nature Methods"


# ── dedupe interplay: the fixed preprint check ────────────────

def test_dedupe_keep_published_now_prefers_journal_over_biorxiv():
    from awescholar.archive import _wins_incoming

    existing = _preprint()
    incoming = _published()
    assert _wins_incoming(incoming, existing, "published")
    assert not _wins_incoming(existing, incoming, "published")


def test_scan_picks_published_twin_from_candidates(monkeypatch, tmp_path):
    """Title drift means the published twin is often not the top S2 hit and
    the preprint itself can come back first — the gate must keep looking."""
    archive_path = tmp_path / "data.json"
    archive_path.write_text(json.dumps({
        "AI Agents": [_preprint(doi="", title="Accurate prediction with AlphaFold3")],
    }), encoding="utf-8")

    def by_title(title, sch):
        return [
            _preprint(title="Accurate prediction with AlphaFold3"),  # the preprint itself
            _published(title="Accurate prediction with AlphaFold 3",
                       doi="10.1038/s41586-024-07487-w", venue="Nature"),
        ]

    _fake_sch(monkeypatch, by_title=by_title)

    review = scan_archive(str(archive_path))
    assert len(review) == 1
    assert review[0]["evidence"]["match"] == "title"
    assert review[0]["published"]["doi"] == "10.1038/s41586-024-07487-w"


def test_scan_title_candidates_require_a_venue(monkeypatch, tmp_path):
    """Repost copies (ResearchHub etc.) reuse the exact title but carry no
    journal name — a title-matched upgrade must demand a venue."""
    archive_path = tmp_path / "data.json"
    archive_path.write_text(json.dumps({"AI Agents": [_preprint(doi="")]}), encoding="utf-8")

    _fake_sch(monkeypatch, by_title=lambda title, sch: [
        _published(venue="", doi="10.55277/researchhub.x"),  # repost, no venue
    ])

    assert scan_archive(str(archive_path)) == []


def test_scan_crossref_fallback_picks_the_journal_record(monkeypatch, tmp_path):
    """When S2's relevance search surfaces only citers, Crossref
    query.title candidates resolve the version of record."""
    archive_path = tmp_path / "data.json"
    archive_path.write_text(json.dumps({
        "AI Agents": [_preprint(doi="10.1101/2024.05.08.592999",
                                title="Accurate structure prediction of biomolecular interactions with AlphaFold3")],
    }), encoding="utf-8")

    # S2: no DOI hit, no usable title candidates
    by_crossref = lambda title: [
            {"year": "2026.04", "title": "Accurate structure prediction of biomolecular interactions with AlphaFold3",
             "team": "", "authors": [], "venue": "", "paperUrl": "https://doi.org/10.55277/x",
             "doi": "10.55277/researchhub.x", "citations": 1},  # repost: rejected (no venue)
            {"year": "2024.05", "title": "Accurate structure prediction of biomolecular interactions with AlphaFold 3",
             "team": "John M. Jumper", "authors": ["John M. Jumper"],
             "venue": "Nature", "paperUrl": "https://doi.org/10.1038/s41586-024-07487-w",
             "doi": "10.1038/s41586-024-07487-w", "citations": 16493},
    ]
    _fake_sch(monkeypatch, by_crossref=by_crossref)

    review = scan_archive(str(archive_path))
    assert len(review) == 1
    assert review[0]["evidence"]["match"] == "crossref-title"
    assert review[0]["published"]["venue"] == "Nature"
    assert review[0]["published"]["doi"] == "10.1038/s41586-024-07487-w"
