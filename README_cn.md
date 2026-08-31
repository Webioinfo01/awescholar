<div align="center">
  <img src="./logo/hero.png" alt="awescholar" width="800">
  <h1>awescholar: Scientific Literature Curator <a href="https://github.com/Webioinfo01/aweskill"><img src="https://raw.githubusercontent.com/Webioinfo01/aweskill/main/logo/aweskill-badge2.svg" alt="aweskill companion"></a></h1>
  <p><strong>AI agent 可自主执行的科学文献发现与策展。</strong></p>
  <p>搜索、标注、筛选和报告学术论文 — 告诉你的 agent 去做，或者自己跑 CLI。</p>
  <p>
    <a href="./README.md">English</a> ·
    <strong>简体中文</strong> ·
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


> 搜索、标注、筛选和报告学术论文 — 告诉你的 agent 去做，或者自己跑 CLI。

一个轻量级 CLI 工具，自动化论文策展工作流：查询 Semantic Scholar、用 LLM 标注、按质量筛选、生成 Markdown 报告，并增量合并到长期维护的项目数据 JSON。同时支持人类和 AI agent 操作 — 安装 skill 后，你的 coding agent 可以通过自然语言指令执行完整流水线。

## awescholar 驱动的项目

- **[Awesome AI Meets Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology)** — AI × 生物学论文策展，由 awescholar 驱动自动发现、筛选和 README 更新。

## 安装

### 让 AI agent 安装

如果你在 Claude Code、Codex、Cursor 等 coding agent 中工作，直接告诉它：

```text
Read https://github.com/Webioinfo01/awescholar/blob/main/README.ai.md and follow it to install awescholar for this agent.
```

Agent 会先安装 `awescholar` CLI，然后在下面两种 awescholar skill 管理方式中选择一种：

1. **通过 [aweskill](https://aweskill.webioinfo.top/)** — 从 GitHub 安装和管理 skill，支持更新、投影和备份。需要 Node.js。由 [aweskill](https://aweskill.webioinfo.top/) 驱动 — AI 编程 Agent 的通用 skill 管理器。
2. **直接复制** — 将 `SKILL.md` 下载到 agent 的 skill 目录。除 Python 外无需额外依赖，但后续更新需要手动重新复制。

### pip

```bash
pip install awescholar
```

## aweskill 支持

awescholar 由 [aweskill](https://github.com/Webioinfo01/aweskill) 驱动 — 一个以 CLI 为核心的 Skill 包管理器，AI agent 也能自己调用和维护。aweskill 负责 skill 的安装、更新、投影和备份，支持 47+ 编程 agent，包括 Claude Code、Codex、Cursor、Gemini CLI 等。

## 使用

### AI Agent

安装 awescholar skill（见上方[安装](#安装)），然后直接告诉你的 agent 做什么 — 无需手动操作 CLI。如果 agent 还没有配置好 `config.json` 或需要修改模型/搜索设置，参考下方[详细配置](#详细配置)。

**AI agent 能做什么：**

- 一键执行完整发现流水线：搜索、标注、筛选、报告
- 将新结果合并到项目数据 JSON 并重新生成 README
- 按标题或 DOI 搜索 Semantic Scholar 并添加论文到存档
- 为策展集合生成 RSS 订阅
- 独立重新运行任意流水线步骤，支持自定义输入

**你可以这样告诉你的 agent：**

> "搜索最近关于 AI agents in biology 的论文，筛选 top 20，更新 README。"

> "用我的 config 跑 awescholar 流水线，然后把结果合并到 docs/data.json。"

> "按 DOI 找到这篇论文，添加到项目数据 JSON 里。"

Agent 通过 [SKILL.md](resources/skills/awescholar/SKILL.md) 理解所有可用命令、配置选项和工作流。

### 人类使用

```bash
# 设置 API key（添加到 ~/.zshrc 或 ~/.bashrc 可持久保存）
export GLM_API_KEY="sk-..."
export SEMANTICSCHOLAR_API_KEY="your-key"   # 可选，不设则使用免费 tier

# 运行完整流水线
awescholar --config config.json crawler run

# 或直接传入搜索词
awescholar --config config.json crawler run "perturbation prediction|single cell" --date 2025-01-01:2025-05-30
```

完整命令参考见下方[命令](#命令)。

## 详细配置

从 [repo 根目录](https://github.com/Webioinfo01/awescholar/blob/main/config.example.json) 复制 `config.example.json` 并填入你的值 — 或直接设置环境变量，跳过配置文件。

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

`${VAR}` 模式在加载时从环境变量展开。

**`model.name`** — 只写模型名称，如 `glm-5.1`、`deepseek-chat`、`gpt-4o`。`openai/` 前缀会自动添加，不要手动写。

**`model_profiles`** — 可复用的 profile 映射。每个 profile 定义 `api_key` 和 `base_url`，通过 `model.profile` 或 `agent_models.*.profile` 引用，避免重复填写凭证。

**`agent_models`** — 按 agent 覆盖模型（annotator, filterer, reporter）。每个条目可用 `profile` 引用 `model_profiles`，或直接设置 `name`/`api_key`/`base_url`：
```json
"agent_models": {
    "annotator": { "profile": "deepseek", "name": "deepseek-chat" },
    "filterer":  { "profile": "glm", "name": "glm-5.1" },
    "reporter":  { "profile": "glm", "name": "glm-5.1" }
}
```

**`filter.research_interests`** — 可选字符串，描述研究兴趣，传给 filterer 做相关性加权。

**`pipeline`** — 控制流水线跳过/复用中间结果：
- `skip_search`: 从数据库加载论文而不是搜索
- `use_updater_json`: 复用已有的 `updater.json`（跳过搜索+标注）
- `use_filtered_json`: 复用已有的 `updater_filter.json`（直接生成报告）
- `existing_json_path`: 自定义 updater JSON 路径
- `merge_new_to_old`: 流水线结束后将筛选结果自动合并到项目数据 JSON
- `data_json_path`: `merge_new_to_old` 使用的项目数据 JSON 路径；当 `merge_new_to_old` 为 `true` 时必须设置

`existing_json_path` 和 `data_json_path` 是两个不同文件。`existing_json_path` 指向标注阶段的中间文件（`updater.json`），用于复用或写入 annotate 结果。`data_json_path` 指向长期维护的项目数据 JSON，在启用 `merge_new_to_old` 后接收筛选后的论文。

**`search.query`** — 如果设置了，`crawler run` 可以不传 CLI query 参数。

支持的 LLM 提供商：任何 OpenAI 兼容 API（通过 `base_url`），如 GLM、DeepSeek、Gemini、Mistral、本地端点。

## 命令

```bash
awescholar -v                                         # 显示版本

# 脚手架：一键生成新的精选论文列表仓库
awescholar init                                       # 在当前目录生成 website-first 仓库（默认 Awesome-AI-Meets-Biology 身份）
awescholar init awesome-ai-foo                        # 生成到子目录
awescholar init --template vt                         # Awesome-AI-Virtual-Tumor 风格网站（默认 bio）
awescholar init --title "Awesome AI Foo" --github-repo Webioinfo01/Awesome-AI-Foo \
                 --website http://foo.webioinfo.top/ --category "AI Agents" --category Reviews
awescholar init --no-zh --no-branding                 # 仅英文 README、不含生态/赞赏区块
awescholar init --tables                              # 经典模式：同时内嵌 README 表格 marker

# 论文发现流水线
awescholar crawler search "query"                     # 搜索 Semantic Scholar
awescholar crawler annotate                           # 标注数据库中的论文
awescholar crawler annotate --input papers.json       # 从 JSON 标注（跳过 DB）
awescholar crawler filter --limit 20                  # 选择 top 论文
awescholar crawler filter --input updater.json        # 从自定义 JSON 筛选
awescholar crawler report                             # 生成报告（输出到 stdout）
awescholar crawler report updater_filter.json -o report.md  # 从自定义 JSON 生成报告
awescholar crawler run ["query"]                      # 完整流水线（如 config 已设 query 则可省略）

# 存档管理
awescholar updater update --direction new2old --input X --archive data.json  # 合并到项目数据 JSON
awescholar updater readme --archive data.json         # 生成 README 表格（自动备份）
awescholar updater readme --archive data.json --no-backup  # 生成 README 不备份
awescholar updater counts --archive data.json         # 刷新 website-first README 的论文计数
awescholar updater rss --archive data.json            # 生成 RSS 订阅
awescholar updater search --json-file papers.json --by title   # 搜索并保存待审阅
awescholar updater search --archive data.json --by title       # 搜索并直接添加
awescholar updater add --archive data.json            # 交互式添加单条记录到项目数据 JSON
```

每个子命令都支持 `--input`（report 用位置参数）指定输入文件，无需重跑完整流水线即可独立执行任意步骤。

`updater readme` 只更新 `<!-- AWESCHOLAR:START -->` 和 `<!-- AWESCHOLAR:END -->` 之间的自动生成区域。这个区域包含 awescholar 生成的目录和分类表格。自定义标题、引用和项目介绍应放在 marker 外。已有 README 如果没有这些 marker，会直接报错，避免整文件覆盖。如果 README 还不存在，`--title` 用来控制生成文件的一级标题。

当不指定 `--readme` 时，`updater readme` 会自动发现当前工作目录下所有包含 `<!-- AWESCHOLAR:START -->` 标记的 `README*.md` / `readme*.md` 文件并逐一更新。这适用于维护多语言 README（如 `readme.md` + `README.zh-CN.md`）— 表格内容自动保持同步。

`awescholar init` 一条命令生成完整的 website-first 仓库（类似 [Awesome-AI-Meets-Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology)）：中英双语落地页 README、带搜索和统计的网站（`--template bio` 或 `--template vt`）、接入 `config.json` 的空 `docs/data.json`、RSS 订阅、MPL-2.0 `LICENSE`、`CONTRIBUTING.md` 和 `.gitignore`。`--website` 传入自定义域名时会额外写入 `docs/CNAME`（GitHub Pages 用）。所有选项都可省略：在空目录里裸跑 `awescholar init` 即使用 Awesome-AI-Meets-Biology 的身份和默认值。对于论文数据只上网站（README 不内嵌表格）的仓库，合并新论文后运行 `awescholar updater counts --archive docs/data.json`，会刷新所有 README 里的分类计数、总数和 badge。

## 开发

详见 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) 了解开发环境搭建、架构、测试和代码风格。

```bash
pip install -e ".[dev]"
pytest
```

## 工作流

```
crawler search -> crawler annotate -> crawler filter -> crawler report
                                                        |
                                                        v
                                              updater_filter.json
                                    （或 merge_new_to_old=true 时自动合并）
                                                        |
                                  +---------------------+---------------------+
                                  |                                         |
                          updater update new2old                  updater search --json-file
                                  |                                         |
                                  v                                         v
                            data.json                               papers.json（审阅）
                                  |                                         |
                          updater readme / rss                    updater update new2old
                                                                          |
                                                                          v
                                                                    data.json
```

每个步骤生成一个 JSON 中间文件。你可以独立重新运行任何步骤。

## Awesome 软件生态

awescholar 是一个不断壮大的 "awesome" 工具家族中的一员 — 围绕 AI 编程 agent 打造，local-first、可被 agent 直接操作。

### CLI 工具

- **[aweskill](https://aweskill.webioinfo.top/)** — CLI 优先的技能包管理器，支持 47+ AI 编程 agent。
- **[aweswitch](https://github.com/Webioinfo01/aweswitch)** — Claude Code、Codex、OpenCode 的 agent 配置切换器。
- **[awerouter](https://github.com/mugpeng/awerouter)** — 智能路由器，用结构信号把请求分给 Flash 或 Pro 模型，减少不必要的模型开销。
- **[aweshelf](https://github.com/Webioinfo01/aweshelf)** — 收藏、分类、恢复 AI 编程会话，还能搭配 aweswitch 实现保存配置，一键启动。
- **[aweshare](https://github.com/wehuman01/aweshare)** — 通过自建 Hub 共享本地 Ollama/vLLM，或国产厂商 coding plan，或已授权的 OpenAI/Anthropic 帐号订阅，实现 token 的共享经济。
- **[awewarm](https://github.com/wehuman01/awewarm)** — 订阅窗口保持器，让 AI 编程套餐的窗口持续激活，无论是本地设置，还是通过远程连接的服务器。
- **[awescholar](https://github.com/Webioinfo01/awescholar)** — AI agent 可自主执行的科学文献发现与策展，搜索、标注、筛选和报告学术论文。

### 桌面应用

- **[awedot](https://awedot.wehuman.top/)** — 悬浮球驻留屏幕边缘，实时追踪当前 AI 会话；一键收藏、随时恢复，并可搭配 aweswitch 固定 agent 配置（比如用 GLM 模型启动）。

### Project Collections

- **[Awesome AI Meets Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology)** — AI 在生物学、生物信息学和生物医学研究中应用的精选综述。由 awescholar 驱动。
- **[Awesome AI Virtual Tumor](https://github.com/Webioinfo01/Awesome-AI-Virtual-Tumor)** — 面向虚拟肿瘤建模与仿真的前沿 AI 系统精选合集：静态模型、动态模型、agent、基准与综述。

## 赞助与支持

如果 awescholar 帮到了你，欢迎支持一下：

- ⭐ 给项目点个 Star — 让更多人看到它。
- ☕ [Ko-fi](https://ko-fi.com/mugpeng) — 请我喝杯咖啡。
- 💬 微信 — 扫描下方收款码。

<p align="center">
  <img src="assets/images/wechat-pay.jpg" alt="微信收款码" width="240">
</p>

> 你的支持让项目持续维护下去 — 谢谢。
