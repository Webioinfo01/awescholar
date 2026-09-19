from __future__ import annotations

import re
from typing import Literal, NamedTuple, TypedDict

# --- Types -------------------------------------------------------------------

class PaperMeta(TypedDict):
    """Metadata subset of an awescholar paper record, stored as JSON on the agent."""
    title: str
    venue: str
    doi: str
    year: str
    authors: str
    firstAuthor: str
    paperUrl: str
    # Semantic Scholar citationCount; None when the record predates it.
    citations: int | None


class PaperClue(NamedTuple):
    """A resolvable paper identifier extracted from an agent record."""
    kind: Literal["doi", "arxiv", "s2", "title"]
    value: str


# --- Regexes -----------------------------------------------------------------

# arXiv IDs: new style 2505.20286 (with optional version), old style cs/0301012.
_ARXIV_URL = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", re.IGNORECASE)
_DOI_URL = re.compile(r"doi\.org/(10\.[^\s?#)]+)", re.IGNORECASE)
# Nature article pages carry the DOI suffix verbatim:
# nature.com/articles/s43588-026-01049-y ↔ 10.1038/s43588-026-01049-y.
_NATURE_URL = re.compile(
    r"(?:^|\.)nature\.com/articles/((?:10\.\d{4,5}/)?[^\s?#)]+)", re.IGNORECASE
)
_ARXIV_MENTION = re.compile(r"arxiv[:\s](\d{4}\.\d{4,5})", re.IGNORECASE)
# Semantic Scholar paper pages, bare (/paper/<40-hex paperId>) or slugged
# (/paper/<slug>/<paperId>) — the fallback paper link record.py writes when
# an S2 record carries no DOI yet.
_S2_PAPER_URL = re.compile(r"semanticscholar\.org/paper/(?:[a-z0-9-]+/)?([0-9a-f]{40})", re.IGNORECASE)
# Straight quotes and Unicode curly quotes used to delimit quoted titles.
_ANY_QUOTE = re.compile(r'["\u201c\u201d]')


# --- Clue extraction ----------------------------------------------------------

def extract_paper_clue(
    agent: dict[str, str | None],
) -> PaperClue | None:
    """The single most precise paper clue an agent record carries, in priority
    order: DOI in the paper URL, arXiv ID in the paper URL, Semantic Scholar
    paperId in the paper URL, arXiv mention in the description, arXiv in the
    homepage, verbatim quoted title in the description. Returns None when
    nothing precise is available.
    """
    paper = agent.get("paper") or ""

    m = _DOI_URL.search(paper)
    if m:
        return PaperClue(kind="doi", value=m.group(1).rstrip(".,;"))

    m = _NATURE_URL.search(paper)
    if m:
        doi = m.group(1)
        if not doi.startswith("10."):
            doi = f"10.1038/{doi}"
        return PaperClue(kind="doi", value=doi)

    m = _ARXIV_URL.search(paper)
    if m:
        return PaperClue(kind="arxiv", value=m.group(1))

    m = _S2_PAPER_URL.search(paper)
    if m:
        return PaperClue(kind="s2", value=m.group(1))

    m = _ARXIV_MENTION.search(agent.get("description") or "")
    if m:
        return PaperClue(kind="arxiv", value=m.group(1))

    m = _ARXIV_URL.search(agent.get("homepage") or "")
    if m:
        return PaperClue(kind="arxiv", value=m.group(1))

    # Split on quote characters and take the segments BETWEEN pairs — a
    # plain regex over quoted spans mis-pairs when a short quoted word
    # precedes the real title.
    segments = _ANY_QUOTE.split(agent.get("description") or "")
    for i in range(1, len(segments), 2):
        title = segments[i].strip()
        # A citable title has spaces; skip quoted URLs and short fragments.
        if len(title) < 12 or " " not in title or "http" in title:
            continue
        return PaperClue(kind="title", value=title)

    return None


# --- Conversions --------------------------------------------------------------

def arxiv_id_to_doi(id: str) -> str:
    """arXiv ID → its DataCite DOI form, the only ID form S2 resolves for preprints."""
    return f"10.48550/arXiv.{id}"


def clue_paper_url(clue: PaperClue, meta: PaperMeta | None) -> str | None:
    """Canonical URL for a resolved clue, used to fill a missing paper link."""
    if clue.kind == "doi":
        return f"https://doi.org/{clue.value}"
    if clue.kind == "arxiv":
        return f"https://arxiv.org/abs/{clue.value}"
    if clue.kind == "s2":
        return f"https://www.semanticscholar.org/paper/{clue.value}"
    return meta.get("paperUrl") if meta else None


# --- Title matching -----------------------------------------------------------

def _title_tokens(text: str) -> set[str]:
    """Tokenise lowercased text with naive plural folding.

    "Agents" and "Agent" must count as the same word when matching S2 titles
    against truncated clues.
    """
    out: set[str] = set()
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.add(t)
    return out


def title_match_ratio(clue: str, title: str) -> float:
    """How much of the clue title is covered by the record title:

    |clue ∩ record| / |clue|.  1 when every clue word appears in the record —
    the expected shape, since clues are usually exact or truncated titles.
    """
    clue_tokens = _title_tokens(clue)
    if not clue_tokens:
        return 0.0
    record_tokens = _title_tokens(title)
    hit = sum(1 for t in clue_tokens if t in record_tokens)
    return hit / len(clue_tokens)


# Acceptance thresholds
TITLE_MATCH_THRESHOLD: float = 0.7
"""Threshold for matching an S2 title-search result to a clue."""

DESCRIPTION_MATCH_THRESHOLD: float = 0.9
"""Stricter threshold for whole-description clues: a GitHub repo description
used as the paper title is a guess, so only a near-complete cover counts."""


def best_title_match(
    query: str,
    records: list[dict[str, str]],
    threshold: float = TITLE_MATCH_THRESHOLD,
) -> dict[str, str] | None:
    """Best S2 title-search record covering the query, None when none clears
    the threshold.  Whole-description clues use the stricter bar.

    A one-word "query" trivially scores 1.0 against any record containing it —
    too weak to identify a paper.  Require a phrase.

    Ties on the ratio: Python's max() keeps the FIRST maximal element, which
    matches the JS behaviour of sorting descending and taking index [0] when
    ratios are equal (the sort is not stable, so the choice is unspecified;
    max() is a deliberate, documented equivalent).
    """
    if len(_title_tokens(query)) < 3:
        return None

    candidates = [
        {"record": r, "ratio": title_match_ratio(query, r["title"])}
        for r in records
    ]
    passing = [c for c in candidates if c["ratio"] >= threshold]
    if not passing:
        return None
    return max(passing, key=lambda c: c["ratio"])["record"]


# --- Venue tier ---------------------------------------------------------------

PREPRINT_SERVER_RE = re.compile(
    r"arxiv|biorxiv|medrxiv|chemrxiv|agentrxiv|ssrn|preprints?\.org|\bosf\b", re.IGNORECASE
)
NON_VENUE_RE = re.compile(r"\bblog\b|website|homepage|github", re.IGNORECASE)
CONFERENCE_HINT_RE = re.compile(
    r"conference|symposium|workshop|proceedings"
    r"|neural information processing systems"
    r"|findings of"
    r"|\bICLR\b|\bNeurIPS\b|\bICML\b|\bCVPR\b|\bACL\b"
    r"|\bEMNLP\b|\bNAACL\b|\bAAAI\b|\bIJCAI\b|\bICDMW\b",
    re.IGNORECASE,
)


def venue_tier(venue: str) -> Literal["journal", "conference", "preprint"] | None:
    """Publication tier of a venue string, or None when it names no real venue
    (empty, or a non-venue source like a company blog).

    Classification is pattern-based and deliberately conservative: anything
    unrecognised that is not a preprint server counts as a journal.
    """
    v = venue.strip()
    if not v or NON_VENUE_RE.search(v):
        return None
    if PREPRINT_SERVER_RE.search(v):
        return "preprint"
    if CONFERENCE_HINT_RE.search(v):
        return "conference"
    return "journal"
