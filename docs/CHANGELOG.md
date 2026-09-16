# Changelog

## Unreleased

CLI regrouped by first principles — every command that only derives artifacts from the project data JSON moves from `updater` to a new `render` group, and citation backfill folds into `updater backfill`; `updater` is now purely the archive-data lifecycle (12 subcommands → 6).

### Highlights

- New `render` group — `render readme` / `render counts` / `render rss` / `render digest` / `render agentx` (formerly `updater readme`/`counts`/`rss`/`digest`/`export-agentx`) — everything that reads `data.json` and writes a derived artifact; rendering never modifies the archive
- `updater citations` folds into `updater backfill --fields citations` (repeatable; default fills affiliation/team and citations) — both were fill-empty-fields passes over the same archive, so they share one command
- `updater` keeps exactly the archive-data lifecycle: `search`, `add`, `update`, `dedupe`, `enrich` (incl. the `--agentx` snapshot refresh), `backfill`
- The `Next:` hints after `updater search --archive` and `updater update --direction new2old` now point at `render counts` / `render rss`, and the scaffolded CONTRIBUTING.md writes the new names
- Breaking: the moved and merged names (`updater readme|counts|rss|digest|export-agentx|citations`) are gone without aliases — switch scripts to the `render` names or `backfill --fields citations`; `updater search` and the other retained subcommands are unchanged

New `updater publish-scan` — scan archived preprints for published versions and upgrade them in place, plus a fix that makes preprint detection cover every preprint server (not just arXiv).

### Highlights

- `updater publish-scan --archive data.json` checks every archived preprint against Semantic Scholar (by DOI, then fuzzy S2 title search, then Crossref `query.title` — title drift between preprint and version of record is the norm, and S2's relevance search sometimes surfaces only citers) and queues the version-of-record metadata into `publish_review.json` next to the archive; title-matched candidates must clear dedupe-grade similarity plus a non-empty venue, which rejects repost copies (ResearchHub and the like) that reuse the exact title
- `--apply` upgrades in one shot: venue, DOI, paperUrl, year, authors and citations switch to the published version, while category, codeUrl, githubStars, domain and affiliation stay; `--review <file> --apply` applies a reviewed queue without rescanning; `--only`/`--limit` scope the scan, `--no-title-search` keeps it DOI-only
- Preprint detection (`is_preprint`) now covers bioRxiv/medRxiv (old `10.1101` and new `10.64898` prefixes), Research Square, Preprints.org, ChemRxiv, Authorea and SSRN in addition to arXiv — a bioRxiv DOI never contains "arxiv", so the old substring check silently missed every non-arXiv preprint server
- As a direct consequence, `updater dedupe --keep published` now correctly prefers a journal version over a bioRxiv/medRxiv preprint when resolving held-back pairs (previously the tie kept the preprint and dropped the published metadata)

Monthly-report workflow — `crawler run --month` replaces copy-a-config-per-month, `updater digest` summarizes a month straight from the archive, report filenames no longer embed the model name, and the filter gates on scope before venue prestige.

### Highlights

- New `crawler run --month 2026-05` (also on `crawler search`; mutually exclusive with `--date`) derives the search dates (`2026-05-01:2026-05-31`, leap years included), the output directory (`month_reports/2605`), and the report name from one argument, overriding `search.publication_date` and `output.db_path` — one tracked base config serves every month, no more hand-copied per-month config files
- New `updater digest --archive docs/data.json --month 2026-05` summarizes the papers a curated archive holds for one month (matched by the `year` field, `2026.05` and unpadded `2026.5` both match): an LLM narrative when a model is configured, structured tables with `--no-llm` or when no key resolves; output defaults to `month_reports/YYMM/digest.md`, and an empty month fails with an actionable error instead of an empty report
- The default report filename is `{db_path}/report.md` instead of `research_report_{model}.md` — the model name moves into a provenance comment at the top of every report (`<!-- awescholar <version> · model: ... · scope: ... -->`), so per-month report paths are stable across model changes
- The filter step now gates on scope before quality: papers whose subject falls outside the research interests (sharing a technique like an LLM but applied in an unrelated domain) are excluded regardless of venue prestige, the annotator-assigned `domain` is sent to the filterer as an off-scope signal, and `filter.limit` is an upper bound rather than a quota — fewer selections is a normal outcome, ending the traffic-prediction-in-a-biology-report failure mode

Single-paper curation pass — DOI-first paper links, `--code-url` and `--annotate` on `updater search`, `--only` scoping on enrich/backfill/citations, the `archive.stars_style` config convention, and `--emit commands` for agentx intake.

### Highlights

- `updater search` writes `paperUrl` as the DOI link (`https://doi.org/…`) whenever the paper has a DOI — the Semantic Scholar page URL is the last-resort fallback, never the first choice
- New `updater search --code-url owner/repo --annotate`: a repo you already know goes straight into `codeUrl` (skipping GitHub discovery; with `archive.stars_style: "badge"` the shields.io URL lands in `githubStars` too), and the configured annotator LLM fills the one-line `domain` of just the added papers — the same annotator the crawler pipeline uses, one batch call, LLM failure never loses the added records
- New `--only "DOI or title substring"` (repeatable) scopes `updater enrich`, `updater backfill`, and `updater citations` to matching entries — topping up one entry no longer rewrites the whole archive (backfill's trusted-name map still spans the whole archive)
- New config `archive.stars_style`: `numeric` (default) keeps refreshing bare ints and migrating legacy badge values; `badge` makes enrich write shields.io URLs and never rewrite an existing badge to a number — the Awesome-AI-Meets-Biology star convention is now config, not documentation; `--stars-style` overrides per run
- New `updater export-agentx --emit commands`: writes an executable `pnpm agent:add owner/repo --category … --name … --paper …` script instead of candidate JSON — the last mile into an agentx repo, where the target's own `agent:add` still validates categories and the tag registry (tags are deliberately not emitted)
- `updater search --archive` and `updater update --direction new2old` print the natural next step (`updater counts` / `updater rss`) after papers land, so README counts and the RSS feed never silently go stale


## v0.2.2

Citation-surface + GitHub-enrichment release — the website shows a citation badge under Paper, `updater search` records carry Semantic Scholar citation counts, `updater citations` fills empty counts, `updater enrich` links papers to their official GitHub repositories with live star counts, and `updater export-agentx` turns repo-backed papers into candidate agents for an AgentX-style registry.

### Highlights

- Website templates (`bio` and `vt`) render a citation badge under the Paper link in the Links column: amber pill with a quote icon, compact `1.2k`/`15k` formatting, and a full-count tooltip sourced from Semantic Scholar
- New `awescholar updater citations --archive docs/data.json` batch-fills empty `citations` fields from Semantic Scholar `citationCount` (DOI required; existing counts are never overwritten)
- `CONTRIBUTING.md` documents the `citations` field in the paper schema and points to the backfill command
- New `updater enrich --archive data.json` fills empty `codeUrl` fields: each paper is searched on GitHub (arXiv ID first, then the leading system name, then the full title), a heuristic scorer accepts only corroborated matches (repo name derivable from the title plus an arXiv ID cited by the repo itself — either signal alone stays below the bar), and ambiguous races go to the configured LLM for a final verdict (`--no-llm` keeps heuristics only, `--limit N` caps resolution per run). Papers that already link a github.com repo get `githubStars` refreshed as a numeric count; legacy badge-URL values migrate automatically, including recovering the repo from badge URLs in entries whose `codeUrl` is empty
- New `updater export-agentx --archive data.json -o candidates.json` exports every paper with a github.com repo as an AgentX snapshot-shaped candidate agent (slug/name/repo/paperMeta/category plus live metrics when a token is available), with slugs generated by agentx rules and duplicate repos collapsed; `--category-map` maps archive categories to agentx slugs, unmapped papers land in `--default-category`, `--categories` scopes the export to given archive categories, `--exclude-snapshot` skips repos already registered in an agentx snapshot, and `source`/`--source-url` record provenance. The file is a review queue for agentx intake, not a drop-in snapshot
- Category handling hardcodes neither side's taxonomy: the previously hardcoded nine agentx slugs are gone — `updater export-agentx` now validates mapped and default slugs against the categories actually present in the `--exclude-snapshot` file (the agentx snapshot is the source of truth; no snapshot means no validation), and `reader stats` gains a repeatable `--category` filter that defaults to every category in the archive instead of any fixed list
- GitHub token resolution follows the Semantic Scholar key pattern: `--github-token` > config `github.token` > env `GITHUB_TOKEN`/`GH_TOKEN` > project or `~/.config/awescholar/.env` (auto-loaded); a stderr warning fires when none is found because anonymous limits (10 searches/min, 60 repo reads/hour) are severe
- The README table now derives the stars badge from the repo URL when `githubStars` holds a numeric count, so stars stay live without re-running enrich; legacy badge-URL values still render unchanged. `updater add` no longer writes badge URLs into new records
- Config now resolves in two deep-merged layers: `~/.config/awescholar/config.json` holds global defaults (shared `model_profiles`, `semantic_scholar`, `github`), and the `--config` project file overrides it key by key (nested dicts merge, so a project can override one profile field or one model name without restating the rest). Commands run without `--config` use the global file alone, so key-dependent commands like `updater enrich` work standalone
- Docs now recommend `~/.config/awescholar/.env` as the primary key store: it is loaded by awescholar itself, so keys stay visible to agents and cron invocations whose shells never source `~/.zshrc`; shell env vars still win when present
- The enrich LLM tiebreak now sees each candidate's `created`/`pushed` dates and topics, and the prompt states the collision rule (a repo created or last pushed years before the paper is usually an unrelated older project sharing the name) — acronym collisions such as an HPC tool matching a same-named dataset paper no longer win the tiebreak
- `updater enrich` learns `--agentx`, treating `--archive` as an AgentX registry snapshot (top-level `{agents, counts}`) instead of an awesome-list archive. It refreshes the same field set the agentx registry's own refresh used to inline-fetch (`stars/pushedAt/openIssues/language/license/description/homepage/archived`; license skipped when `NOASSERTION`, homepage filled only for an explicit empty string because agentx snapshots use `null` for "deliberately no homepage") and strictly preserves every other field — `status`, `slug`, `repo`, `githubUrl`, `paperMeta`, category, tags, source — so the registry's `scripts/snapshot.ts` keeps owning the lifecycle (404 → `gone`, retirement resolution, slug dedup, `writeSnapshot`). The existing awesome-list mode is untouched and the new shape mismatches fail loud
- Enrich search rounds now fall through: when the arXiv-ID round surfaces only candidates the scorer and the LLM both reject, the system-name and full-title rounds still run instead of the search silently ending at the first round with any candidates
- The persisted `archived` flag lets the agentx registry's lifecycle pass mark owner-archived repos `gone` in the same run instead of waiting for `pushedAt` to age out
- `updater export-agentx` writes `counts.gone` (the agentx `SnapshotFile` contract; was `graveyard`) and prefers the archive's full `authors` list over the legacy `team` value when building `paperMeta`
- GitHub 403/429 responses now print a stderr warning instead of silently degrading to "no results", so a rate-limited run is distinguishable from an empty one
- `updater search` (by title or DOI) requests `citationCount` and writes it into each record as `citations`, so `--json-file` output and archive additions carry live citation counts; the alias map accepts `citations`, `citationCount`, and `citation_count`, and archive merges keep existing counts when the incoming value is empty. `citations` is data-only — the README table gains no column
- Search now stores the complete Semantic Scholar author list in a new `authors` field instead of keeping only the last author as `team`: `updater search` records and the crawler DB carry the full name list, normalization accepts both the DB blob (`all`) and plain-list forms so the list survives merging into project data, and archive merges treat an empty list as empty so gaps never wipe an existing list (project data records are now 13 fields, the updater pipeline 15)


## v0.2.1

Repository-scaffolding, read-only query, and duplicate-review release — `awescholar init` generates a complete website-first curated list, a new `reader` group gives the archive a query/recommend face, and `updater` holds back suspected preprint-vs-published duplicates for explicit review.

### Highlights

- New `awescholar init` command scaffolds a complete website-first curated-repo — like Awesome-AI-Meets-Biology — in one step: bilingual landing-page READMEs, a searchable statistics website (`--template bio` or `--template vt`), an empty `docs/data.json` wired into `config.json`, an RSS feed, MPL-2.0 `LICENSE`, `CONTRIBUTING.md`, and `.gitignore`; a custom `--website` domain also writes `docs/CNAME`. After scaffolding it serves `docs/` on `127.0.0.1:8000` for local review (skip with `--no-serve`, pick a port with `--port`, auto-increment while a port is busy). New `updater counts` refreshes per-category counts, totals, and badges in website-first READMEs
- New `reader` command group gives the curated archive a read-only query face: `reader query` (keyword search over title/domain/abstract/venue/team with weighted scoring), `reader related` (in-archive neighbors of a seed paper — by `--doi`, `--title`, or a pasted record via `--input`), `reader recommend` (must-read ranking per research field; offline by default, `--llm` adds model-ranked one-line reasons), and `reader stats`. All reader commands are offline, never modify data, and need no config — `--json` serves agent consumption. SKILL.md ships the reader intents in its router plus a response-format contract for reader answers
- `updater update` now holds back suspected duplicates before merging: entries whose normalized-title similarity to an archive entry is ≥ 0.90 (or ≥ 0.80 with a shared author token) but that dodge the exact DOI/title match — the preprint-vs-published signature — land in `dedupe_review.json` next to the input file instead of being appended; `--no-dedupe` restores the old append-everything behavior. New `updater dedupe --review <file> --archive <data.json> --keep newer|published|both` resolves held-back pairs: the winner's non-empty fields overwrite in place (or both entries are kept), and the review file is removed once applied
- The Semantic Scholar API key resolution order is now documented and explicit: `--ss-api-key` CLI flag > `semantic_scholar.api_key` in config.json > `SEMANTIC_SCHOLAR_API_KEY` environment variable (legacy `SEMANTICSCHOLAR_API_KEY` still honored)
- CI and the release workflow now run a single `./verify` entry point (ruff + pytest) so the local gate matches CI exactly
- `updater search` now accepts paper titles/DOIs as positional arguments for non-interactive use (`awescholar updater search --archive data.json --by doi <doi1> <doi2>`); omitting them keeps the previous interactive prompt

## v0.2.0

Backfill release — a new `updater backfill` command recovers missing affiliation/team fields from three web sources, and archive merges stop duplicating papers across categories.

### Highlights

- New `awescholar updater backfill` command fills empty affiliation/team fields in an existing archive, consulting three sources cheapest-per-coverage first: Semantic Scholar batch endpoints (covers names and teams well), Crossref per-DOI work metadata, and OpenAlex curated institution data. Only empty fields are filled, entries never move between categories, and the affiliation always comes from the same author as the team so the pair can never mismatch; the archive is backed up first unless `--no-backup`
- Backfill reliability fixes: paper batches now request `externalIds` (missing DOIs were the real cause of all-null batch results) and all-empty batch responses are retried instead of trusted
- Pathological affiliation blobs from Crossref deposits (worst live case: 710 chars of department + address + author biography) are shortened at write time — values over 200 chars keep only segments naming an institution, max two, capped at 160 chars
- Archive merge now deduplicates globally across categories by DOI, falling back to normalized-title match for papers without a DOI (which also backfills the DOI onto the existing entry) — previously dedup was per-category by DOI only, so the same paper could appear under two categories
- `updater search` accepts `--category` to add papers to a specific category (normalized to an existing spelling, default remains the first category), and its dedup matches titles case/whitespace-insensitively
- New regression test suites for backfill, record dedup, and merge behavior

## v0.1.9

Dependency-health release — minimum Python 3.11, verified dependency floors, leaner install, and CI hardening.

### Highlights

- Require Python >= 3.11: litellm 1.98.0 (2026-08-22) imports `typing.NotRequired` (3.11+) while its metadata still claims 3.10 support, so fresh installs on 3.10 were broken; 3.10 reaches end-of-life in October 2026. CI matrix is now 3.11/3.12/3.13
- Dependencies declare tested lower bounds (`litellm>=1.86`, `semanticscholar>=0.12`, `sqlalchemy>=2.0`, `python-dotenv>=1.0`) — pip can no longer resolve to untested ancient versions
- Drop unused `rich` dependency — never imported by awescholar (litellm brings its own); one less upstream to break
- CI now runs `ruff check` alongside pytest, on Node 24 action versions (`checkout@v7`, `setup-python@v7`, `action-gh-release@v3`) — removes the Node.js 20 deprecation warning; ruff is pinned (`==0.16.5`) so the lint gate is reproducible
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
