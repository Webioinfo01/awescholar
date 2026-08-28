# Changelog

## v0.1.9

Dependency-health release — minimum Python 3.11, verified dependency floors, leaner install, and CI hardening.

### Highlights

- Require Python >= 3.11: litellm 1.98.0 (2026-08-22) imports `typing.NotRequired` (3.11+) while its metadata still claims 3.10 support, so fresh installs on 3.10 were broken; 3.10 reaches end-of-life in October 2026. CI matrix is now 3.11/3.12/3.13
- Dependencies declare tested lower bounds (`litellm>=1.86`, `semanticscholar>=0.12`, `sqlalchemy>=2.0`, `python-dotenv>=1.0`) — pip can no longer resolve to untested ancient versions
- Drop unused `rich` dependency — never imported by awescholar (litellm brings its own); one less upstream to break
- CI now runs `ruff check` alongside pytest, on Node 24 action versions (`checkout@v7`, `setup-python@v7`, `action-gh-release@v3`) — removes the Node.js 20 deprecation warning
- README version badges are now dynamic PyPI badges — no more manual badge bumps at release time (the Chinese README badge had drifted to v0.1.6)
- Remove the `tomli` test fallback and dev dependency — 3.11+ always has `tomllib`

## v0.1.8

Bugfix release — restore the author affiliation data chain that silently broke paper filtering.

### Highlights

- Fix: author detail lookups failed silently on every search — `get_authors` returns objects, not dicts, so the affiliations lookup threw and the exception was swallowed. Author names and affiliations are now fetched and stored correctly (as JSON in the `authors` field)
- Fix: the filter step now receives real `affiliation` values (extracted from stored author data) instead of always-empty strings — the filterer's top ranking priority (premier venues and institutions) finally has data to work with
- Fix: papers loaded from the DB (`skip_search` / `crawler annotate`) now include the `authors` field so team and affiliation extraction also works on resumed runs
- Fix: README table sorting pads unpadded months, so `2025.3` no longer sorts after `2025.12`
- Fix: RSS `lastBuildDate` is now UTC instead of local time labeled as GMT
- Chore: remove unused import, fix `_split_sections` docstring; new regression tests for search persistence, affiliation extraction, and filter payload

## v0.1.7

Documentation restructure — AI agent usage guide, install/usage flow, and contributing docs.

### Highlights

- New `README.ai.md` — dedicated install and usage guide for AI coding agents
- README restructure: move "Powered by aweskill" to top, merge Quick Start into Usage after Config, add AI/human usage sections
- Add aweskill badge to README titles
- Add Webioinfo org link to README
- Update CONTRIBUTING.md with missing modules and cross-reference from README
- Add `docs/todo/refactor_0528.md` planning notes

## v0.1.6

Module refactor, multi-README auto-discovery, and Python 3.10 compatibility fix.

### Highlights

- Refactor: split monolithic `utils.py` into focused modules — `archive.py` (merge operations), `readme.py` (README generation), `rss.py` (RSS feed), with `utils.py` as a backwards-compatible re-export facade
- `updater readme` auto-discovers all README files containing `<!-- AWESCHOLAR:START -->` markers when `--readme` is not specified — supports multilingual READMEs out of the box
- Fix: `html.escape` in XML paper snippets to prevent injection in LLM prompts
- Fix: use `tomli` fallback for Python 3.10 compatibility in tests
- Update CONTRIBUTING.md architecture docs to reflect new module layout

## v0.1.5

Agent install flow, filtering config propagation, licensing metadata, and test maintenance.

### Highlights

- Agent bootstrap docs now install the `awescholar` CLI first, then choose a skill management path (`aweskill` or direct copy)
- README install sections clarify that `aweskill` and direct copy are two ways to manage the awescholar skill, not two separate CLI install methods
- Fix: `filter.research_interests` now reaches the normal full `crawler run` filter path
- Version metadata is kept aligned between package metadata, `__version__`, README badges, and CLI version tests
- Project license metadata changed to MPL-2.0 and a repository LICENSE file was added
- Test suite cleanup removes low-value schema tests, parameterizes duplicate detection coverage, and makes README backup assertions time-independent
- Ruff cleanup removes unused code found during release validation

## v0.1.4

Marker-based README update, data field normalization, and robust merge/readme/rss handling.

### Highlights

- Marker-based README update — `updater readme` now only modifies content between `<!-- AWESCHOLAR:START -->` and `<!-- AWESCHOLAR:END -->`, preserving custom headings, citations, and project text outside that region
- Category normalization — new `categories.py` module for consistent category mapping across pipeline
- Data field normalization (`data_fields.py`) — normalize project data fields and preserve code/product links during merge
- Robust merge/readme/rss — handle missing DOI, mixed year types, and normalized fields without crashing
- Preserve existing README TOC and headers on update
- Hero image and AI agent install guide added to README
- Expanded SKILL.md with full workflow diagrams and command reference

## v0.1.3

Config module extraction, auto-merge pipeline, and filter limit fix.

### Highlights

- Extract `config.py` module — `load_config`, `prefix_model`, `resolve_agent_settings` moved out of `cli.py` for reuse and testability
- `pipeline.data_json_path` — auto-merge filtered results into project data JSON after pipeline completes
- `updater search --json-file` — save search results to flat JSON for review before merging into project data
- `updater readme --no-backup` — skip timestamped README backup creation
- Fix: filter now respects `limit` by truncating in LLM ranking order (previously kept all papers)
- Add ruff as dev dependency (`py310`, `line-length = 100`)
- Add install and PyPI downloads badges to README
- Terminology: "archive" → "project data JSON" across docs and CLI help
- New tests: config loading, agent resolution, CLI help/version, pipeline auto-merge

## v0.1.2

Model profiles, research interests filter, and PyPI publish fix.

### Highlights

- `model_profiles` — named LLM provider presets (api_key + base_url) referenced by `profile` field in `model` and `agent_models`, so switching providers only requires changing one field
- `research_interests` in `filter` config — user-defined interests passed to the filterer for priority-based selection
- `--input` flags on `annotate`, `filter`, `report` subcommands for step reuse without re-running earlier stages
- Reporter prompt: enforce consecutive global index, every paper must appear in report
- Filter prompt: quality-first priority, then relevance to research interests
- PyPI publish switched from OIDC (`pypa/gh-action-pypi-publish`) to `twine upload` with API token
- `config.example.json` updated with `model_profiles` usage

## v0.1.1

CLI restructure, grouped config format, and new single-record commands.

### Highlights

- Group CLI commands into `crawler` (search, annotate, filter, report, run) and `updater` (update, readme, rss, search, add)
- Grouped config format: `model`, `search`, `filter`, `output`, `pipeline`, `agent_models`
- `agent_models` — override LLM model per agent (annotator, filterer, reporter)
- Pipeline flow control: `skip_search`, `use_updater_json`, `use_filtered_json`
- `search.query` in config allows `crawler run` without CLI query argument
- `awescholar updater search` — search Semantic Scholar by title/DOI and add to archive
- `awescholar updater add` — interactively add a single record to archive
- Document `fields_of_study` valid values (23 fields) in search module
- Add Chinese README (README_cn.md), CONTRIBUTING.md, CI/CD workflows
- Add "Scientific Literature Curator" subtitle to README

## v0.1.0

Initial release. Simplified rewrite of AweAgent without agent framework dependency.

### Highlights

- Pure Python + LiteLLM — no Agno or other agent framework
- 4-step pipeline: search, annotate, filter, report
- Semantic Scholar integration with SQLite deduplication
- Incremental merge for maintaining curated Awesome lists
- README table generation and RSS feed from archive JSON
- Multi-provider LLM support via LiteLLM (OpenAI, DeepSeek, Gemini, Mistral)
- Config via JSON file with `${ENV_VAR}` expansion or direct environment variables
