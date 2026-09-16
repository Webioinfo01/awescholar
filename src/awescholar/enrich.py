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
OWNER_MATCH_SCORE = 2
DESCRIPTION_SIMILARITY_SCORE = 3
# Academic repos often have an empty description and no arXiv citation, so the
# only officiality evidence is the name plus the community's verdict. A repo
# with the paper's system name and a decisive star lead over same-name rivals
# is the one the community already picked.
POPULARITY_MIN_STARS = 30
POPULARITY_STAR_RATIO = 5
# The description must restate the part of the title the repo/owner name
# cannot explain: enough rest tokens, most of them present.
DESCRIPTION_MIN_REST_TOKENS = 3
DESCRIPTION_SIMILARITY_THRESHOLD = 0.5

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
    "awesome lists, and repos that merely cite the paper do not count. The "
    "official repo is typically named after the paper's system and created "
    "around or after the paper; a candidate created or last pushed years "
    "before the paper is usually an unrelated older project that shares the "
    "name by coincidence. Reply "
    'with JSON: {"repo": "owner/name", "reason": "short justification"}. Use '
    "an empty repo string when none of the candidates is official."
)


def _repo_tokens(name: str) -> set[str]:
    """Camel/separator-split tokens plus the unsplit whole word, lowercased.

    Titles write system names as one word (BioAgent) while repos split them
    (bio-agent), and vice versa, so both forms are kept as evidence.
    """
    tokens = {m.group(0).lower() for m in _CAMEL_RE.finditer(name or "") if len(m.group(0)) >= 2}
    whole = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
    if len(whole) >= 2:
        tokens.add(whole)
    return tokens


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


def _score_candidate(title_tokens: set[str], arxiv_id: str, repo: dict,
                     arxiv_via_search: bool = False) -> int:
    """Heuristic evidence that a repo is the paper's official implementation.

    Core signal: the repo name derives from the title (official repos are
    named after the system the paper describes). Near-conclusive: the repo
    cites the paper's arXiv ID — directly, or by surfacing from the arXiv
    search (the index matched name, description, or README). Supporting:
    a dedicated owner (org named after the system) and a description that
    restates the paper title. No single signal clears the auto-accept bar —
    one corroborates another, and ambiguous races go to the LLM tiebreak.
    """
    distinctive = _repo_tokens(repo.get("name") or "") - GENERIC_REPO_WORDS
    description = str(repo.get("description") or "").lower()
    score = 0
    name_subset = bool(title_tokens and distinctive and distinctive <= title_tokens)
    if name_subset:
        score += 4
    elif distinctive & title_tokens:
        score += 1
    if arxiv_id and (arxiv_via_search
                     or arxiv_id.lower() in f"{repo.get('full_name') or ''} {description}".lower()):
        score += 4
    owner = _repo_tokens(str(repo.get("full_name") or "").split("/")[0]) - GENERIC_REPO_WORDS
    # Dedicated-org signal: every owner token is title-derived (an org named
    # after the system, MetaBeeAI), not a coincidental substring (ruby-grape).
    if owner and owner <= title_tokens:
        score += OWNER_MATCH_SCORE
    explained = distinctive | owner
    if title_tokens and _description_similarity(
            title_tokens, description, explained) >= DESCRIPTION_SIMILARITY_THRESHOLD:
        score += DESCRIPTION_SIMILARITY_SCORE
    topics = {t.lower() for t in repo.get("topics") or []}
    if distinctive & topics:
        score += 1
    repo["_name_subset"] = name_subset
    return score


def _description_similarity(title_tokens: set[str], description: str,
                            explained: set[str]) -> float:
    """How much of the title the description covers beyond the repo/owner name.

    Tokens already explained by the name are excluded, so echoing the repo
    name earns nothing — only title content the name cannot account for
    counts as the description restating the paper.
    """
    rest = title_tokens - explained
    if len(rest) < DESCRIPTION_MIN_REST_TOKENS:
        return 0.0
    words = set(re.findall(r"[a-z0-9]{2,}", description)) - STOPWORDS
    return len(rest & words) / len(rest)


def _popularity_accept(best: dict, ranked: list, paper_year: int | None) -> bool:
    """Exact system name plus a decisive star lead over every same-name rival.

    Catches real official repos whose bare description defeats description-
    based corroboration; the star gap substitutes for it. A repo created
    years before the paper is a name collision (an older tool sharing the
    system name), not the paper's code.
    """
    if not best.get("_name_subset"):
        return False
    stars = int(best.get("stargazers_count") or 0)
    if stars < POPULARITY_MIN_STARS:
        return False
    if paper_year is not None:
        created = str(best.get("created_at") or "")[:4]
        if not created or int(created) < paper_year - 1:
            return False
    rival_stars = max((int(c.get("stargazers_count") or 0) for _, c in ranked[1:]), default=0)
    return stars >= POPULARITY_STAR_RATIO * max(rival_stars, 1)


def _auto_pick(title_tokens: set[str], arxiv_id: str, candidates: list[dict],
               paper_year: int | None = None) -> dict | None:
    """Return the clear heuristic winner, or None when the race is ambiguous."""
    ranked = sorted(
        ((_score_candidate(title_tokens, arxiv_id, c,
                           arxiv_via_search=c.get("_arxiv_via_search", False)), c)
         for c in candidates),
        key=lambda pair: -pair[0],
    )
    best_score, best = ranked[0]
    if best_score < AUTO_ACCEPT_SCORE:
        return best if _popularity_accept(best, ranked, paper_year) else None
    if len(ranked) > 1 and best_score - ranked[1][0] < SCORE_MARGIN:
        return best if _popularity_accept(best, ranked, paper_year) else None
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
                "created": str(c.get("created_at") or "")[:10],
                "pushed": str(c.get("pushed_at") or "")[:10],
                "topics": c.get("topics") or [],
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


def _system_name(title: str) -> str:
    """The leading system name of a 'Name: description' title, or ''. Repos
    are named after the system, and GitHub's phrase search over the full
    title misses repos whose metadata only carries the name."""
    head = re.split(r"[:：—–]", str(title or ""), maxsplit=1)[0].strip()
    if 2 <= len(head) <= 40 and len(head.split()) <= 5:
        return head
    return ""


def resolve_repo(paper: dict, token: str | None, model: str = "",
                 api_key: str | None = None, base_url: str | None = None) -> dict | None:
    """Find the official GitHub repository for a paper, or None.

    Search rounds: arXiv ID (a hit there means the repo cites the ID in its
    name, description, or README), leading system name, full title. Clear
    heuristic winners are accepted directly; ambiguous races go to the LLM
    when one is configured.
    """
    arxiv_id = arxiv_id_from_paper(paper)
    title_tokens = _title_tokens(paper.get("title") or "")
    year = str(paper.get("year") or "")[:4]
    paper_year = int(year) if year.isdigit() else None
    queries = []
    if arxiv_id:
        fields = "name,description,readme" if token else "name,description"
        queries.append((f'"{arxiv_id}" in:{fields}', True))
    name = _system_name(paper.get("title") or "")
    if name:
        queries.append((f'"{name}" in:name,description', False))
    if paper.get("title"):
        queries.append((f'"{paper["title"]}" in:name,description', False))

    for query, via_arxiv in queries:
        candidates = search_repositories(query, token)
        if via_arxiv:
            for c in candidates:
                c["_arxiv_via_search"] = True
        if not candidates:
            continue
        pick = _auto_pick(title_tokens, arxiv_id, candidates, paper_year)
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
