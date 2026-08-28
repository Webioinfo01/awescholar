"""Tests for utils.py — merge, readme, rss."""

import email.utils
import json
import os
import re
import tempfile
from datetime import UTC, datetime

from awescholar.utils import generate_rss, merge_archive_to_new, merge_new_to_archive, update_readme


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── merge_new_to_archive ─────────────────────────────────────

def test_merge_new_creates_archive():
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "archive.json")
        _write_json(new, {"Cat A": [{"doi": "10.1/a", "title": "Paper A"}]})

        result = merge_new_to_archive(new, archive)

        assert "Cat A" in result
        assert len(result["Cat A"]) == 1
        assert result["Cat A"][0]["doi"] == "10.1/a"
        assert os.path.exists(archive)


def test_merge_new_deduplicates_by_doi():
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "archive.json")
        _write_json(new, {"Cat A": [{"doi": "10.1/a", "title": "Updated Title"}]})
        _write_json(archive, {"Cat A": [{"doi": "10.1/a", "title": "Old Title"}]})

        result = merge_new_to_archive(new, archive)

        assert len(result["Cat A"]) == 1
        assert result["Cat A"][0]["title"] == "Updated Title"


def test_merge_new_adds_to_existing_category():
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "archive.json")
        _write_json(new, {"Cat A": [{"doi": "10.1/b", "title": "Paper B"}]})
        _write_json(archive, {"Cat A": [{"doi": "10.1/a", "title": "Paper A"}]})

        result = merge_new_to_archive(new, archive)

        assert len(result["Cat A"]) == 2


def test_merge_new_creates_new_category():
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "archive.json")
        _write_json(new, {"Cat B": [{"doi": "10.1/b", "title": "Paper B"}]})
        _write_json(archive, {"Cat A": [{"doi": "10.1/a", "title": "Paper A"}]})

        result = merge_new_to_archive(new, archive)

        assert "Cat A" in result
        assert "Cat B" in result


def test_merge_new_reuses_existing_category_with_different_case_and_separator():
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "archive.json")
        _write_json(new, {"AI Agents": [{"doi": "10.1/b", "title": "Paper B", "category": "AI Agents"}]})
        _write_json(archive, {"ai-agents": [{"doi": "10.1/a", "title": "Paper A"}]})

        result = merge_new_to_archive(new, archive)

        assert list(result) == ["ai-agents"]
        assert [p["doi"] for p in result["ai-agents"]] == ["10.1/a", "10.1/b"]


def test_merge_new_does_not_duplicate_doi_across_categories():
    """Same DOI arriving under a different category updates the existing entry
    instead of creating a cross-category duplicate."""
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "archive.json")
        _write_json(archive, {
            "AI Agents": [{"doi": "10.1/a", "title": "Paper A", "venue": "NeurIPS"}]
        })
        _write_json(new, {
            "Reviews": [{"doi": "10.1/a", "title": "Paper A", "affiliation": "MIT"}]
        })

        merged = merge_new_to_archive(new, archive)

        assert len(merged["AI Agents"]) == 1
        assert merged.get("Reviews", []) == []
        entry = merged["AI Agents"][0]
        assert entry["venue"] == "NeurIPS"
        assert entry["affiliation"] == "MIT"


def test_merge_new_title_fallback_backfills_doi():
    """A new paper with no DOI match but the same (normalized) title merges
    into the existing entry and backfills its DOI."""
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "archive.json")
        _write_json(archive, {
            "Foundation models": [
                {"title": "GENERator: A Model", "codeUrl": "https://github.com/x/y"}
            ]
        })
        _write_json(new, {
            "Foundation models": [
                {"title": "generator: a model", "doi": "10.1/g", "venue": "bioRxiv"}
            ]
        })

        merged = merge_new_to_archive(new, archive)

        assert len(merged["Foundation models"]) == 1
        entry = merged["Foundation models"][0]
        assert entry["doi"] == "10.1/g"
        assert entry["codeUrl"] == "https://github.com/x/y"
        assert entry["venue"] == "bioRxiv"


def test_merge_archive_to_new_does_not_duplicate_across_categories():
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "archive.json")
        _write_json(new, {
            "Reviews": [{"doi": "10.1/a", "title": "Paper A", "venue": "NeurIPS"}]
        })
        _write_json(archive, {
            "AI Agents": [{"doi": "10.1/a", "title": "Paper A", "affiliation": "MIT"}]
        })

        enriched = merge_archive_to_new(new, archive)

        assert len(enriched["Reviews"]) == 1
        entry = enriched["Reviews"][0]
        assert entry["venue"] == "NeurIPS"
        assert entry["affiliation"] == "MIT"
        assert enriched.get("AI Agents", []) == []


def test_merge_new_preserves_existing_code_product_fields_when_old_updater_lacks_them():
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "archive.json")
        _write_json(new, {
            "AI Agents": [
                {
                    "doi": "10.1101/2025.05.30.656746",
                    "title": "Biomni: A General-Purpose Biomedical AI Agent",
                }
            ]
        })
        _write_json(archive, {
            "AI Agents": [
                {
                    "doi": "10.1101/2025.05.30.656746",
                    "title": "Biomni: A General-Purpose Biomedical AI Agent",
                    "codeUrl": "https://biomni.stanford.edu/",
                    "githubStars": "https://img.shields.io/github/stars/snap-stanford/biomni",
                }
            ]
        })

        result = merge_new_to_archive(new, archive)

        paper = result["AI Agents"][0]
        assert paper["codeUrl"] == "https://biomni.stanford.edu/"
        assert paper["githubStars"] == "https://img.shields.io/github/stars/snap-stanford/biomni"


def test_merge_new_does_not_clear_existing_code_product_fields_with_empty_values():
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "archive.json")
        _write_json(new, {
            "AI Agents": [
                {
                    "doi": "10.1101/2025.05.30.656746",
                    "title": "Biomni: A General-Purpose Biomedical AI Agent",
                    "codeUrl": "",
                    "githubStars": "",
                }
            ]
        })
        _write_json(archive, {
            "AI Agents": [
                {
                    "doi": "10.1101/2025.05.30.656746",
                    "title": "Biomni: A General-Purpose Biomedical AI Agent",
                    "codeUrl": "https://biomni.stanford.edu/",
                    "githubStars": "https://img.shields.io/github/stars/snap-stanford/biomni",
                }
            ]
        })

        result = merge_new_to_archive(new, archive)

        paper = result["AI Agents"][0]
        assert paper["codeUrl"] == "https://biomni.stanford.edu/"
        assert paper["githubStars"] == "https://img.shields.io/github/stars/snap-stanford/biomni"


# ── merge_archive_to_new ─────────────────────────────────────

def test_merge_archive_enriches_new():
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "archive.json")
        _write_json(new, {"Cat A": [{"doi": "10.1/b", "title": "New Paper"}]})
        _write_json(archive, {"Cat A": [{"doi": "10.1/a", "title": "Archive Paper"}]})

        result = merge_archive_to_new(new, archive)

        assert len(result["Cat A"]) == 2
        dois = {p["doi"] for p in result["Cat A"]}
        assert "10.1/a" in dois
        assert "10.1/b" in dois


def test_merge_archive_no_archive():
    with tempfile.TemporaryDirectory() as tmp:
        new = os.path.join(tmp, "new.json")
        archive = os.path.join(tmp, "nonexistent.json")
        _write_json(new, {"Cat A": [{"doi": "10.1/a", "title": "Paper"}]})

        result = merge_archive_to_new(new, archive)

        assert len(result["Cat A"]) == 1


# ── update_readme ────────────────────────────────────────────

def test_update_readme_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        readme = os.path.join(tmp, "readme.md")
        _write_json(archive, {
            "Models": [{"doi": "10.1/a", "title": "Test Paper", "year": 2025, "domain": "AI"}]
        })

        update_readme(archive, readme, project_title="Test Awesome")

        assert os.path.exists(readme)
        with open(readme) as f:
            content = f.read()
        assert "# Test Awesome" in content
        assert "<!-- AWESCHOLAR:START -->" in content
        assert "## Table of Contents" in content
        assert "Test Paper" in content
        assert "## Models" in content


def test_update_readme_creates_backup_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        readme = os.path.join(tmp, "readme.md")
        _write_json(archive, {"Cat": [{"doi": "10.1/a", "title": "P", "year": 2025}]})
        # Create initial readme
        with open(readme, "w") as f:
            f.write(
                "# Old Content\n"
                "<!-- AWESCHOLAR:START -->\n"
                "old\n"
                "<!-- AWESCHOLAR:END -->\n"
            )

        update_readme(archive, readme)

        # Should have exactly one .bak file
        bak_files = [f for f in os.listdir(tmp) if f.startswith("readme.md.") and f.endswith(".bak")]
        assert len(bak_files) == 1
        with open(os.path.join(tmp, bak_files[0]), encoding="utf-8") as f:
            backup_content = f.read()
        assert backup_content == (
            "# Old Content\n"
            "<!-- AWESCHOLAR:START -->\n"
            "old\n"
            "<!-- AWESCHOLAR:END -->\n"
        )


def test_update_readme_no_backup_skips_backup():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        readme = os.path.join(tmp, "readme.md")
        _write_json(archive, {"Cat": [{"doi": "10.1/a", "title": "P", "year": 2025}]})
        with open(readme, "w") as f:
            f.write(
                "# Old Content\n"
                "<!-- AWESCHOLAR:START -->\n"
                "old\n"
                "<!-- AWESCHOLAR:END -->\n"
            )

        update_readme(archive, readme, no_backup=True)

        bak_files = [f for f in os.listdir(tmp) if f.endswith(".bak")]
        assert bak_files == []


def test_update_readme_no_backup_no_existing_file():
    """no_backup should not error when readme doesn't exist yet."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        readme = os.path.join(tmp, "readme.md")
        _write_json(archive, {"Cat": [{"doi": "10.1/a", "title": "P", "year": 2025}]})

        update_readme(archive, readme, no_backup=True)

        assert os.path.exists(readme)


def test_update_readme_replaces_only_marker_region():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        readme = os.path.join(tmp, "readme.md")
        _write_json(archive, {"Models": [{"doi": "10.1/a", "title": "Test Paper", "year": 2025}]})
        with open(readme, "w", encoding="utf-8") as f:
            f.write(
                "# Manual Title\n"
                "\n"
                "## Table of Contents\n"
                "- [Manual](#manual)\n"
                "\n"
                "<!-- AWESCHOLAR:START -->\n"
                "old generated content\n"
                "<!-- AWESCHOLAR:END -->\n"
                "\n"
                "## Citation\n"
                "Keep this.\n"
            )

        update_readme(archive, readme, no_backup=True)

        with open(readme, encoding="utf-8") as f:

            content = f.read()
        assert "# Manual Title" in content
        assert "- [Manual](#manual)" in content
        assert "## Citation\nKeep this." in content
        assert "old generated content" not in content
        assert "## Models" in content
        assert "Test Paper" in content


def test_update_readme_adds_new_categories_to_toc_outside_markers():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        readme = os.path.join(tmp, "readme.md")
        _write_json(archive, {
            "AI Agents": [{"doi": "10.1/a", "title": "Agent Paper", "year": 2025}],
            "Databases": [{"doi": "10.1/b", "title": "Database Paper", "year": 2025}],
        })
        with open(readme, "w", encoding="utf-8") as f:
            f.write(
                "# Manual Title\n"
                "\n"
                "## Table of Contents\n"
                "- [Old](#old)\n"
                "\n"
                "<!-- AWESCHOLAR:START -->\n"
                "old content\n"
                "<!-- AWESCHOLAR:END -->\n"
            )

        update_readme(archive, readme, no_backup=True)

        with open(readme, encoding="utf-8") as f:

            content = f.read()
        # TOC is outside markers — new categories appended there
        before_marker = content.split("<!-- AWESCHOLAR:START -->", 1)[0]
        assert "- [Old](#old)" in before_marker
        assert "- [AI Agents](#ai-agents)" in before_marker
        assert "- [Databases](#databases)" in before_marker
        # Table sections are inside markers
        generated = content.split("<!-- AWESCHOLAR:START -->", 1)[1].split(
            "<!-- AWESCHOLAR:END -->", 1
        )[0]
        assert "## AI Agents" in generated
        assert "## Databases" in generated
        assert "Agent Paper" in generated
        assert "Database Paper" in generated


def test_update_readme_toc_does_not_duplicate_case_equivalent_categories():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        readme = os.path.join(tmp, "readme.md")
        _write_json(archive, {
            "ai-agents": [{"doi": "10.1/a", "title": "Old Agent", "year": 2025}],
            "AI Agents": [{"doi": "10.1/b", "title": "New Agent", "year": 2025}],
        })

        update_readme(archive, readme, project_title="Custom Title", no_backup=True)

        with open(readme, encoding="utf-8") as f:

            content = f.read()
        assert content.startswith("# Custom Title")
        assert content.count("- [ai-agents](#ai-agents)") == 1
        assert "- [AI Agents](#ai-agents)" not in content
        assert "Old Agent" in content
        assert "New Agent" in content


def test_update_readme_renders_project_data_link_fields_without_clearing_code_product():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        readme = os.path.join(tmp, "readme.md")
        _write_json(archive, {
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
        })

        update_readme(archive, readme, no_backup=True)

        with open(readme, encoding="utf-8") as f:

            content = f.read()
        assert "[Link](https://github.com/snap-stanford)" in content
        assert "[Link](https://www.biorxiv.org/content/10.1101/2025.05.30.656746v1)" in content
        assert "[Link](https://biomni.stanford.edu/)" in content
        assert "![GitHub Stars](https://img.shields.io/github/stars/snap-stanford/biomni)" in content


def test_update_readme_existing_file_requires_marker():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        readme = os.path.join(tmp, "readme.md")
        _write_json(archive, {"Models": [{"doi": "10.1/a", "title": "Test Paper", "year": 2025}]})
        with open(readme, "w", encoding="utf-8") as f:
            f.write("# Manual Title\n")

        try:
            update_readme(archive, readme, no_backup=True)
            assert False, "Expected missing marker error"
        except RuntimeError as exc:
            assert "AWESCHOLAR:START" in str(exc)


# ── generate_rss ─────────────────────────────────────────────

def test_generate_rss_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        rss = os.path.join(tmp, "rss.xml")
        _write_json(archive, {
            "Cat": [{"doi": "10.1/a", "title": "Paper", "abstract": "Abstract text"}]
        })

        generate_rss(archive, rss, title="Test Feed")

        assert os.path.exists(rss)
        with open(rss) as f:
            content = f.read()
        assert "<rss" in content
        assert "Paper" in content
        assert "Test Feed" in content


def test_update_readme_sorts_unpadded_months_correctly():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        readme = os.path.join(tmp, "readme.md")
        _write_json(archive, {
            "Models": [
                {"doi": "10.1/a", "title": "March Paper", "year": "2025.3"},
                {"doi": "10.1/b", "title": "December Paper", "year": "2025.12"},
                {"doi": "10.1/c", "title": "Padded March Paper", "year": "2025.03"},
            ]
        })

        update_readme(archive, readme)

        with open(readme, encoding="utf-8") as f:

            content = f.read()
        march_pos = content.index("March Paper")
        december_pos = content.index("December Paper")
        padded_pos = content.index("Padded March Paper")
        assert december_pos < march_pos
        assert december_pos < padded_pos


def test_generate_rss_lastbuilddate_is_utc():
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "archive.json")
        rss = os.path.join(tmp, "rss.xml")
        _write_json(archive, {"Cat": [{"doi": "10.1/a", "title": "Paper"}]})

        generate_rss(archive, rss, title="Test Feed")

        with open(rss, encoding="utf-8") as f:

            content = f.read()
        m = re.search(r"<lastBuildDate>(.*?)</lastBuildDate>", content)
        assert m, "lastBuildDate missing from RSS output"
        parsed = email.utils.parsedate_to_datetime(m.group(1))
        assert abs((parsed - datetime.now(UTC)).total_seconds()) < 120
