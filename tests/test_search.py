"""Tests for Semantic Scholar search persistence."""

import json

from awescholar import search


class FakeAuthorRef:
    """Author entry embedded in search results (name + id only)."""

    def __init__(self, author_id, name):
        self.authorId = author_id
        self.name = name


class FakeAuthorDetail:
    """Author object returned by get_authors — attribute access, not subscriptable."""

    def __init__(self, author_id, name, affiliations):
        self.authorId = author_id
        self.name = name
        self.affiliations = affiliations


class FakePaper:
    def __init__(self, **kwargs):
        self.paperId = kwargs.get("paper_id", "pid-1")
        self.externalIds = {"DOI": kwargs.get("doi", "10.1/a")}
        self.title = kwargs.get("title", "Paper A")
        self.abstract = kwargs.get("abstract", "An abstract")
        self.authors = kwargs.get("authors", [])
        self.year = kwargs.get("year", 2025)
        self.venue = kwargs.get("venue", "TestConf")
        self.journal = None
        self.url = "https://example.com"
        self.publicationTypes = None
        self.publicationDate = "2025-06-01"
        self.fieldsOfStudy = kwargs.get("fields_of_study", ["Biology"])
        self.citationCount = 0
        self.isOpenAccess = False
        self.openAccessPdf = None


class FakeScholar:
    def __init__(self, papers, author_details):
        self._papers = papers
        self._author_details = author_details

    def search_paper(self, query, fields=None, fields_of_study=None,
                     publication_date_or_year=None, limit=None):
        return type("Results", (), {"items": self._papers})()

    def get_authors(self, author_ids, fields=None):
        return [self._author_details[i] for i in author_ids if i in self._author_details]


def _install(monkeypatch, papers, author_details):
    fake = FakeScholar(papers, author_details)
    monkeypatch.setattr(search, "SemanticScholar", lambda api_key=None: fake)


def test_search_papers_stores_author_affiliations(tmp_path, monkeypatch):
    paper = FakePaper(
        doi="10.1/a",
        title="Paper A",
        authors=[FakeAuthorRef("A1", "First Author"), FakeAuthorRef("A2", "Yutaka Saito")],
    )
    details = {"A2": FakeAuthorDetail("A2", "Yutaka Saito", ["The University of Tokyo"])}
    _install(monkeypatch, [paper], details)

    saved = search.search_papers("query", db_path=str(tmp_path))

    assert len(saved) == 1
    stored = json.loads(saved[0]["authors"])
    assert stored["name"] == "Yutaka Saito"
    assert stored["affiliations"] == ["The University of Tokyo"]


def test_search_papers_falls_back_to_author_name_without_details(tmp_path, monkeypatch):
    paper = FakePaper(
        doi="10.1/b",
        title="Paper B",
        authors=[FakeAuthorRef("A1", "Solo Author")],
    )
    _install(monkeypatch, [paper], {})

    saved = search.search_papers("query", db_path=str(tmp_path))

    assert len(saved) == 1
    stored = json.loads(saved[0]["authors"])
    assert stored["name"] == "Solo Author"
    assert stored["affiliations"] == []


def test_search_papers_skips_papers_without_doi(tmp_path, monkeypatch):
    paper = FakePaper(
        doi="10.1/c",
        title="With DOI",
        authors=[FakeAuthorRef("A1", "Author")],
    )
    no_doi = FakePaper(title="No DOI", authors=[FakeAuthorRef("A2", "Author")])
    no_doi.externalIds = {}
    _install(monkeypatch, [no_doi, paper], {})

    saved = search.search_papers("query", db_path=str(tmp_path))

    assert [p["doi"] for p in saved] == ["10.1/c"]
