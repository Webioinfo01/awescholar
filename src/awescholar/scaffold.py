"""Scaffold a new curated paper-list repository (README + website + data skeleton)."""

import json
import os
import re
from datetime import datetime
from importlib.resources import files
from urllib.parse import urlparse

from .categories import normalize_category_name
from .readme import update_readme
from .rss import generate_rss

DEFAULT_TITLE = "Awesome AI Meets Biology"
DEFAULT_SUBTITLE = "A curated survey of AI applications in biology, bioinformatics, and biomedical research"
DEFAULT_SUBTITLE_ZH = "AI 在生物学、生物信息学和生物医学研究中应用的精选综述"
DEFAULT_WEBSITE = "http://awesomebio.webioinfo.top/"
DEFAULT_GITHUB_REPO = "Webioinfo01/Awesome-AI-Meets-Biology"
DEFAULT_CONTACT_EMAIL = "yc47680@um.edu.mo"
DEFAULT_CATEGORIES = ["AI Agents", "Foundation models", "Databases/Simulation", "Benchmarks", "Reviews"]

AWESKILL_BADGE_HTML = (
    ' <a href="https://github.com/Webioinfo01/aweskill">'
    '<img src="https://raw.githubusercontent.com/Webioinfo01/aweskill/main/logo/aweskill-badge2.svg"'
    ' alt="aweskill companion"></a>'
)

CATEGORY_ICONS = {
    "ai agents": "fa-robot",
    "foundation models": "fa-brain",
    "databases": "fa-database",
    "benchmarks": "fa-chart-bar",
    "reviews": "fa-book",
    "sequence models": "fa-dna",
    "drug models": "fa-pills",
    "static models": "fa-cube",
    "dynamic models": "fa-wave-square",
    "other models": "fa-cogs",
    "tools infrastructure": "fa-tools",
    "evaluation frameworks": "fa-balance-scale",
    "methodology": "fa-microscope",
    "other domain foundation models": "fa-globe",
    "paper before 2024": "fa-history",
}

CATEGORY_EMOJIS = {
    "ai agents": "🌟",
    "foundation models": "🎯",
    "databases": "💾",
    "benchmarks": "📊",
    "reviews": "📚",
    "sequence models": "🧬",
    "drug models": "💊",
    "static models": "📦",
    "dynamic models": "🌊",
    "other models": "🔧",
    "tools infrastructure": "🔧",
    "evaluation frameworks": "⚖️",
    "methodology": "🔬",
    "other domain foundation models": "🌐",
    "paper before 2024": "📜",
}

DEFAULT_TOPIC_BADGES = [
    ("fab fa-github", "Open Source"),
    ("fas fa-microscope", "Research"),
    ("fas fa-robot", "AI/ML"),
    ("fas fa-heartbeat", "Biology"),
]


def _read_template(rel: str) -> str:
    resource = files("awescholar") / "templates" / rel
    return resource.read_text(encoding="utf-8")


def _read_template_bytes(rel: str) -> bytes:
    resource = files("awescholar") / "templates" / rel
    return resource.read_bytes()


def slugify(name: str) -> str:
    """Mirror the website JS categoryToSectionId: lowercase, non-alnum runs -> '-', trimmed."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "category"


def _category_icon(name: str) -> str:
    return CATEGORY_ICONS.get(normalize_category_name(name), "fa-folder")


def _category_emoji(name: str) -> str:
    return CATEGORY_EMOJIS.get(normalize_category_name(name), "📄")


def _render(template: str, mapping: dict) -> str:
    content = template
    for key, value in mapping.items():
        content = content.replace("{{" + key + "}}", str(value))
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", content)
    if leftover:
        raise ValueError(f"unresolved template placeholders: {sorted(set(leftover))}")
    return content


def _nav_links(website: str, zh: bool, branding: bool, english_first: bool) -> str:
    if english_first:
        entries = ["<strong>English</strong>"]
        if zh:
            entries.append('<a href="./README.zh-CN.md">简体中文</a>')
        entries.append(f'<a href="{website}">Website</a>')
        if branding:
            entries.append('<a href="https://we.webioinfo.top/">Webioinfo</a>')
    else:
        entries = ['<a href="./readme.md">English</a>', "<strong>简体中文</strong>"]
        entries.append(f'<a href="{website}">官网</a>')
        if branding:
            entries.append('<a href="https://we.webioinfo.top/">Webioinfo</a>')
    lines = [f"    {entry} ·" for entry in entries[:-1]]
    lines.append(f"    {entries[-1]}")
    return "\n".join(lines)


def _categories_sentence(categories: list[str], zh: bool) -> str:
    if zh:
        quoted = "、".join(f'"{name}"' for name in categories[:-1])
        quoted = f'{quoted}和"{categories[-1]}"' if quoted else f'"{categories[0]}"'
        return f"本仓库将内容分为 {len(categories)} 大类别：{quoted}。"
    quoted = ", ".join(f'"{name}"' for name in categories[:-1])
    quoted = f"{quoted} and \"{categories[-1]}\""
    return f"This repository organizes papers into {len(categories)} main categories: {quoted}."


def _category_bullets(categories: list[str], website: str, zh: bool) -> str:
    unit = "篇" if zh else "papers"
    base = website.rstrip("/")
    lines = [
        f"- {_category_emoji(name)} [{name}]({base}/#{slugify(name)}) — 0 {unit}"
        for name in categories
    ]
    return "\n".join(lines)


def _topic_badges_html() -> str:
    return "\n".join(
        f'                <span class="badge"><i class="{icon}"></i> {label}</span>'
        for icon, label in DEFAULT_TOPIC_BADGES
    )


def _stat_items(categories: list[str]) -> str:
    blocks = []
    for name in categories:
        slug = slugify(name)
        blocks.append(
            f'                <div class="stat-item">\n'
            f'                    <div class="stat-number" id="{slug}-count"></div>\n'
            f'                    <div class="stat-label">{name}</div>\n'
            f"                </div>"
        )
    return "\n".join(blocks)


def _nav_tabs(categories: list[str]) -> str:
    blocks = []
    for name in categories:
        slug = slugify(name)
        blocks.append(
            f'            <a href="#{slug}" class="nav-tab" data-section="{slug}">\n'
            f'                <i class="fas {_category_icon(name)}"></i> {name} '
            f'(<span id="{slug}-nav-count"></span>)\n'
            f"            </a>"
        )
    return "\n".join(blocks)


def _category_sections(categories: list[str]) -> str:
    blocks = []
    for name in categories:
        slug = slugify(name)
        blocks.append(
            f"                <!-- {name} Section -->\n"
            f'                <section class="section" id="{slug}">\n'
            f'                    <div class="section-header">\n'
            f'                        <i class="fas {_category_icon(name)}"></i>\n'
            f'                        <h2 class="section-title">{name}</h2>\n'
            f'                        <span class="section-count" id="{slug}-section-count"></span>\n'
            f"                    </div>\n"
            f'                    <div class="table-container">\n'
            f'                        <table class="data-table">\n'
            f"                            <thead>\n                                <tr>\n"
            f"                                    <th>Year</th>\n"
            f"                                    <th>Title</th>\n"
            f"                                    <th>Team</th>\n"
            f"                                    <th>Domain</th>\n"
            f"                                    <th>Venue</th>\n"
            f"                                    <th>Links</th>\n"
            f"                                </tr>\n                            </thead>\n"
            f'                            <tbody id="{slug}-tbody">\n'
            f"                                <!-- Data will be populated by JavaScript -->\n"
            f"                            </tbody>\n"
            f"                        </table>\n"
            f"                    </div>\n"
            f"                </section>"
        )
    return "\n\n".join(blocks)


def _category_metadata_js(categories: list[str]) -> str:
    def js_escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("'", "\\'")

    lines = ["{"]
    lines.append("            'all-projects': { icon: 'fa-list', name: 'All Entries' },")
    for name in categories:
        lines.append(
            f"            '{slugify(name)}': {{ icon: '{_category_icon(name)}',"
            f" name: '{js_escape(name)}' }},"
        )
    lines.append("        }")
    return "\n".join(lines)


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def run_init(
    target_dir: str = ".",
    title: str | None = None,
    subtitle: str | None = None,
    github_repo: str | None = None,
    website: str | None = None,
    contact_email: str | None = None,
    template: str = "bio",
    categories: list[str] | None = None,
    include_zh: bool = True,
    branding: bool = True,
    embed_tables: bool = False,
    force: bool = False,
) -> list[str]:
    """Create a website-first curated paper-list repository; returns created file paths."""
    if template not in ("bio", "vt"):
        raise ValueError(f"unknown template: {template!r} (expected 'bio' or 'vt')")

    target = os.path.abspath(target_dir)
    if os.path.exists(target) and os.listdir(target) and not force:
        raise FileExistsError(f"target directory is not empty: {target} (use --force to proceed)")
    os.makedirs(target, exist_ok=True)

    title = title or DEFAULT_TITLE
    subtitle = subtitle or DEFAULT_SUBTITLE
    subtitle_zh = DEFAULT_SUBTITLE_ZH if subtitle == DEFAULT_SUBTITLE else subtitle
    github_repo = github_repo or DEFAULT_GITHUB_REPO
    website = website or DEFAULT_WEBSITE
    contact_email = contact_email or DEFAULT_CONTACT_EMAIL
    categories = categories or list(DEFAULT_CATEGORIES)

    owner = github_repo.split("/")[0]
    github_url = f"https://github.com/{github_repo}"
    now = datetime.now()
    counts = {name: [] for name in categories}
    total = sum(len(papers) for papers in counts.values())

    common = {
        "TITLE": title,
        "SUBTITLE": subtitle,
        "SUBTITLE_ZH": subtitle_zh,
        "DESCRIPTION": subtitle,
        "TAGLINE": subtitle,
        "WEBSITE": website,
        "WEBSITE_ENCODED": website.replace("/", "%2F").replace(":", "%3A").replace("-", "%2D"),
        "GITHUB_URL": github_url,
        "GITHUB_README_URL": f"{github_url}/blob/main/readme.md",
        "GITHUB_REPO_URL": github_url,
        "GITHUB_REPO_PATH": github_repo,
        "GITHUB_REPO_PATH_DOT": github_repo.replace("/", "."),
        "CONTACT_EMAIL": contact_email,
        "AUTHOR": owner,
        "YEAR": str(now.year),
        "YEAR_MONTH": now.strftime("%Y.%m"),
        "N_CATEGORIES": str(len(categories)),
        "TOTAL": str(total),
        "BIBTEX_KEY": re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower(),
        "LOADING_TEXT": f"Loading {title} projects...",
        "AWESKILL_BADGE": AWESKILL_BADGE_HTML if branding else "",
        "NAV_LINKS": _nav_links(website, include_zh, branding, english_first=True),
        "NAV_LINKS_ZH": _nav_links(website, include_zh, branding, english_first=False),
        "CATEGORIES_SENTENCE": _categories_sentence(categories, zh=False),
        "CATEGORIES_SENTENCE_ZH": _categories_sentence(categories, zh=True),
        "CATEGORY_BULLETS": _category_bullets(categories, website, zh=False),
        "CATEGORY_BULLETS_ZH": _category_bullets(categories, website, zh=True),
        "TOPIC_BADGES": _topic_badges_html(),
        "TABLES_BLOCK": (
            "\n<!-- AWESCHOLAR:START -->\n<!-- AWESCHOLAR:END -->\n" if embed_tables else ""
        ),
    }

    branding_en = _render(_read_template("readme_branding_en.md.tmpl"), common) if branding else ""
    branding_zh = _render(_read_template("readme_branding_zh.md.tmpl"), common) if branding else ""
    common["BRANDING_SECTIONS"] = branding_en
    common["BRANDING_SECTIONS_ZH"] = branding_zh

    if template == "bio":
        site = _render(
            _read_template("website_bio/index.html.tmpl"),
            {
                **common,
                "STAT_ITEMS": _stat_items(categories),
                "NAV_TABS": _nav_tabs(categories),
                "CATEGORY_SECTIONS": _category_sections(categories),
            },
        )
    else:
        site = _render(
            _read_template("website_vt/index.html.tmpl"),
            {**common, "CATEGORY_METADATA_JS": _category_metadata_js(categories)},
        )

    created = []
    _write(os.path.join(target, "readme.md"), _render(_read_template("readme_en.md.tmpl"), common))
    created.append("readme.md")
    if include_zh:
        _write(
            os.path.join(target, "README.zh-CN.md"),
            _render(_read_template("readme_zh.md.tmpl"), common),
        )
        created.append("README.zh-CN.md")

    _write(
        os.path.join(target, "CONTRIBUTING.md"),
        _read_template("contributing.md.tmpl"),
    )
    created.append("CONTRIBUTING.md")
    _write(os.path.join(target, "LICENSE"), _read_template("license_mpl2.txt"))
    created.append("LICENSE")
    _write(os.path.join(target, ".gitignore"), _read_template("gitignore.tmpl"))
    created.append(".gitignore")

    categories_json = json.dumps(categories, indent=4, ensure_ascii=False)
    config = _read_template("config.json.tmpl").replace("{{CATEGORIES_JSON}}", categories_json)
    _write(os.path.join(target, "config.json"), config)
    created.append("config.json")

    _write(os.path.join(target, "docs", "index.html"), site)
    created.append("docs/index.html")

    data_path = os.path.join(target, "docs", "data.json")
    with open(data_path, "w", encoding="utf-8") as handle:
        json.dump(counts, handle, indent=2, ensure_ascii=False)
    created.append("docs/data.json")

    generate_rss(
        data_path,
        os.path.join(target, "docs", "rss.xml"),
        title=f"{title} Updates",
        link=website,
        rss_url=f"{website}rss.xml" if website.endswith("/") else f"{website}/rss.xml",
    )
    created.append("docs/rss.xml")

    hostname = urlparse(website).hostname or ""
    if hostname and not hostname.endswith(".github.io"):
        _write(os.path.join(target, "docs", "CNAME"), hostname + "\n")
        created.append("docs/CNAME")

    if branding:
        image_path = os.path.join(target, "assets", "images", "wechat-pay.jpg")
        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        with open(image_path, "wb") as handle:
            handle.write(_read_template_bytes("assets/wechat-pay.jpg"))
        created.append("assets/images/wechat-pay.jpg")

    if embed_tables:
        update_readme(data_path, os.path.join(target, "readme.md"),
                      project_title=title, no_backup=True)

    return created
