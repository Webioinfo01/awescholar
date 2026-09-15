"""Enrich archive entries with GitHub repository links and live star counts.

Two jobs, one command:
1. Papers without a codeUrl are matched to their official GitHub repository
   (arXiv-ID search first, title search second; heuristic scoring with an
   optional LLM tiebreak for ambiguous cases).
2. Papers with a github.com codeUrl get their githubStars refreshed as a
   numeric count (legacy badge-URL values are migrated along the way).

Only empty codeUrl fields are filled; entries never move between categories.
"""

import json
import re
import shutil
from datetime import datetime

from pydantic import BaseModel

from .github import (
    arxiv_id_from_paper,
    fetch_repo,
    owner_repo_from_url,
    search_repositories,
    stars_from_repo,
)
from .llm import complete

AUTO_ACCEPT_SCORE = 5
SCORE_MARGIN = 2

STOPWORDS = {
    "the", "for", "and", "with", "from", "using", "toward", "towards", "via",
    "based", "new", "study", "approach", "framework", "leveraging", "under",
}
# Repo names made only of these words match almost any paper; they must not
# earn the name-subset bonus on their own.
GENERIC_REPO_WORDS = {
    "agent", "agents", "llm", "paper", "papers", "code", "benchmark",
    "benchmarks", "model", "models", "toolkit", "library", "ai", "deep",
}
_CAMEL_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")
_BADGE_URL_RE = re.compile(r"img\.shields\.io/github/stars/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")


class RepoPick(BaseModel):
    """LLM verdict on which candidate is the paper's official repository."""
    repo: str = ""
    reason: str = ""


REPO_PICK_SYSTEM = (
    "You link scientific papers to their official code repositories. Given a "
    "paper and candidate GitHub repositories, pick the one repository that is "
    "the authors' official implementation. Third-party reimplementations, "
    "awesome lists, and repos that merely cite the paper do not count. Reply "
    'with JSON: {"repo": "owner/name", "reason": "short justification"}. Use '
    "an empty repo string when none of the candidates is official."
)


def _repo_tokens(name: str) -> set[str]:
    return {m.group(0).lower() for m in _CAMEL_RE.finditer(name or "") if len(m.group(0)) >= 2}


def _title_tokens(title: str) -> set[str]:
    """Significant title words, camel-split so compound names match repo names.

    Paper titles write system names as one word (BioAgent) while repos
    camelCase or hyphenate them (bio-agent), so both forms are kept.
    """
    tokens: set[str] = set()
    for word in re.findall(r"[A-Za-z]{3,}", title or ""):
        parts = [word.lower()] + [p.lower() for p in _CAMEL_RE.findall(word)]
        for part in parts:
            if len(part) >= 2 and part not in STOPWORDS:
                tokens.add(part)
    return tokens


def _score_candidate(title_tokens: set[str], arxiv_id: str, repo: dict) -> int:
    """Heuristic evidence that a repo is the paper's official implementation.

    The official repo is normally named after the system the paper describes,
    so a repo name derivable from the title is the core signal; an arXiv ID
    cited by the repo itself is near-conclusive. Neither alone clears the
    auto-accept bar — one corroborates the other, and ambiguous races go to
    the LLM tiebreak instead.
    """
    distinctive = _repo_tokens(repo.get("name") or "") - GENERIC_REPO_WORDS
    description = str(repo.get("description") or "").lower()
    score = 0
    if title_tokens and distinctive and distinctive <= title_tokens:
        score += 4
    elif distinctive & title_tokens:
        score += 1
    if arxiv_id:
        blob = f"{repo.get('full_name') or ''} {description}".lower()
        if arxiv_id.lower() in blob:
            score += 4
    topics = {t.lower() for t in repo.get("topics") or []}
    if distinctive & topics:
        score += 1
    return score


def _auto_pick(title_tokens: set[str], arxiv_id: str, candidates: list[dict]) -> dict | None:
    """Return the clear heuristic winner, or None when the race is ambiguous."""
    ranked = sorted(
        ((_score_candidate(title_tokens, arxiv_id, c), c) for c in candidates),
        key=lambda pair: -pair[0],
    )
    best_score, best = ranked[0]
    if best_score < AUTO_ACCEPT_SCORE:
        return None
    if len(ranked) > 1 and best_score - ranked[1][0] < SCORE_MARGIN:
        return None
    return best


def _llm_pick(paper: dict, candidates: list[dict], model: str,
              api_key: str | None, base_url: str | None) -> dict | None:
    """Ask the configured LLM which candidate is official; None on no pick."""
    payload = {
        "paper": {
            "title": paper.get("title") or "",
            "team": paper.get("team") or "",
            "venue": paper.get("venue") or "",
            "year": paper.get("year") or "",
        },
        "candidates": [
            {
                "repo": c.get("full_name") or "",
                "stars": c.get("stargazers_count") or 0,
                "description": c.get("description") or "",
            }
            for c in candidates
        ],
    }
    try:
        pick = complete(
            model, REPO_PICK_SYSTEM, json.dumps(payload, ensure_ascii=False),
            response_format=RepoPick, api_key=api_key, base_url=base_url,
        )
    except Exception:  # noqa: BLE001 — one failed verdict must not abort the run
        return None
    wanted = (pick.repo or "").strip().lower()
    if not wanted:
        return None
    for c in candidates:
        if str(c.get("full_name") or "").lower() == wanted:
            return c
    return None


def resolve_repo(paper: dict, token: str | None, model: str = "",
                 api_key: str | None = None, base_url: str | None = None) -> dict | None:
    """Find the official GitHub repository for a paper, or None.

    arXiv-ID search first (repos citing the ID are near-matches), title
    search second. Clear heuristic winners are accepted directly; ambiguous
    races go to the LLM when one is configured.
    """
    arxiv_id = arxiv_id_from_paper(paper)
    title_tokens = _title_tokens(paper.get("title") or "")
    queries = []
    if arxiv_id:
        fields = "name,description,readme" if token else "name,description"
        queries.append(f'"{arxiv_id}" in:{fields}')
    if paper.get("title"):
        queries.append(f'"{paper["title"]}" in:name,description')

    for query in queries:
        candidates = search_repositories(query, token)
        if not candidates:
            continue
        pick = _auto_pick(title_tokens, arxiv_id, candidates)
        if pick is None and model and api_key:
            pick = _llm_pick(paper, candidates, model, api_key, base_url)
        return pick
    return None


def enrich_archive(archive_path: str, token: str | None = None, model: str = "",
                   api_key: str | None = None, base_url: str | None = None,
                   use_llm: bool = True, limit: int | None = None,
                   no_backup: bool = False, status_cb=print) -> dict:
    """Fill empty codeUrl fields and refresh numeric githubStars in place."""
    with open(archive_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    # Legacy entries store a shields.io badge URL in githubStars; the repo it
    # renders is itself the missing codeUrl.
    for papers in archive.values():
        for p in papers:
            if not p.get("codeUrl"):
                badge = _BADGE_URL_RE.search(str(p.get("githubStars") or ""))
                if badge:
                    p["codeUrl"] = f"https://github.com/{badge.group(1)}"

    to_resolve = []  # (category, entry)
    to_refresh = []  # (category, entry)
    for category, papers in archive.items():
        for p in papers:
            if not p.get("codeUrl"):
                if p.get("title"):
                    to_resolve.append((category, p))
            elif owner_repo_from_url(p["codeUrl"]):
                to_refresh.append((category, p))

    if limit is not None:
        to_resolve = to_resolve[:limit]

    llm_ready = use_llm and model and api_key
    status_cb(
        f"Resolving repositories for {len(to_resolve)} papers, "
        f"refreshing metrics for {len(to_refresh)} linked repos"
        + ("" if llm_ready else " (LLM tiebreak off — only clear matches resolve)")
    )

    resolved = 0
    for i, (_, p) in enumerate(to_resolve, 1):
        repo = resolve_repo(p, token, model if llm_ready else "",
                            api_key if llm_ready else None, base_url)
        if repo:
            p["codeUrl"] = repo.get("html_url") or f"https://github.com/{repo.get('full_name')}"
            p["githubStars"] = stars_from_repo(repo)
            resolved += 1
            status_cb(f"  [{i}/{len(to_resolve)}] {repo.get('full_name')}  <-  "
                      f"{str(p.get('title'))[:60]}")
        elif i % 10 == 0 or i == len(to_resolve):
            status_cb(f"  [{i}/{len(to_resolve)}] unresolved: {str(p.get('title'))[:60]}")

    refreshed = missing = 0
    for _, p in to_refresh:
        owner_repo = owner_repo_from_url(p["codeUrl"])
        repo = fetch_repo(owner_repo, token)
        if repo:
            p["githubStars"] = stars_from_repo(repo)
            refreshed += 1
        else:
            missing += 1
    if to_refresh:
        status_cb(f"Refreshed stars for {refreshed} repos"
                  + (f"; {missing} unreachable" if missing else ""))

    if not no_backup:
        ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{archive_path}.{ts}.bak"
        shutil.copy2(archive_path, backup_path)
        status_cb(f"Created backup: {backup_path}")

    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(archive, f, indent=2, ensure_ascii=False)

    return {
        "resolve_candidates": len(to_resolve),
        "resolved": resolved,
        "refresh_candidates": len(to_refresh),
        "refreshed": refreshed,
        "missing_repos": missing,
    }
