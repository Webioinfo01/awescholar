"""Single-record operations: search by title/DOI and interactive manual entry."""

import json
import os

from semanticscholar import SemanticScholar

from .categories import canonicalize_category
from .data_fields import normalize_title

FIELDS = [
    "year", "title", "team", "team website", "affiliation",
    "domain", "venue", "paperUrl", "codeUrl", "githubStars",
]


def _get_client(api_key: str | None = None) -> SemanticScholar:
    key = api_key or os.getenv("SEMANTICSCHOLAR_API_KEY")
    return SemanticScholar(api_key=key) if key else SemanticScholar()


def _paper_to_record(paper) -> dict | None:
    if not paper:
        return None

    team = ""
    if paper.authors:
        team = paper.authors[-1].name or ""

    year = ""
    pub_date = getattr(paper, "publicationDate", None)
    if pub_date:
        if isinstance(pub_date, str):
            year = pub_date[:7].replace("-", ".")
        else:
            year = pub_date.strftime("%Y.%m")
    elif getattr(paper, "year", None):
        year = str(paper.year)

    ext_ids = getattr(paper, "externalIds", None) or {}
    doi = ext_ids.get("DOI", "")

    venue = getattr(paper, "venue", None) or ""
    if not venue:
        journal = getattr(paper, "journal", None)
        if journal and hasattr(journal, "name"):
            venue = journal.name or ""

    paper_url = getattr(paper, "url", None) or ""
    if not paper_url and paper.paperId:
        paper_url = f"https://www.semanticscholar.org/paper/{paper.paperId}"

    return {
        "year": year,
        "title": paper.title or "",
        "team": team,
        "team website": "",
        "affiliation": "",
        "domain": "",
        "venue": venue,
        "paperUrl": paper_url,
        "codeUrl": "",
        "githubStars": "",
        "doi": doi,
    }


def search_by_title(title: str, sch: SemanticScholar) -> dict | None:
    if not title.strip():
        return None
    try:
        paper = sch.search_paper(
            title, limit=1, match_title=True,
            fields=["paperId", "title", "venue", "year",
                    "publicationDate", "authors", "externalIds", "url", "journal"],
        )
        return _paper_to_record(paper)
    except Exception as e:  # noqa: BLE001 — one failed lookup must not abort the batch
        print(f"  Error: {e}")
        return None


def search_by_doi(doi: str, sch: SemanticScholar) -> dict | None:
    if not doi.strip():
        return None
    try:
        paper = sch.get_paper(
            f"DOI:{doi}",
            fields=["paperId", "title", "venue", "year",
                    "publicationDate", "authors", "externalIds", "url", "journal"],
        )
        return _paper_to_record(paper)
    except Exception as e:  # noqa: BLE001 — one failed lookup must not abort the batch
        print(f"  Error: {e}")
        return None


def _load_archive(archive_path: str) -> dict | list:
    if not os.path.exists(archive_path):
        return {}
    with open(archive_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_archive(archive_path: str, data) -> None:
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_flat_json(path: str) -> list:
    """Load a flat JSON list file. Returns empty list if not found."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Flatten dict format to list if needed
    if isinstance(data, dict):
        flat = []
        for papers in data.values():
            if isinstance(papers, list):
                flat.extend(papers)
        return flat
    return data


def _save_flat_json(path: str, papers: list) -> None:
    """Save papers as a flat JSON list."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(papers, f, indent=2, ensure_ascii=False)


def _is_duplicate(papers: list, record: dict) -> bool:
    rec_title = normalize_title(record.get("title"))
    rec_doi = record.get("doi")
    for existing in papers:
        if rec_title and normalize_title(existing.get("title")) == rec_title:
            return True
        if rec_doi and existing.get("doi") == rec_doi:
            return True
    return False


def search_and_add(
    archive_path: str | None = None,
    by: str = "title",
    api_key: str | None = None,
    json_file: str | None = None,
    category: str | None = None,
) -> None:
    """Search Semantic Scholar by title or DOI and add records to archive or json file."""
    target = json_file or archive_path
    print("\nSemantic Scholar Paper Search")
    print(f"Search by: {by}")
    print(f"Target: {target}")

    queries = []
    print(f"\nEnter paper {by} (empty line to finish):")
    while True:
        line = input(f"  [{len(queries) + 1}] ").strip()
        if not line:
            break
        queries.append(line)

    if not queries:
        print("\nNo papers to search.")
        return

    sch = _get_client(api_key)

    if json_file:
        # Flat list mode: save to a standalone JSON file for review
        papers_list = _load_flat_json(json_file)
        added = 0
        for i, query in enumerate(queries, 1):
            print(f"\n[{i}/{len(queries)}] Searching: {query}")
            record = search_by_title(query, sch) if by == "title" else search_by_doi(query, sch)

            if not record:
                print("  Not found.")
                continue

            if _is_duplicate(papers_list, record):
                print(f"  Already exists: {record['title'][:60]}")
                continue

            papers_list.append(record)
            added += 1
            print(f"  Added: {record['title'][:60]}")

        if added:
            _save_flat_json(json_file, papers_list)
            print(f"\nAdded {added} paper(s) to {json_file}")
        else:
            print("\nNo new papers were added.")
    else:
        # Archive mode: save to categorized archive dict
        archive = _load_archive(archive_path)
        if not isinstance(archive, dict):
            archive = {"papers": archive}

        added = 0
        # Add to the requested category (normalized to an existing spelling),
        # falling back to the first category as before
        if category:
            target = canonicalize_category(category, archive.keys())
        else:
            categories = list(archive.keys())
            target = categories[0] if categories else "papers"

        for i, query in enumerate(queries, 1):
            print(f"\n[{i}/{len(queries)}] Searching: {query}")
            record = search_by_title(query, sch) if by == "title" else search_by_doi(query, sch)

            if not record:
                print("  Not found.")
                continue

            # Flatten all papers across categories for dedup
            all_papers = []
            for cat_papers in archive.values():
                if isinstance(cat_papers, list):
                    all_papers.extend(cat_papers)

            if _is_duplicate(all_papers, record):
                print(f"  Already exists: {record['title'][:60]}")
                continue

            if target not in archive:
                archive[target] = []
            archive[target].append(record)
            added += 1
            print(f"  Added: {record['title'][:60]}")

        if added:
            _save_archive(archive_path, archive)
            print(f"\nAdded {added} paper(s) to {archive_path}")
        else:
            print("\nNo new papers were added.")


def add_interactive(archive_path: str, categories: list[str] | None = None) -> None:
    """Interactively add a single record to the archive."""
    if categories is None:
        categories = ["ai-agents", "foundation-models", "databases", "benchmarks", "reviews"]

    print("\nSelect category:")
    for i, cat in enumerate(categories, 1):
        print(f"  {i}. {cat}")

    while True:
        choice = input("Enter number or name: ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(categories):
                category = categories[idx]
                break
        elif choice in categories:
            category = choice
            break
        print("Invalid choice.")

    print(f"\nCategory: {category}")
    print("Enter fields separated by semicolons (;). Use \"\" for empty values.")
    print("Fields: year; title; team; team website; affiliation; domain; venue; paperUrl; codeUrl; githubStars")

    while True:
        line = input("Record: ").strip()
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < len(FIELDS):
            parts.extend([""] * (len(FIELDS) - len(parts)))
        elif len(parts) > len(FIELDS):
            print(f"Too many fields. Expected {len(FIELDS)}, got {len(parts)}.")
            continue
        parts = ["" if p == '""' else p for p in parts]
        if not parts[0]:
            print("Year is mandatory.")
            continue
        if not parts[1]:
            print("Title is mandatory.")
            continue

        # Auto-generate GitHub stars badge
        code_url = parts[8]
        if "github.com" in code_url:
            try:
                path = code_url.split("github.com/")[1].strip("/")
                owner_repo = "/".join(path.split("/")[:2])
                parts[9] = f"https://img.shields.io/github/stars/{owner_repo}"
            except Exception:  # noqa: BLE001, S110 — badge is best-effort decoration
                pass
        break

    record = dict(zip(FIELDS, parts))

    archive = _load_archive(archive_path)
    if not isinstance(archive, dict):
        archive = {}

    if category not in archive:
        archive[category] = []
    archive[category].append(record)
    archive[category].sort(key=lambda x: x.get("year", "0"), reverse=True)

    _save_archive(archive_path, archive)
    print(f"\nRecord added to '{category}' in {archive_path}")
