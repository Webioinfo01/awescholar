"""CLI entry point for awescholar."""

import argparse
import json
import os
import sys

from . import __version__
from .archive import DateEncoder
from .config import load_config, resolve_agent_config


def get_version() -> str:
    return __version__


def status(msg: str) -> None:
    print(f"  -> {msg}")


# ── Subcommands ──────────────────────────────────────────────

def cmd_search(args: argparse.Namespace, config: dict) -> int | None:
    from .pipeline import run_search

    papers = run_search(
        query=args.query,
        db_path=config["db_path"],
        api_key=config["ss_api_key"],
        limit=args.limit or config["limit_search"],
        fields_of_study=config["fields_of_study"],
        publication_date_or_year=args.date or config["publication_date"],
        status_cb=status,
    )
    print(f"\nSaved {len(papers)} papers to {config['db_path']}/papers.db")


def cmd_annotate(args: argparse.Namespace, config: dict) -> int | None:
    from .pipeline import run_annotate

    if args.input:
        if not os.path.exists(args.input):
            print(f"Not found: {args.input}")
            return 1
        with open(args.input, "r", encoding="utf-8") as f:
            papers = json.load(f)
    else:
        from .db import Paper, get_session
        session = get_session(config["db_path"])
        db_papers = session.query(Paper).all()
        session.close()
        if not db_papers:
            print("No papers in database. Run 'awescholar crawler search <query>' first.")
            return 1
        papers = [
            {"doi": p.doi, "title": p.title, "abstract": p.abstract, "venue": p.venue,
             "authors": p.authors}
            for p in db_papers
        ]

    model, api_key, base_url = resolve_agent_config(config, "annotator")
    structured = run_annotate(
        papers=papers, model=model, categories=config["categories"],
        include_abstracts=config["include_abstracts"],
        api_key=api_key, base_url=base_url, status_cb=status,
    )

    out_path = os.path.join(config["db_path"], "updater.json")
    os.makedirs(config["db_path"], exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2, ensure_ascii=False, cls=DateEncoder)
    print(f"\nSaved annotated data to {out_path}")


def cmd_filter(args: argparse.Namespace, config: dict) -> int | None:
    from .pipeline import run_filter

    updater_path = args.input or os.path.join(config["db_path"], "updater.json")
    if not os.path.exists(updater_path):
        print(f"Not found: {updater_path}. Run 'awescholar crawler annotate' first.")
        return 1

    with open(updater_path, "r", encoding="utf-8") as f:
        structured = json.load(f)

    model, api_key, base_url = resolve_agent_config(config, "filterer")
    filtered = run_filter(
        structured_data=structured, model=model,
        limit=args.limit or config["limit_filter"],
        research_interests=config.get("research_interests"),
        api_key=api_key, base_url=base_url, status_cb=status,
    )

    out_path = os.path.join(config["db_path"], "updater_filter.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False, cls=DateEncoder)
    print(f"\nSaved filtered data to {out_path}")


def cmd_report(args: argparse.Namespace, config: dict) -> int | None:
    from .pipeline import run_report

    filtered_path = args.input or os.path.join(config["db_path"], "updater_filter.json")
    if not os.path.exists(filtered_path):
        print(f"Not found: {filtered_path}. Run 'awescholar crawler filter' first.")
        return 1

    with open(filtered_path, "r", encoding="utf-8") as f:
        filtered = json.load(f)

    model, api_key, base_url = resolve_agent_config(config, "reporter")
    report = run_report(
        filtered_data=filtered, model=model,
        date_range=config.get("publication_date") or "N/A",
        api_key=api_key, base_url=base_url, status_cb=status,
    )

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nReport saved to {args.output}")
    else:
        print("\n" + report)


def cmd_run(args: argparse.Namespace, config: dict) -> int | None:
    from .pipeline import run_pipeline

    query = args.query or config.get("search_query")
    if not query and not config.get("skip_search"):
        print("Error: query is required (via CLI arg or config search.query)")
        return 1

    _, report = run_pipeline(
        query=query, model=config["model"], db_path=config["db_path"],
        api_key=config["api_key"], ss_api_key=config["ss_api_key"], base_url=config["base_url"],
        agent_models=config.get("agent_models"),
        model_profiles=config.get("model_profiles"),
        limit_search=args.limit_search or config["limit_search"],
        limit_filter=args.limit_filter or config["limit_filter"],
        categories=config["categories"], include_abstracts=config["include_abstracts"],
        fields_of_study=config["fields_of_study"],
        publication_date_or_year=args.date or config["publication_date"],
        skip_search=config["skip_search"],
        use_updater_json=config["use_updater_json"],
        use_filtered_json=config["use_filtered_json"],
        existing_json_path=config["existing_json_path"],
        merge_new_to_old=config["merge_new_to_old"],
        data_json_path=config["data_json_path"],
        research_interests=config.get("research_interests"),
        status_cb=status,
    )

    output = args.output or config.get("report_filename")
    if not output:
        reporter_model, _, _ = resolve_agent_config(config, "reporter")
        model_suffix = reporter_model.split("/")[-1]
        output = os.path.join(config["db_path"], f"research_report_{model_suffix}.md")
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport saved to {output}")


def cmd_update(args: argparse.Namespace, config: dict) -> int | None:
    from .archive import merge_archive_to_new, merge_new_to_archive

    new_path = args.input or os.path.join(config["db_path"], "updater_filter.json")
    if not os.path.exists(new_path):
        print(f"Not found: {new_path}. Run 'awescholar crawler run' first.")
        return 1

    if args.direction == "new2old":
        merge_new_to_archive(new_path, args.archive)
        print(f"Merged new papers into {args.archive}")
    elif args.direction == "old2new":
        merge_archive_to_new(new_path, args.archive)
        print(f"Enriched {new_path} with archive papers")


def cmd_readme(args: argparse.Namespace, config: dict) -> int | None:
    from .readme import discover_readme_targets, update_readme

    if args.readme:
        targets = [args.readme]
    else:
        targets = discover_readme_targets(".")
        if not targets:
            targets = [os.path.join(os.path.dirname(args.archive), "readme.md")]

    for readme_path in targets:
        update_readme(
            archive_path=args.archive, readme_path=readme_path,
            project_title=args.title or "Awesome Scholar",
            project_description=args.description or "",
            no_backup=args.no_backup,
        )
        print(f"README updated at {readme_path}")


def cmd_rss(args: argparse.Namespace, config: dict) -> int | None:
    from .rss import generate_rss

    output = args.output or "rss.xml"
    generate_rss(
        archive_path=args.archive, output_path=output,
        title=args.title or "Awesome Scholar Updates",
        link=args.link or "",
        description=args.description or "Latest papers from curated collection",
        rss_url=args.rss_url or "",
    )
    print(f"RSS feed generated at {output}")


def cmd_search_record(args: argparse.Namespace, config: dict) -> int | None:
    from .record import search_and_add

    if not args.archive and not args.json_file:
        print("Error: provide --archive or --json-file")
        return 1
    search_and_add(
        archive_path=args.archive, by=args.by,
        api_key=config["ss_api_key"], json_file=args.json_file,
        category=args.category,
    )


def cmd_add(args: argparse.Namespace, config: dict) -> int | None:
    from .record import add_interactive

    add_interactive(archive_path=args.archive, categories=config.get("categories"))


# ── Main ─────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="awescholar",
        description="Automated scientific literature discovery and curation.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"awescholar {get_version()}")
    parser.add_argument("--config", type=str, help="Path to config.json")
    sub = parser.add_subparsers(dest="command")

    # crawler
    crawler = sub.add_parser("crawler", help="Paper discovery pipeline")
    crawler_sub = crawler.add_subparsers(dest="crawler_command")

    p = crawler_sub.add_parser("search", help="Search Semantic Scholar for papers")
    p.add_argument("query", type=str, help="Search query string")
    p.add_argument("--limit", type=int, help="Max results (default: 100)")
    p.add_argument("--date", type=str, help="Date range, e.g. 2025-01-01:2025-05-30")

    p = crawler_sub.add_parser("annotate", help="Annotate papers with domain and category")
    p.add_argument("--input", type=str, help="Path to papers JSON (default: read from DB)")

    p = crawler_sub.add_parser("filter", help="Select top papers by quality and relevance")
    p.add_argument("--input", type=str, help="Path to annotated JSON (default: {db_path}/updater.json)")
    p.add_argument("--limit", type=int, help="Number of papers to keep (default: 20)")

    p = crawler_sub.add_parser("report", help="Generate Markdown report from filtered data")
    p.add_argument("input", type=str, nargs="?", help="Path to filtered JSON (default: {db_path}/updater_filter.json)")
    p.add_argument("-o", "--output", type=str, help="Output file path")

    p = crawler_sub.add_parser("run", help="Run full pipeline: search, annotate, filter, report")
    p.add_argument("query", type=str, nargs="?", help="Search query string (or set in config)")
    p.add_argument("--limit-search", type=int, help="Max search results (default: 100)")
    p.add_argument("--limit-filter", type=int, help="Papers to keep after filter (default: 20)")
    p.add_argument("--date", type=str, help="Date range, e.g. 2025-01-01:2025-05-30")
    p.add_argument("-o", "--output", type=str, help="Report output path")

    # updater
    updater = sub.add_parser("updater", help="Archive data management")
    updater_sub = updater.add_subparsers(dest="updater_command")

    p = updater_sub.add_parser("update", help="Merge data between new results and project data JSON")
    p.add_argument("--direction", choices=["new2old", "old2new"], required=True)
    p.add_argument("--input", type=str, help="Path to new data JSON")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")

    p = updater_sub.add_parser("readme", help="Generate README tables from project data JSON")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("--readme", type=str, help="Output README path")
    p.add_argument("--title", type=str, help="Project title")
    p.add_argument("--description", type=str, help="Project description")
    p.add_argument("--no-backup", action="store_true", help="Do not create a backup of the README before updating")

    p = updater_sub.add_parser("rss", help="Generate RSS feed from project data JSON")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")
    p.add_argument("-o", "--output", type=str, help="Output RSS file path")
    p.add_argument("--title", type=str, help="Feed title")
    p.add_argument("--link", type=str, help="Channel link URL")
    p.add_argument("--rss-url", type=str, help="RSS self-link URL")
    p.add_argument("--description", type=str, help="Channel description")

    p = updater_sub.add_parser("search", help="Search Semantic Scholar by title/DOI and add to project data JSON")
    p.add_argument("--archive", type=str, help="Path to project data JSON")
    p.add_argument("--json-file", type=str, help="Save to a flat JSON list for review (instead of archive)")
    p.add_argument("--by", choices=["title", "doi"], default="title", help="Search by title or DOI (default: title)")
    p.add_argument("--category", type=str, help="Category for added papers (default: first category in archive)")

    p = updater_sub.add_parser("add", help="Interactively add a single record to project data JSON")
    p.add_argument("--archive", type=str, required=True, help="Path to project data JSON")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.command == "crawler":
        if not args.crawler_command:
            crawler.print_help()
            return 0
        handlers = {
            "search": cmd_search, "annotate": cmd_annotate, "filter": cmd_filter,
            "report": cmd_report, "run": cmd_run,
        }
        return handlers[args.crawler_command](args, config) or 0

    if args.command == "updater":
        if not args.updater_command:
            updater.print_help()
            return 0
        handlers = {
            "update": cmd_update, "readme": cmd_readme, "rss": cmd_rss,
            "search": cmd_search_record, "add": cmd_add,
        }
        return handlers[args.updater_command](args, config) or 0


if __name__ == "__main__":
    sys.exit(main())
