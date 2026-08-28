"""Tests for schemas.py — project schema contracts."""

from awescholar.schemas import AnnotationResult, FilteredPaper, FilterResult, PaperAnnotation


def test_annotation_result_contract():
    result = AnnotationResult(
        paper_list=[
            PaperAnnotation(doi="10.1/a", domain="Bio", category="Genomics"),
            PaperAnnotation(doi="10.1/b", domain="Chem", category="Drug"),
        ],
        category_list=["Genomics", "Drug"],
    )
    assert len(result.paper_list) == 2
    assert result.category_list == ["Genomics", "Drug"]


def test_filter_result_contract_includes_default_venue():
    result = FilterResult(papers={
        "Genomics": [FilteredPaper(doi="10.1/a", title="A", reason="Relevant")],
        "Drug": [FilteredPaper(doi="10.1/b", title="B", reason="High quality")],
    })
    assert len(result.papers) == 2
    assert result.papers["Genomics"][0].doi == "10.1/a"
    assert result.papers["Genomics"][0].venue == ""
