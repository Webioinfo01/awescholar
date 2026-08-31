---
name: awescholar
description: "Use when working with awescholar CLI — scientific literature discovery, annotation, filtering, and report generation. 中文触发词：文献检索、论文搜索、研究报告、awescholar、文献综述、更新数据、更新readme。"
---

# Awescholar

Use `awescholar` CLI directly. Do not add wrapper scripts unless the CLI is missing a needed capability.

## Intent Router

Match the user's intent to a task domain, then follow the workflow below.

| User intent | Domain | First command |
|---|---|---|
| "Create a new awesome paper list repo", "scaffold a curated list" | Init | `awescholar init <dir> --title ... --github-repo ... --website ...` |
| "Search for papers about X", "find recent papers" | Crawler Pipeline | `awescholar --config cfg.json crawler search "query"` |
| "Run the full discovery pipeline" | Crawler Pipeline | `awescholar --config cfg.json crawler run "query"` |
| "Update the project", "full update", "merge and update" | Updater Full | `updater update` → `updater counts` (website-first) or `updater readme` (tables) → `updater rss` |
| "Merge new results into project data", "update the archive" | Updater Merge | `awescholar updater update --direction new2old --input X --archive Y` |
| "Update the README table" | Updater README | `awescholar updater readme --archive data.json` |
| "Refresh README paper counts" | Updater Counts | `awescholar updater counts --archive docs/data.json` |
| "Generate RSS feed" | Updater RSS | `awescholar updater rss --archive data.json` |
| "Add a paper by title/DOI search" | Updater Search | `awescholar updater search --json-file papers.json` |
| "Manually add a paper record" | Updater Add | `awescholar updater add --archive data.json` |

## First-Time Setup

1. Install: `pip install awescholar`
2. Copy `config.example.json` to `config.json` (or any path)
3. Set API keys: `SEMANTICSCHOLAR_API_KEY` and your LLM provider key (e.g. `GLM_API_KEY`)
4. Verify: `awescholar -v`

## Core Rules

1. Always use `--config` when running crawler commands — it carries model, API key, and search settings.
2. Crawler steps are sequential: search → annotate → filter → report. Each reads from the previous step's output by default, but accepts `--input` to override.
3. Updater commands operate on the **project data JSON** (long-lived curated file, e.g. `docs/data.json`). Do not confuse with pipeline intermediates (`updater.json`, `updater_filter.json`).
4. For `updater search`: use `--json-file` to save results for review first, then `updater update --direction new2old` to merge. Use `--archive` only when you want to write directly.
5. For `updater readme`: default behavior creates a timestamped `.bak` backup. Use `--no-backup` to skip.

## Workflows

### Init (Scaffold a New Repository)

Use when creating a brand-new curated paper-list repository. Generates bilingual website-first READMEs, a searchable statistics website, an empty `docs/data.json` wired into `config.json`, RSS, LICENSE, CONTRIBUTING.md, and `.gitignore`.

```bash
# Everything optional — bare init in an empty dir uses Awesome-AI-Meets-Biology defaults
awescholar init ./my-awesome-list --title "Awesome AI Foo" \
    --subtitle "A curated survey of AI for foo" \
    --github-repo Webioinfo01/Awesome-AI-Foo \
    --website http://foo.webioinfo.top/ \
    --category "AI Agents" --category "Foundation models" --category Reviews

awescholar init --template vt          # Awesome-AI-Virtual-Tumor style website (default: bio)
awescholar init --no-zh --no-branding  # English-only README, no ecosystem/support sections
awescholar init --tables               # also embed classic AWESCHOLAR README table markers
```

After init: edit `config.json` (model keys, search query), then add papers with `updater add` / `updater search`. For website-first repos (no embedded tables), refresh README counts with `updater counts` after merging papers.

### Crawler Pipeline

Use when discovering and curating new papers. Each step can run independently with `--input`.

```bash
# Full pipeline (search + annotate + filter + report)
awescholar --config cfg.json crawler run "AI agent" --limit 50 --date 2025-01-01:2025-05-30 -o report.md

# Step-by-step
awescholar --config cfg.json crawler search "AI agent" --limit 100 --date 2025-01-01:2025-05-30
awescholar --config cfg.json crawler annotate                       # reads from DB
awescholar --config cfg.json crawler annotate --input papers.json   # reads from JSON
awescholar --config cfg.json crawler filter --limit 20              # reads from updater.json
awescholar --config cfg.json crawler report -o report.md            # reads from updater_filter.json
awescholar --config cfg.json crawler report updater_filter.json -o report.md  # explicit input
```

Pipeline config flow control:
- `skip_search: true` — load from DB, do annotate + filter + report
- `use_updater_json: true` — skip annotate, do filter + report
- `use_filtered_json: true` — skip to report only
- `merge_new_to_old: true` + `data_json_path` — auto-merge filtered results into project data JSON after filter step

### Updater Merge

Use when merging new pipeline results into the project data JSON, or enriching new results with historical data.

```bash
# Merge new filtered results into project data JSON
awescholar updater update --direction new2old --input output/updater_filter.json --archive docs/data.json

# Enrich new results with historical data from project data JSON
awescholar updater update --direction old2new --input output/updater_filter.json --archive docs/data.json
```

Decision order:
1. Review `updater_filter.json` before merging — confirm content is appropriate.
2. `new2old` when new papers should be added to the curated collection.
3. `old2new` when the new report should include relevant historical papers.

### Updater Full Update

Use when updating the entire project after new data is ready. Chains all three updater steps.

```bash
# 1. Merge new filtered results into project data
awescholar updater update --direction new2old --input output/updater_filter.json --archive docs/data.json

# 2. Regenerate README table
awescholar updater readme --archive docs/data.json --readme readme.md --no-backup

# 3. Regenerate RSS feed
awescholar updater rss --archive docs/data.json -o docs/rss.xml
```

Decision order:
1. Review `updater_filter.json` before merging — confirm content is appropriate.
2. Run merge first (`updater update`). If merge fails, stop and fix before continuing.
3. Run readme (`updater readme`). If readme fails, the data is already merged — check for marker issues.
4. Run RSS last (`updater rss`). Skipping RSS means subscribers won't see new papers.

### Updater Search & Add

Use when adding individual papers to the project data JSON.

```bash
# Search Semantic Scholar, save to flat JSON for review
awescholar updater search --json-file papers.json --by title
awescholar updater search --json-file papers.json --by doi

# Search and write directly to project data JSON
awescholar updater search --archive docs/data.json --by title

# Manually add a record (interactive prompt)
awescholar updater add --archive docs/data.json
```

Workflow for reviewed search:
1. `updater search --json-file papers.json` — search and save for review
2. Review and edit `papers.json` as needed
3. `updater update --direction new2old --input papers.json --archive docs/data.json` — merge when ready

### Updater README

Use when regenerating the README table from the project data JSON.

```bash
# Generate with backup (default)
awescholar updater readme --archive docs/data.json --readme readme.md

# Generate without backup
awescholar updater readme --archive docs/data.json --readme readme.md --no-backup

# Custom title and description
awescholar updater readme --archive docs/data.json --readme readme.md --title "My Project" --description "A curated list of papers"
```

Default backup creates `{readme}.{YYYYMMDD_HHMMSS}.bak` before overwriting.

### Updater Counts

Use when the repo is website-first (papers live on the website, README shows links and counts only). Refresh after every merge.

```bash
awescholar updater counts --archive docs/data.json
# updates readme.md + README.zh-CN.md in cwd; --readme <path> to target specific files
```

### Updater RSS

Use when generating an RSS feed from the project data JSON.

```bash
awescholar updater rss --archive docs/data.json -o docs/rss.xml
awescholar updater rss --archive docs/data.json -o docs/rss.xml --title "Paper Updates"
```

## Config Reference

```json
{
    "model_profiles": {
        "glm": { "api_key": "${GLM_API_KEY}", "base_url": "https://open.bigmodel.cn/api/paas/v4" }
    },
    "model": { "profile": "glm", "name": "glm-5.1" },
    "agent_models": null,
    "semantic_scholar": { "api_key": "${SEMANTICSCHOLAR_API_KEY}" },
    "search": {
        "query": "AI agent|large language model",
        "fields_of_study": ["Biology", "Medicine"],
        "publication_date": "2025-01-01:2025-05-30",
        "limit": 100, "include_abstracts": true
    },
    "filter": { "limit": 20, "research_interests": null },
    "output": { "db_path": "output", "report_filename": null },
    "pipeline": {
        "skip_search": false,
        "use_updater_json": false,
        "use_filtered_json": false,
        "existing_json_path": null,
        "merge_new_to_old": false,
        "data_json_path": null
    },
    "categories": ["Foundation Models", "Drug Discovery", "Single Cell Analysis"]
}
```

Key fields:
- **model.name**: Model name only (e.g. `glm-5.1`, `deepseek-chat`). The `openai/` prefix is auto-prepended.
- **model.base_url**: Required for non-default endpoints. Must be OpenAI-compatible.
- **model_profiles**: Reusable profile map. Referenced by `model.profile` or `agent_models.*.profile`.
- **agent_models**: Per-agent overrides for annotator/filterer/reporter. `null` = use global model.
- **pipeline.data_json_path**: Long-lived curated project data JSON. When `merge_new_to_old` is true, filtered results auto-merge here after pipeline completes.
- **pipeline.existing_json_path**: Intermediate annotate output (`updater.json`). Different from `data_json_path`.
- **pipeline.skip_search / use_updater_json / use_filtered_json**: Flow control — see Crawler Pipeline section.
