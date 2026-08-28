# awescholar Bootstrap Protocol

This document is for AI coding agents. First install the `awescholar` CLI, then choose one of two ways to manage the awescholar skill for the current agent.

## Language Behavior

- Reply in the user's language when possible.
- If the user asks in Chinese, continue in Chinese.
- If the user asks in English, continue in English.

## Step 1: Install awescholar CLI

### Prerequisites

- Python >= 3.11 (`python3 --version`)
- pip available (`pip --version`)

If Python is missing, tell the user to install it from https://www.python.org/.

### Steps

#### 1. Install awescholar Python package

```bash
pip install awescholar
```

#### 2. Verify awescholar CLI

```bash
awescholar -v
```

Expected output: `awescholar X.Y.Z`

---

## Step 2: Install or manage the awescholar skill

Choose one of the following skill management options. Both options assume the `awescholar` CLI was installed in Step 1.

### Option A: Via aweskill (recommended if aweskill is available)

Use this option if the user already has aweskill installed, or is willing to install it. This gives full skill management — install, update, projection, backup.

#### Prerequisites

- Node.js >= 20 (`node --version`) — required by aweskill
- npm available (`npm --version`)

If Node.js is missing, tell the user to install it from https://nodejs.org/.

#### Steps

##### A1. Install aweskill (if not already installed)

```bash
npm install -g aweskill
```

##### A2. Initialize the aweskill central store (if not already done)

```bash
aweskill store init
```

##### A3. Install awescholar skill from GitHub

```bash
aweskill install Webioinfo01/awescholar
```

##### A4. Identify the current agent

```bash
aweskill agent supported
```

Look for lines marked with `✓`. Common agent ids: `claude-code`, `cursor`, `codex`, `gemini-cli`, `windsurf`, `opencode`, `qwen-code`.

If you cannot determine the agent id, ask the user.

##### A5. Project awescholar skill to this agent

```bash
aweskill agent add skill awescholar --global --agent <agent-id>
```

##### A6. Verify

```bash
aweskill agent list --global --agent <agent-id>
```

Expected: `awescholar` shows as `linked`.

---

### Option B: Direct copy (no aweskill needed)

Use this option if the user does not have aweskill and does not want to install Node.js. This copies the SKILL.md file directly into the agent's skill directory.

#### Prerequisites

- `curl` or `wget` available

#### Steps

##### B1. Identify the current agent's skill directory

Determine which agent is running and its global skill directory:

| Agent | Skill directory |
|---|---|
| Claude Code | `~/.claude/skills/awescholar/` |
| Codex | `~/.codex/skills/awescholar/` |
| Cursor | `.cursor/skills/awescholar/` (project-level) |
| Gemini CLI | `~/.gemini/skills/awescholar/` |
| Windsurf | `~/.windsurf/skills/awescholar/` |
| OpenCode | `~/.opencode/skills/awescholar/` |
| Qwen Code | `~/.qwen/skills/awescholar/` |

If the agent is not in this list, ask the user where to place the skill file.

##### B2. Download and place SKILL.md

```bash
mkdir -p <skill-directory>
curl -fsSL https://raw.githubusercontent.com/Webioinfo01/awescholar/main/resources/skills/awescholar/SKILL.md -o <skill-directory>/SKILL.md
```

Replace `<skill-directory>` with the path from step B1.

---

## Step 3: Configure awescholar

After installing the CLI and skill, set up the config file before running any pipeline.

#### 1. Copy the example config

```bash
cp config.example.json config.json
```

`config.example.json` is in the [awescholar repo root](https://github.com/Webioinfo01/awescholar/blob/main/config.example.json). If the repo is not available locally, download it:

```bash
curl -fsSL https://raw.githubusercontent.com/Webioinfo01/awescholar/main/config.example.json -o config.json
```

#### 2. Set API keys

```bash
export GLM_API_KEY="sk-..."
export SEMANTICSCHOLAR_API_KEY="your-key"   # optional, uses free tier without it
```

Or add them to `~/.zshrc` / `~/.bashrc` to persist. `${VAR}` patterns in `config.json` are expanded from environment variables at load time.

#### 3. Edit config.json

Key fields to check:
- **`model.name`** — model name (e.g. `glm-5.1`, `deepseek-chat`, `gpt-4o`). The `openai/` prefix is auto-prepended for OpenAI-compatible endpoints.
- **`model.base_url`** — required for non-default endpoints. Must be OpenAI-compatible.
- **`search.query`** — default search terms
- **`search.publication_date`** — date range filter

See the [Detailed Config](https://github.com/Webioinfo01/awescholar#detailed-config) section in the README for the full reference.

---

## Final Step (both options)

After setup, the agent needs to be restarted to pick up the new skill. Tell the user:

> awescholar is installed. Please restart this agent to activate the awescholar skill. After restart, you can ask me things like:
>
> - "Search for recent papers about AI agents in biology."
> - "Run the full awescholar pipeline with my config."
> - "Merge new results into the project data JSON and update the README."

If the user is speaking Chinese, use this version instead:

> awescholar 已安装。请重启当前 agent，以激活 awescholar skill。重启后你可以继续问我，例如：
>
> - "搜索最近关于 AI agents in biology 的论文。"
> - "用我的 config 跑一遍 awescholar 完整流水线。"
> - "把新结果合并到项目数据 JSON 里，更新 README。"

## Safety Rules

- If you cannot determine the agent id or skill directory, ask the user before proceeding.
- Do not copy skills to all agents by default. Only set up the current agent unless the user explicitly requests otherwise.
- If any command fails, report the exact command and error message to the user. Do not silently retry.
