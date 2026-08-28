"""Tests for db.py — SQLAlchemy ORM."""

import tempfile

from sqlalchemy.exc import IntegrityError

from awescholar.db import Paper, get_session


def test_create_session_and_table():
    with tempfile.TemporaryDirectory() as tmp:
        session = get_session(tmp)
        assert session.query(Paper).count() == 0
        session.close()


def test_insert_and_query_paper():
    with tempfile.TemporaryDirectory() as tmp:
        session = get_session(tmp)
        paper = Paper(
            paper_id="abc123",
            doi="10.1234/test",
            title="Test Paper",
            abstract="A test abstract",
            year=2025,
        )
        session.add(paper)
        session.commit()

        result = session.query(Paper).filter_by(doi="10.1234/test").first()
        assert result is not None
        assert result.title == "Test Paper"
        assert result.year == 2025
        session.close()


def test_doi_uniqueness():
    with tempfile.TemporaryDirectory() as tmp:
        session = get_session(tmp)
        session.add(Paper(paper_id="p1", doi="10.1/a", title="First"))
        session.commit()

        session.add(Paper(paper_id="p2", doi="10.1/a", title="Duplicate"))
        try:
            session.commit()
            assert False, "Should have raised integrity error"
        except IntegrityError:
            session.rollback()
        session.close()
