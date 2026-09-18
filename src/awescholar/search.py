"""Semantic Scholar paper search with database persistence."""

import json
import sys

from semanticscholar import SemanticScholar

from .config import ss_env_api_key, warn_missing_ss_key
from .db import Paper, get_session
from .pubmed import search_pubmed
from .utils import retry_with_backoff


def search_papers(
    query: str,
    db_path: str = "output",
    api_key: str | None = None,
    limit: int = 100,
    fields_of_study: list[str] | None = None,
    publication_date_or_year: str | None = None,
    fields: list[str] | None = None,
    pubmed: bool = False,
) -> list[dict]:
    """Search Semantic Scholar and optionally PubMed, then persist to SQLite.

    Args:
        fields_of_study: Filter by field. Valid values (case-sensitive):
            Computer Science, Medicine, Chemistry, Biology, Materials Science,
            Physics, Geology, Psychology, Art, History, Geography, Sociology,
            Business, Political Science, Economics, Philosophy, Mathematics,
            Engineering, Environmental Science, Agricultural and Food Sciences,
            Education, Linguistics, Law.

    Returns list of paper dicts with doi, title, journal, etc.
    """
    if fields is None:
        fields = [
            "paperId", "externalIds", "url", "title", "abstract", "venue",
            "publicationVenue", "publicationTypes", "publicationDate", "journal",
            "authors", "citationCount", "influentialCitationCount",
            "fieldsOfStudy", "isOpenAccess", "openAccessPdf", "tldr",
        ]

    api_key = api_key or ss_env_api_key()
    if not api_key:
        warn_missing_ss_key()
    sch = SemanticScholar(api_key=api_key) if api_key else SemanticScholar()

    s2_error = None
    try:
        results = retry_with_backoff(
            sch.search_paper,
            query,
            fields=fields,
            fields_of_study=fields_of_study,
            publication_date_or_year=publication_date_or_year,
            limit=limit,
        )
    except Exception as e:
        if not pubmed:
            msg = str(e)
            if "403" in msg or "Forbidden" in msg:
                raise RuntimeError("Semantic Scholar API 403. Check your API key.") from e
            if "429" in msg:
                raise RuntimeError("Semantic Scholar rate limit (429). Wait and retry.") from e
            raise
        results = []
        s2_error = e

    if not results:
        paper_items = []
    else:
        paper_items = results.items if hasattr(results, "items") else results

    pubmed_items = []
    if pubmed:
        try:
            pubmed_items = search_pubmed(query, limit=limit)
        except Exception as exc:  # noqa: BLE001 — optional source must not block S2
            print(f"Warning: PubMed search failed: {exc}", file=sys.stderr)

    if s2_error:
        print(f"Warning: Semantic Scholar search failed; using PubMed only: {s2_error}", file=sys.stderr)

    # Post-validate fields_of_study (SS API filter is not strict)
    if fields_of_study:
        paper_items = [
            p for p in paper_items
            if p.fieldsOfStudy and any(f in p.fieldsOfStudy for f in fields_of_study)
        ]

    # Fetch affiliations for last authors
    author_ids = []
    for p in paper_items:
        if p.authors and p.authors[-1].authorId:
            author_ids.append(p.authors[-1].authorId)

    author_map = {}
    if author_ids:
        try:
            authors_data = sch.get_authors(author_ids, fields=["name", "affiliations"])
            author_map = {a.authorId: a for a in authors_data}
        except Exception as e:  # noqa: BLE001 — author details are optional enrichment
            print(f"Warning: could not fetch author details: {e}", file=sys.stderr)

    session = get_session(db_path)
    saved = []

    try:
        for paper in paper_items:
            ext_ids = getattr(paper, "externalIds", None)
            if not ext_ids or not ext_ids.get("DOI"):
                continue
            if not paper.authors:
                continue

            doi = ext_ids["DOI"]
            existing = session.query(Paper).filter_by(doi=doi).first()
            if existing:
                saved.append(_paper_to_dict(existing))
                continue

            last_author = paper.authors[-1]
            author_detail = author_map.get(last_author.authorId)
            team_name = (author_detail.name if author_detail else None) or last_author.name or ""
            affiliations = list(author_detail.affiliations or []) if author_detail else []

            db_paper = Paper(
                paper_id=paper.paperId,
                doi=doi,
                title=paper.title,
                abstract=getattr(paper, "abstract", None),
                authors=json.dumps({
                    "name": team_name,
                    "affiliations": affiliations,
                    "all": [a.name for a in paper.authors if a.name],
                }),
                year=getattr(paper, "year", None),
                venue=getattr(paper, "venue", None),
                journal=paper.journal.name if paper.journal else None,
                url=getattr(paper, "url", None),
                publication_types=",".join(paper.publicationTypes) if paper.publicationTypes else None,
                publication_date=getattr(paper, "publicationDate", None),
                fields_of_study=",".join(paper.fieldsOfStudy) if paper.fieldsOfStudy else None,
                citation_count=getattr(paper, "citationCount", None),
                is_open_access=getattr(paper, "isOpenAccess", None),
                open_access_pdf=str(getattr(paper, "openAccessPdf", None)),
            )
            session.add(db_paper)
            saved.append(_paper_to_dict(db_paper))

        for paper in pubmed_items:
            doi = paper["doi"]
            if session.query(Paper).filter_by(doi=doi).first():
                continue
            authors = paper.get("authors") or []
            if not authors:
                continue
            db_paper = Paper(
                paper_id=f"pubmed:{paper.get('pmid') or doi}",
                doi=doi,
                title=paper.get("title") or "",
                abstract=paper.get("abstract") or None,
                authors=json.dumps({"name": authors[-1], "affiliations": [], "all": authors}),
                year=paper.get("year") or None,
                venue=paper.get("venue") or None,
                journal=paper.get("journal") or None,
                url=paper.get("url") or None,
                publication_types=paper.get("publication_types") or None,
                publication_date=paper.get("publication_date") or None,
                fields_of_study=paper.get("fields_of_study") or None,
                citation_count=None,
                is_open_access=None,
                open_access_pdf=None,
            )
            session.add(db_paper)
            saved.append(_paper_to_dict(db_paper))

        session.commit()
    finally:
        session.close()

    return saved


def _paper_to_dict(p: Paper) -> dict:
    return {
        "doi": p.doi,
        "title": p.title,
        "abstract": p.abstract,
        "authors": p.authors,
        "year": p.year,
        "venue": p.venue,
        "journal": p.journal,
        "url": p.url,
        "publication_types": p.publication_types,
        "publication_date": p.publication_date,
        "fields_of_study": p.fields_of_study,
        "citation_count": p.citation_count,
    }
