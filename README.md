<div align="center">
  <img src="./logo/hero.png" alt="awescholar" width="800">
  <h1>awescholar: Scientific Literature Curator <a href="https://github.com/Webioinfo01/aweskill"><img src="https://raw.githubusercontent.com/Webioinfo01/aweskill/main/logo/aweskill-badge2.svg" alt="aweskill companion"></a></h1>
  <p><strong>AI-agent-operable scientific literature discovery and curation.</strong></p>
  <p>Search, annotate, filter, and report on academic papers — tell your agent to do it, or run the CLI yourself.</p>
  <p>
    <strong>English</strong> ·
    <a href="./README_cn.md">简体中文</a> ·
    <a href="https://we.webioinfo.top/">Webioinfo</a>
  </p>
  <p>
    <img src="https://img.shields.io/pypi/v/awescholar?style=flat-square&color=7C3AED" alt="Version">
    <img src="https://img.shields.io/badge/python-%E2%89%A53.11-0EA5E9?style=flat-square" alt="Python">
  </p>
  <p>
    <img src="https://img.shields.io/badge/status-alpha-c96a3d?style=flat-square" alt="Status">
    <img src="https://img.shields.io/badge/install-pip-22C55E?style=flat-square" alt="pip install">
    <img src="https://img.shields.io/badge/platform-cli-334155?style=flat-square" alt="Platform">
    <img src="https://img.shields.io/pypi/dm/awescholar?style=flat-square" alt="PyPI downloads">
    <img src="https://img.shields.io/github/stars/Webioinfo01/awescholar?style=flat-square" alt="GitHub stars">
  </p>
</div>


> Search, annotate, filter, and report on academic papers — tell your agent to do it, or run the CLI yourself.

A lightweight CLI that automates the paper curation workflow: query Semantic Scholar, annotate with LLM, filter by quality, generate Markdown reports, and incrementally merge into a maintained project data JSON. Designed for both human and AI-agent operation — install the skill, and your coding agent can run the entire pipeline from natural-language requests.

## Powered by awescholar

- **[Awesome AI Meets Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology)** — AI x biology paper curation powered by awescholar for automated discovery, filtering, and README updates.

## Install

### Ask an AI agent

If you are working inside Claude Code, Codex, Cursor, or another coding agent, tell it:

```text
Read https://github.com/Webioinfo01/awescholar/blob/main/README.ai.md and follow it to install awescholar for this agent.
```

The agent will first install the `awescholar` CLI, then choose one of two awescholar skill management options:

1. **Via [aweskill](https://aweskill.webioinfo.top/)** — installs and manages the skill from GitHub with update, projection, and backup support. Requires Node.js. Powered by [aweskill](https://aweskill.webioinfo.top/) — the universal skill manager for AI coding agents.
2. **Direct copy** — downloads `SKILL.md` into the agent's skill directory. No extra dependencies beyond Python, but future updates require copying the file again manually.

### pip

```bash
pip install awescholar
```

## Supported by aweskill

awescholar is powered by [aweskill](https://github.com/Webioinfo01/aweskill) — a CLI-first skill package manager that AI agents can operate themselves. aweskill handles skill installation, updates, projection, and backup across 47+ coding agents including Claude Code, Codex, Cursor, Gemini CLI, and more.

## Usage

### AI Agent

Install the awescholar skill (see [Install](#install)), then just tell your agent what to do — no manual CLI steps needed. If the agent hasn't configured `config.json` yet or you need to change model/search settings, see [Detailed Config](#detailed-config) below.

**What an AI agent can do:**

- Run the full discovery pipeline: search, annotate, filter, report — in one command
- Merge new results into the project data JSON and regenerate the README
- Search Semantic Scholar by title or DOI and add papers to the archive
- Generate RSS feeds for curated collections
- Re-run any pipeline step independently with custom input

**Example requests:**

> "Search for recent papers about AI agents in biology, filter the top 20, and update the README."

> "Run the awescholar pipeline with my config, then merge the results into docs/data.json."

> "Find this paper by DOI and add it to the project data JSON."

The agent uses the [SKILL.md](resources/skills/awescholar/SKILL.md) to understand all available commands, config options, and workflows.

### Human

```bash
# Set API keys (add to ~/.zshrc or ~/.bashrc to persist)
export GLM_API_KEY="sk-..."
export SEMANTICSCHOLAR_API_KEY="your-key"   # optional, without it uses free tier

# Run the full pipeline
awescholar --config config.json crawler run

# Or pass query directly
awescholar --config config.json crawler run "perturbation prediction|single cell" --date 2025-01-01:2025-05-30
```

See [Commands](#commands) below for the full CLI reference.

## Detailed Config

Copy `config.example.json` from the [repo root](https://github.com/Webioinfo01/awescholar/blob/main/config.example.json) and fill in your values — or set env vars directly and skip the config file.

```json
{
    "model_profiles": {
        "glm": {
            "api_key": "${GLM_API_KEY}",
            "base_url": "https://open.bigmodel.cn/api/paas/v4"
        },
        "deepseek": {
            "api_key": "${DEEPSEEK_API_KEY}",
            "base_url": null
        }
    },
    "model": {
        "profile": "glm",
        "name": "glm-5.1"
    },
    "agent_models": null,
    "semantic_scholar": {
        "api_key": "${SEMANTICSCHOLAR_API_KEY}"
    },
    "search": {
        "query": "AI agent|large language model|foundation model",
        "fields_of_study": ["Biology", "Medicine", "Computer Science"],
        "publication_date": "2025-01-01:2025-05-30",
        "limit": 100,
        "include_abstracts": true
    },
    "filter": {
        "limit": 20,
        "research_interests": null
    },
    "output": {
        "db_path": "output",
        "report_filename": null
    },
    "pipeline": {
        "skip_search": false,
        "use_updater_json": false,
        "use_filtered_json": false,
        "existing_json_path": null,
        "merge_new_to_old": false,
        "data_json_path": null
    },
    "categories": ["Foundation Models", "Drug Discovery", "Perturbation Study"]
}
```

`${VAR}` patterns are expanded from environment variables at load time.

**`model.name`** — just the model name, e.g. `glm-5.1`, `deepseek-chat`, `gpt-4o`. The `openai/` prefix is auto-prepended for OpenAI-compatible endpoints — do NOT add it manually.

**`model_profiles`** — reusable profile map. Each profile defines `api_key` and `base_url`. Referenced by `model.profile` or `agent_models.*.profile`, avoiding credential duplication.

**`agent_models`** — override model per agent (annotator, filterer, reporter). Each entry can use `profile` to reference a `model_profiles` entry, or set `name`/`api_key`/`base_url` directly:
```json
"agent_models": {
    "annotator": { "profile": "deepseek", "name": "deepseek-chat" },
    "filterer":  { "profile": "glm", "name": "glm-5.1" },
    "reporter":  { "profile": "glm", "name": "glm-5.1" }
}
```

**`pipeline`** — control flow to skip/reuse intermediate results:
- `skip_search`: load papers from DB instead of searching
- `use_updater_json`: reuse existing `updater.json` (skip search + annotate)
- `use_filtered_json`: reuse existing `updater_filter.json` (skip to report)
- `existing_json_path`: custom path for updater JSON
- `merge_new_to_old`: auto-merge filtered results into your project data JSON after pipeline
- `data_json_path`: project data JSON path used by `merge_new_to_old`; required when `merge_new_to_old` is `true`

`existing_json_path` and `data_json_path` are different files. `existing_json_path` points to the annotation intermediate file (`updater.json`) used to resume or write the annotate step. `data_json_path` points to the long-lived curated project data JSON that receives filtered papers when `merge_new_to_old` is enabled.

**`filter.research_interests`** — optional string describing research focus, passed to filterer for relevance weighting.

**`search.query`** — if set, `crawler run` can be called without a CLI query argument.

Supported LLM providers: any OpenAI-compatible API via `base_url` (e.g. GLM, DeepSeek, Gemini, Mistral, local endpoints).

## Commands

```bash
awescholar -v                                         # Show version

# Paper discovery pipeline
awescholar crawler search "query"                     # Search Semantic Scholar
awescholar crawler annotate                           # Annotate papers in DB
awescholar crawler annotate --input papers.json       # Annotate from JSON (skip DB)
awescholar crawler filter --limit 20                  # Select top papers
awescholar crawler filter --input updater.json        # Filter from custom JSON
awescholar crawler report                             # Generate report (stdout)
awescholar crawler report updater_filter.json -o report.md  # Report from custom JSON
awescholar crawler run ["query"]                      # Full pipeline (query optional if set in config)

# Archive management
awescholar updater update --direction new2old --input X --archive data.json  # Merge to project data JSON
awescholar updater readme --archive data.json         # Generate README tables (with .bak backup)
awescholar updater readme --archive data.json --no-backup  # Generate README without backup
awescholar updater rss --archive data.json            # Generate RSS feed
awescholar updater search --json-file papers.json --by title   # Search, save for review
awescholar updater search --archive data.json --by title       # Search and add directly
awescholar updater search --archive data.json --category "AI Agents"  # Add to a specific category
awescholar updater add --archive data.json            # Interactively add a record to project data JSON
```

Each subcommand accepts `--input` (or positional `input` for report) to read from a specific file instead of the default path. This lets you re-run any step independently without re-running the full pipeline.

`updater readme` updates only the generated region between `<!-- AWESCHOLAR:START -->` and `<!-- AWESCHOLAR:END -->`. That generated region contains the awescholar table of contents and category tables. Keep custom headings, citation, and project text outside that region. Existing README files without those markers are rejected instead of being overwritten. If the README does not exist yet, `--title` controls the generated top-level heading.

When `--readme` is not specified, `updater readme` auto-discovers all `README*.md` / `readme*.md` files in the current working directory that contain `<!-- AWESCHOLAR:START -->` markers and updates each one. This is useful for maintaining multilingual READMEs (e.g., `readme.md` + `README.zh-CN.md`) — the table content stays in sync automatically.

## Development

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for setup, architecture, testing, and code style.

```bash
pip install -e ".[dev]"
pytest
```

## Workflow

```
crawler search -> crawler annotate -> crawler filter -> crawler report
                                                        |
                                                        v
                                              updater_filter.json
                                    (or auto-merge if merge_new_to_old=true)
                                                        |
                                  +---------------------+---------------------+
                                  |                                         |
                          updater update new2old                  updater search --json-file
                                  |                                         |
                                  v                                         v
                            data.json                               papers.json (review)
                                  |                                         |
                          updater readme / rss                    updater update new2old
                                                                          |
                                                                          v
                                                                    data.json
```

Each step produces a JSON intermediate file. You can re-run any step independently.
