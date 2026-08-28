"""Tests for pipeline orchestration behavior."""

import json

import pytest

from awescholar import pipeline
from awescholar.schemas import AnnotationResult, FilteredPaper, FilterResult, PaperAnnotation


def test_run_pipeline_auto_merges_filtered_data_when_configured(tmp_path, monkeypatch):
    updater_path = tmp_path / "updater.json"
    data_json_path = tmp_path / "data.json"
    updater_path.write_text(
        json.dumps(
            {
                "Models": [
                    {
                        "doi": "10.1/new",
                        "title": "New Paper",
                        "venue": "TestConf",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    data_json_path.write_text(
        json.dumps(
            {
                "Models": [
                    {
                        "doi": "10.1/old",
                        "title": "Old Paper",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_complete(*, response_format=None, **kwargs):
        if response_format is FilterResult:
            return FilterResult(
                papers={
                    "Models": [
                        FilteredPaper(
                            doi="10.1/new",
                            title="New Paper",
                            venue="TestConf",
                            reason="Relevant",
                        )
                    ]
                }
            )
        return "# Report"

    monkeypatch.setattr(pipeline, "complete", fake_complete)

    pipeline.run_pipeline(
        query=None,
        model="openai/test-model",
        db_path=str(tmp_path),
        use_updater_json=True,
        existing_json_path=str(updater_path),
        merge_new_to_old=True,
        data_json_path=str(data_json_path),
    )

    merged = json.loads(data_json_path.read_text(encoding="utf-8"))
    assert [paper["doi"] for paper in merged["Models"]] == ["10.1/old", "10.1/new"]
    assert merged["Models"][1]["title"] == "New Paper"


def test_run_pipeline_requires_data_json_path_when_auto_merge_enabled(tmp_path):
    filtered_path = tmp_path / "updater_filter.json"
    filtered_path.write_text(json.dumps({"Models": []}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="pipeline.data_json_path is required"):
        pipeline.run_pipeline(
            query=None,
            model="openai/test-model",
            db_path=str(tmp_path),
            use_filtered_json=True,
            merge_new_to_old=True,
            data_json_path=None,
        )


def test_run_pipeline_uses_same_agent_model_prefixing_as_config(tmp_path, monkeypatch):
    filtered_path = tmp_path / "updater_filter.json"
    filtered_path.write_text(json.dumps({"Models": []}), encoding="utf-8")
    captured = {}

    def fake_run_report(*, model, **kwargs):
        captured["model"] = model
        return "# Report"

    monkeypatch.setattr(pipeline, "run_report", fake_run_report)

    pipeline.run_pipeline(
        query=None,
        model="openai/global-model",
        db_path=str(tmp_path),
        api_key="global-key",
        base_url="https://global.example",
        use_filtered_json=True,
        agent_models={
            "reporter": {
                "profile": "glm",
                "name": "glm-5.1",
            }
        },
        model_profiles={
            "glm": {
                "api_key": "profile-key",
                "base_url": "https://profile.example",
            }
        },
    )

    assert captured["model"] == "openai/glm-5.1"


def test_run_pipeline_passes_research_interests_to_full_filter_path(tmp_path, monkeypatch):
    captured = {}

    def fake_run_search(**kwargs):
        return [{"doi": "10.1/a", "title": "Paper A", "abstract": "", "venue": "TestConf"}]

    def fake_run_annotate(**kwargs):
        return {
            "Models": [
                {
                    "doi": "10.1/a",
                    "title": "Paper A",
                    "venue": "TestConf",
                }
            ]
        }

    def fake_run_filter(**kwargs):
        captured["research_interests"] = kwargs["research_interests"]
        return kwargs["structured_data"]

    def fake_run_report(**kwargs):
        return "# Report"

    monkeypatch.setattr(pipeline, "run_search", fake_run_search)
    monkeypatch.setattr(pipeline, "run_annotate", fake_run_annotate)
    monkeypatch.setattr(pipeline, "run_filter", fake_run_filter)
    monkeypatch.setattr(pipeline, "run_report", fake_run_report)

    pipeline.run_pipeline(
        query="AI agents",
        model="openai/test-model",
        db_path=str(tmp_path),
        research_interests="biology agents",
    )

    assert captured["research_interests"] == "biology agents"


def test_run_annotate_maps_llm_category_to_config_casing(monkeypatch):
    def fake_complete(**kwargs):
        return AnnotationResult(
            paper_list=[
                PaperAnnotation(
                    doi="10.1/a",
                    domain="Agents",
                    category="ai-agents",
                )
            ],
            category_list=["ai-agents"],
        )

    monkeypatch.setattr(pipeline, "complete", fake_complete)

    structured = pipeline.run_annotate(
        papers=[{"doi": "10.1/a", "title": "Paper A", "abstract": ""}],
        model="openai/test-model",
        categories=["Foundation Models", "AI Agents", "Databases"],
    )

    assert list(structured) == ["AI Agents"]
    assert structured["AI Agents"][0]["doi"] == "10.1/a"


def test_run_annotate_outputs_project_data_fields(monkeypatch):
    def fake_complete(**kwargs):
        return AnnotationResult(
            paper_list=[
                PaperAnnotation(
                    doi="10.1101/2025.05.30.656746",
                    domain="Biomedical AI agent for autonomous research workflows",
                    category="AI Agents",
                )
            ],
            category_list=["AI Agents"],
        )

    monkeypatch.setattr(pipeline, "complete", fake_complete)

    structured = pipeline.run_annotate(
        papers=[
            {
                "doi": "10.1101/2025.05.30.656746",
                "title": "Biomni: A General-Purpose Biomedical AI Agent",
                "year": "2025.06",
                "team": "Jure Leskovec",
                "team_website": "https://github.com/snap-stanford",
                "affiliation": "Stanford University",
                "venue": "bioRxiv",
                "url": "https://www.biorxiv.org/content/10.1101/2025.05.30.656746v1",
                "code_url": "https://biomni.stanford.edu/",
                "github_stars": "https://img.shields.io/github/stars/snap-stanford/biomni",
            }
        ],
        model="openai/test-model",
        categories=["AI Agents"],
    )

    paper = structured["AI Agents"][0]
    assert paper["year"] == "2025.06"
    assert paper["title"] == "Biomni: A General-Purpose Biomedical AI Agent"
    assert paper["team"] == "Jure Leskovec"
    assert paper["team website"] == "https://github.com/snap-stanford"
    assert paper["affiliation"] == "Stanford University"
    assert paper["domain"] == "Biomedical AI agent for autonomous research workflows"
    assert paper["venue"] == "bioRxiv"
    assert paper["paperUrl"] == "https://www.biorxiv.org/content/10.1101/2025.05.30.656746v1"
    assert paper["codeUrl"] == "https://biomni.stanford.edu/"
    assert paper["githubStars"] == "https://img.shields.io/github/stars/snap-stanford/biomni"
    assert paper["doi"] == "10.1101/2025.05.30.656746"


def test_run_annotate_extracts_team_and_affiliation_from_authors(monkeypatch):
    def fake_complete(**kwargs):
        return AnnotationResult(
            paper_list=[
                PaperAnnotation(doi="10.1/a", domain="Agents", category="AI Agents")
            ],
            category_list=["AI Agents"],
        )

    monkeypatch.setattr(pipeline, "complete", fake_complete)

    structured = pipeline.run_annotate(
        papers=[
            {
                "doi": "10.1/a",
                "title": "Paper A",
                "abstract": "",
                "authors": '{"name": "Yutaka Saito", "affiliations": ["The University of Tokyo"]}',
            }
        ],
        model="openai/test-model",
        categories=["AI Agents"],
    )

    paper = structured["AI Agents"][0]
    assert paper["team"] == "Yutaka Saito"
    assert paper["affiliation"] == "The University of Tokyo"


def test_run_filter_sends_affiliation_to_llm(monkeypatch):
    captured = {}

    def fake_complete(*, system, user, **kwargs):
        captured["payload"] = json.loads(user)
        return FilterResult(
            papers={
                "AI Agents": [
                    FilteredPaper(doi="10.1/a", title="Paper A", venue="TestConf", reason="ok")
                ]
            }
        )

    monkeypatch.setattr(pipeline, "complete", fake_complete)

    pipeline.run_filter(
        {
            "AI Agents": [
                {
                    "doi": "10.1/a",
                    "title": "Paper A",
                    "venue": "TestConf",
                    "affiliation": "Stanford University",
                }
            ]
        },
        model="openai/test-model",
    )

    assert captured["payload"]["papers"]["AI Agents"][0]["affiliation"] == "Stanford University"


def test_run_filter_preserves_project_data_fields(monkeypatch):
    def fake_complete(**kwargs):
        return FilterResult(
            papers={
                "AI Agents": [
                    FilteredPaper(
                        doi="10.1101/2025.05.30.656746",
                        title="Biomni: A General-Purpose Biomedical AI Agent",
                        venue="bioRxiv",
                        reason="Relevant biomedical agent",
                    )
                ]
            }
        )

    monkeypatch.setattr(pipeline, "complete", fake_complete)

    filtered = pipeline.run_filter(
        {
            "AI Agents": [
                {
                    "year": "2025.06",
                    "title": "Biomni: A General-Purpose Biomedical AI Agent",
                    "team": "Jure Leskovec",
                    "team website": "https://github.com/snap-stanford",
                    "affiliation": "Stanford University",
                    "domain": "Biomedical AI agent for autonomous research workflows",
                    "venue": "bioRxiv",
                    "paperUrl": "https://www.biorxiv.org/content/10.1101/2025.05.30.656746v1",
                    "codeUrl": "https://biomni.stanford.edu/",
                    "githubStars": "https://img.shields.io/github/stars/snap-stanford/biomni",
                    "doi": "10.1101/2025.05.30.656746",
                }
            ]
        },
        model="openai/test-model",
    )

    paper = filtered["AI Agents"][0]
    assert paper["codeUrl"] == "https://biomni.stanford.edu/"
    assert paper["githubStars"] == "https://img.shields.io/github/stars/snap-stanford/biomni"
    assert paper["reason_for_inclusion"] == "Relevant biomedical agent"
