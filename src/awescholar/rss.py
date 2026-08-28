"""RSS feed generation from project archive data."""

import html
import json
import os
import re
from datetime import UTC, datetime


def _year_to_rfc822(year_str: str) -> str:
    """Convert '2025.12' or '2025-12' to RFC 822 date like 'Mon, 01 Dec 2025 00:00:00 GMT'."""
    if not year_str:
        return ""
    normalized = year_str.replace(".", "-")
    try:
        # Synthesized first-of-month date; pinned to UTC so the RFC 822 "GMT" label is honest
        dt = datetime.strptime(normalized[:7], "%Y-%m").replace(tzinfo=UTC)
        return dt.strftime("%a, %d %b %Y 00:00:00 GMT")
    except (ValueError, IndexError):
        return year_str


def _guid_from_paper(title: str, year: str) -> str:
    """Generate a stable guid: strip non-alpha, concat title+year."""
    clean = re.sub(r"[^a-zA-Z]", "", title)
    y = (year or "").replace(".", "")
    return f"{clean}{y}"


def generate_rss(
    archive_path: str,
    output_path: str,
    title: str = "Awesome Scholar Updates",
    link: str = "",
    description: str = "Latest papers from curated collection",
    rss_url: str = "",
):
    """Generate RSS feed from archive JSON.

    If the output file already exists, preserves its channel metadata
    (title, link, description, atom:link) unless explicitly overridden.
    """
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            existing = f.read()
        if title == "Awesome Scholar Updates":
            m = re.search(r"<title>(.*?)</title>", existing)
            if m:
                title = m.group(1)
        if not link:
            m = re.search(r"<link>(.*?)</link>", existing)
            if m:
                link = m.group(1)
        if description == "Latest papers from curated collection":
            m = re.search(r"<description>(.*?)</description>", existing, re.DOTALL)
            if m:
                description = m.group(1).strip()
        if not rss_url:
            m = re.search(r'<atom:link href="(.*?)"', existing)
            if m:
                rss_url = m.group(1)

    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    items = []
    for papers in archive.values():
        for p in papers:
            ptitle = p.get("title", "Untitled")
            team = p.get("team", "")
            domain = p.get("domain", "")
            venue = p.get("venue", "")
            doi = p.get("doi", "")
            year = p.get("year", "")
            paper_url = p.get("paperUrl", "") or (f"https://doi.org/{doi}" if doi else "")
            code_url = p.get("codeUrl", "")

            item_link = f"https://doi.org/{doi}" if doi else paper_url

            desc_parts = [f"<p><b>Team:</b> {html.escape(team)}</p>"]
            if domain:
                desc_parts.append(f"<p><b>Domain:</b> {html.escape(domain)}</p>")
            if venue:
                desc_parts.append(f"<p><b>Venue:</b> {html.escape(venue)}</p>")
            if paper_url:
                desc_parts.append(f'<p><a href="{html.escape(paper_url)}">Read the Paper</a></p>')
            if code_url:
                desc_parts.append(f'<p><a href="{html.escape(code_url)}">Code</a></p>')
            cdata = "\n        ".join(desc_parts)

            pub_date = _year_to_rfc822(year)
            guid = _guid_from_paper(ptitle, year)

            items.append(f"""  <item>
    <title>{html.escape(ptitle)}</title>
    <link>{html.escape(item_link)}</link>
    <description>
      <![CDATA[
        {cdata}
      ]]>
    </description>
    <pubDate>{pub_date}</pubDate>
    <guid isPermaLink="false">{guid}</guid>
  </item>""")

    now = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S GMT")
    atom_link = f'\n  <atom:link href="{html.escape(rss_url)}" rel="self" type="application/rss+xml" />' if rss_url else ""

    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{html.escape(title)}</title>
  <link>{html.escape(link)}</link>
  <description>{html.escape(description)}</description>
  <language>en-us</language>
  <lastBuildDate>{now}</lastBuildDate>{atom_link}
{chr(10).join(items)}
</channel>
</rss>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rss)

    return output_path
