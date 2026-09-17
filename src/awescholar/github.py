"""GitHub REST access: repository search, live metrics, URL parsing.

Used by the enrich step (paper → official repo, then stars) and the agentx
export. Mirrors the backfill module's plain-urllib, best-effort style.
"""

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.github.com"
USER_AGENT = "awescholar (https://github.com/wehuman01/awescholar)"
SEARCH_TIMEOUT_SECONDS = 20
REPO_TIMEOUT_SECONDS = 15
# Search is the scarce budget (10/min anonymous, 30/min authenticated);
# single-repo fetches only count against the far larger core pool.
SEARCH_PAUSE_ANON_SECONDS = 6.0
SEARCH_PAUSE_AUTH_SECONDS = 2.0

_GITHUB_URL_RE = re.compile(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")
_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", re.IGNORECASE)
_ARXIV_DOI_RE = re.compile(r"10\.48550/arxiv\.(\d{4}\.\d{4,5})", re.IGNORECASE)


def github_headers(token: str | None) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _api_get(path: str, token: str | None, timeout: float) -> dict | None:
    """GET an API path; return parsed JSON, or None on 404/transient failure."""
    req = urllib.request.Request(f"{API_BASE}{path}", headers=github_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            # A rate-limited call must not masquerade as "no results".
            print(f"Warning: GitHub API denied {path} (HTTP {exc.code}) — rate "
                  "limit or private resource; results may be missing.",
                  file=sys.stderr)
        return None
    except Exception:  # noqa: BLE001 — unknown repos and hiccups are normal outcomes
        return None


def owner_repo_from_url(url: str) -> str | None:
    """Extract 'owner/repo' from a github.com URL, or None."""
    if not url:
        return None
    match = _GITHUB_URL_RE.search(str(url))
    if not match:
        return None
    owner_repo = match.group(1)
    if any(part.endswith(".git") for part in owner_repo.split("/")):
        owner_repo = owner_repo.replace(".git", "")
    return owner_repo


def arxiv_id_from_paper(paper: dict) -> str:
    """Extract an arXiv ID from paperUrl/doi when one is present."""
    for key in ("paperUrl", "paper_url", "url"):
        match = _ARXIV_URL_RE.search(str(paper.get(key) or ""))
        if match:
            return match.group(1)
    match = _ARXIV_DOI_RE.search(str(paper.get("doi") or ""))
    if match:
        return match.group(1)
    return ""


def search_repositories(query: str, token: str | None, per_page: int = 5) -> list[dict]:
    """Search repositories; returns raw repo dicts (full_name, description, ...)."""
    url = f"/search/repositories?per_page={per_page}&q={urllib.parse.quote(query)}"
    data = _api_get(url, token, SEARCH_TIMEOUT_SECONDS)
    time.sleep(SEARCH_PAUSE_AUTH_SECONDS if token else SEARCH_PAUSE_ANON_SECONDS)
    return (data or {}).get("items") or []


def fetch_repo(owner_repo: str, token: str | None) -> dict | None:
    """Fetch one repository's current metrics; None when missing/unreachable."""
    return _api_get(f"/repos/{owner_repo}", token, REPO_TIMEOUT_SECONDS)


def stars_from_repo(repo: dict | None) -> int:
    return int((repo or {}).get("stargazers_count") or 0)
