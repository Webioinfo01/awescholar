"""Tests for downloader.py — open-access PDF download."""

import json
from argparse import Namespace

from awescholar import downloader as dl

ARXIV_PDF = b"%PDF-1.7 fake arXiv bytes"
PUB_PDF = b"%PDF-1.4 fake publisher bytes"


class _FakeResponse:
    def __init__(self, data):
        self._data = data
        self._served = False

    def read(self, n=None):
        if self._served:
            return b""
        self._served = True
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _patch_urls(monkeypatch, url_map, hits=None):
    """Route urlopen by URL prefix. Values are bytes, JSON bytes, or Exception."""
    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if hits is not None:
            hits.append(url)
        for prefix, data in url_map.items():
            if url.startswith(prefix):
                if isinstance(data, Exception):
                    raise data
                return _FakeResponse(data)
        raise AssertionError(f"unexpected URL fetched: {url}")

    monkeypatch.setattr(dl.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(dl, "ARXIV_PAUSE_SECONDS", 0)
    monkeypatch.setattr(dl, "PUBLISHER_PAUSE_SECONDS", 0)
    monkeypatch.setattr(dl, "OPENALEX_PAUSE_SECONDS", 0)


def _openalex_json(doi, pdf_url, title, year):
    return json.dumps({
        "results": [{
            "doi": f"https://doi.org/{doi}",
            "best_oa_location": {"pdf_url": pdf_url},
            "display_name": title,
            "publication_year": year,
        }],
    }).encode()


def _write_archive(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_arxiv_doi_record_downloads_directly(tmp_path, monkeypatch):
    archive = tmp_path / "data.json"
    _write_archive(archive, {"AI Agents": [{
        "title": "Benchmark Radar", "year": "2026.09",
        "doi": "10.48550/arXiv.2609.11115",
    }]})
    _patch_urls(monkeypatch, {"https://arxiv.org/pdf/2609.11115": ARXIV_PDF})

    before = archive.read_bytes()
    stats = dl.download_pdfs(archive_path=str(archive), out_dir=str(tmp_path / "pdfs"))

    assert stats == {"candidates": 1, "downloaded": 1, "skipped_existing": 0,
                     "no_source": 0, "failed": 0}
    assert (tmp_path / "pdfs" / "2026-benchmark-radar.pdf").read_bytes() == ARXIV_PDF
    assert archive.read_bytes() == before  # the archive is never modified


def test_arxiv_paperurl_is_detected(tmp_path, monkeypatch):
    archive = tmp_path / "data.json"
    _write_archive(archive, {"Reviews": [{
        "title": "Aging LLMs", "paperUrl": "https://arxiv.org/abs/2501.04227v2",
    }]})
    _patch_urls(monkeypatch, {"https://arxiv.org/pdf/2501.04227": ARXIV_PDF})

    stats = dl.download_pdfs(archive_path=str(archive), out_dir=str(tmp_path))
    assert stats["downloaded"] == 1


def test_plain_doi_resolved_via_openalex(tmp_path, monkeypatch):
    archive = tmp_path / "data.json"
    _write_archive(archive, {"Reviews": [{
        "title": "Known Title", "doi": "10.1038/xyz",
    }]})
    _patch_urls(monkeypatch, {
        "https://api.openalex.org/works": _openalex_json(
            "10.1038/xyz", "https://pub.example/paper.pdf", "OpenAlex Title", 2025),
        "https://pub.example/paper.pdf": PUB_PDF,
    })

    stats = dl.download_pdfs(archive_path=str(archive), out_dir=str(tmp_path))
    assert stats["downloaded"] == 1
    # archive title wins for naming; OpenAlex fills the missing year
    assert (tmp_path / "2025-known-title.pdf").exists()


def test_direct_doi_gets_name_from_openalex(tmp_path, monkeypatch):
    _patch_urls(monkeypatch, {
        "https://api.openalex.org/works": _openalex_json(
            "10.1038/xyz", "https://pub.example/p.pdf", "Standalone Paper", 2024),
        "https://pub.example/p.pdf": PUB_PDF,
    })

    stats = dl.download_pdfs(dois=["10.1038/xyz"], out_dir=str(tmp_path))
    assert stats["downloaded"] == 1
    assert (tmp_path / "2024-standalone-paper.pdf").exists()


def test_direct_arxiv_doi_skips_lookup(tmp_path, monkeypatch):
    hits = []
    _patch_urls(monkeypatch, {"https://arxiv.org/pdf/2609.11115": ARXIV_PDF}, hits)

    stats = dl.download_pdfs(dois=["10.48550/arXiv.2609.11115"], out_dir=str(tmp_path))
    assert stats["downloaded"] == 1
    assert (tmp_path / "arxiv-2609.11115.pdf").exists()
    assert not any("openalex" in u for u in hits)  # arXiv DOI resolves without OpenAlex


def test_html_response_fails_without_writing(tmp_path, monkeypatch):
    archive = tmp_path / "data.json"
    _write_archive(archive, {"Reviews": [{
        "title": "Bot Gated", "doi": "10.1016/j.cell.2026.08.026",
        "paperUrl": "https://doi.org/10.1016/j.cell.2026.08.026",
    }]})
    _patch_urls(monkeypatch, {
        "https://api.openalex.org/works": _openalex_json(
            "10.1016/j.cell.2026.08.026", "https://www.cell.com/fake.pdf", "Bot Gated", 2026),
        "https://www.cell.com/fake.pdf": b"<html>request blocked</html>",
    })

    stats = dl.download_pdfs(archive_path=str(archive), out_dir=str(tmp_path / "pdfs"))
    assert stats["failed"] == 1 and stats["downloaded"] == 0
    assert not (tmp_path / "pdfs" / "bot-gated.pdf").exists()


def test_existing_file_skipped_until_force(tmp_path, monkeypatch):
    archive = tmp_path / "data.json"
    _write_archive(archive, {"Reviews": [{
        "title": "Benchmark Radar", "doi": "10.48550/arXiv.2609.11115",
    }]})
    target = tmp_path / "benchmark-radar.pdf"
    target.write_bytes(b"old copy")
    _patch_urls(monkeypatch, {"https://arxiv.org/pdf/2609.11115": ARXIV_PDF})

    stats = dl.download_pdfs(archive_path=str(archive), out_dir=str(tmp_path))
    assert stats["skipped_existing"] == 1 and stats["downloaded"] == 0
    assert target.read_bytes() == b"old copy"

    stats = dl.download_pdfs(archive_path=str(archive), out_dir=str(tmp_path), force=True)
    assert stats["downloaded"] == 1
    assert target.read_bytes() == ARXIV_PDF


def test_only_scopes_candidates(tmp_path, monkeypatch):
    archive = tmp_path / "data.json"
    _write_archive(archive, {"Reviews": [
        {"title": "Alpha Paper", "doi": "10.48550/arXiv.2501.00001"},
        {"title": "Beta Paper", "doi": "10.48550/arXiv.2501.00002"},
    ]})
    _patch_urls(monkeypatch, {"https://arxiv.org/pdf/2501.00002": ARXIV_PDF})

    stats = dl.download_pdfs(archive_path=str(archive), out_dir=str(tmp_path),
                             only=["Beta"])
    assert stats["candidates"] == 1 and stats["downloaded"] == 1
    assert (tmp_path / "beta-paper.pdf").exists()
    assert not (tmp_path / "alpha-paper.pdf").exists()


def test_entry_without_any_source_is_reported(tmp_path, monkeypatch):
    archive = tmp_path / "data.json"
    _write_archive(archive, {"Reviews": [{"title": "No Links Paper"}]})
    _patch_urls(monkeypatch, {})

    stats = dl.download_pdfs(archive_path=str(archive), out_dir=str(tmp_path))
    assert stats["no_source"] == 1 and stats["candidates"] == 1


def test_openalex_without_pdf_url_is_no_source(tmp_path, monkeypatch):
    archive = tmp_path / "data.json"
    _write_archive(archive, {"Reviews": [{"title": "Closed Paper", "doi": "10.1/closed"}]})
    _patch_urls(monkeypatch, {
        "https://api.openalex.org/works": _openalex_json("10.1/closed", None, "Closed Paper", 2026),
    })

    stats = dl.download_pdfs(archive_path=str(archive), out_dir=str(tmp_path))
    assert stats["no_source"] == 1 and stats["failed"] == 0


def test_slug_collision_disambiguates_by_doi(tmp_path, monkeypatch):
    archive = tmp_path / "data.json"
    _write_archive(archive, {"Reviews": [
        {"title": "Same Name", "doi": "10.48550/arXiv.2501.00001"},
        {"title": "Same Name", "doi": "10.48550/arXiv.2501.00002"},
    ]})
    _patch_urls(monkeypatch, {
        "https://arxiv.org/pdf/2501.00001": ARXIV_PDF,
        "https://arxiv.org/pdf/2501.00002": ARXIV_PDF,
    })

    stats = dl.download_pdfs(archive_path=str(archive), out_dir=str(tmp_path))
    assert stats["downloaded"] == 2
    assert (tmp_path / "same-name.pdf").exists()
    assert (tmp_path / "same-name-10-48550-arxiv-2501-00002.pdf").exists()


def test_slugify_shape():
    assert dl.slugify("Hello, World! This is Fine") == "hello-world-this-is-fine"
    assert len(dl.slugify("x" * 300)) <= dl.SLUG_MAX_CHARS
    assert dl.slugify("!!!") == "untitled"


def test_cli_download_requires_a_target():
    from awescholar.cli import cmd_download
    args = Namespace(archive=None, only=None, doi=None, arxiv=None,
                     out="pdfs", force=False)
    assert cmd_download(args, {}) == 1
