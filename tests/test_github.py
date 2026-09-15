"""Tests for github.py — URL parsing, arXiv extraction, API helpers."""

from awescholar import github


def test_owner_repo_from_url():
    assert github.owner_repo_from_url("https://github.com/owner/repo") == "owner/repo"
    assert github.owner_repo_from_url("https://github.com/owner/repo.git") == "owner/repo"
    assert github.owner_repo_from_url("https://github.com/owner/repo/tree/main") == "owner/repo"
    assert github.owner_repo_from_url("https://gitlab.com/owner/repo") is None
    assert github.owner_repo_from_url("") is None
    assert github.owner_repo_from_url(None) is None


def test_arxiv_id_from_paper():
    assert github.arxiv_id_from_paper(
        {"paperUrl": "https://arxiv.org/abs/2501.04227"}) == "2501.04227"
    assert github.arxiv_id_from_paper(
        {"paperUrl": "https://arxiv.org/pdf/2501.04227v2"}) == "2501.04227"
    assert github.arxiv_id_from_paper({"doi": "10.48550/arXiv.2501.04227"}) == "2501.04227"
    assert github.arxiv_id_from_paper({"paperUrl": "https://nature.com/x", "doi": "10.1/x"}) == ""


def test_stars_from_repo():
    assert github.stars_from_repo({"stargazers_count": 42}) == 42
    assert github.stars_from_repo(None) == 0
    assert github.stars_from_repo({}) == 0


def test_search_repositories_parses_items(monkeypatch):
    captured = {}

    def fake_get(path, token, timeout):
        captured["path"] = path
        return {"items": [{"full_name": "a/b"}]}

    monkeypatch.setattr(github, "_api_get", fake_get)
    result = github.search_repositories("anything", token=None, per_page=5)
    assert result == [{"full_name": "a/b"}]
    assert "search/repositories" in captured["path"]


def test_search_repositories_returns_empty_on_failure(monkeypatch):
    monkeypatch.setattr(github, "_api_get", lambda path, token, timeout: None)
    assert github.search_repositories("anything", token=None) == []


def test_fetch_repo_returns_none_on_missing(monkeypatch):
    monkeypatch.setattr(github, "_api_get", lambda path, token, timeout: None)
    assert github.fetch_repo("ghost/repo", token=None) is None
