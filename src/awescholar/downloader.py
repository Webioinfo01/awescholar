"""Download open-access PDFs for archive papers (or standalone DOIs/arXiv IDs).

Two sources, cheapest and most reliable first:
1. arXiv — records whose DOI is ``10.48550/arXiv.<id>`` or whose paperUrl
   points at ``arxiv.org/abs/<id>`` download from ``arxiv.org/pdf/<id>``.
2. OpenAlex — batched DOI lookup returning ``best_oa_location.pdf_url``.

Every candidate response is verified to start with ``%PDF`` — publisher
sites that answer with HTML (bot-gated pages such as cell.com) count as
failures, never as downloads. Files land in the output directory named
``<year>-<title-slug>.pdf`` and existing files are skipped, so re-runs are
idempotent. The archive itself is never modified.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .utils import matches_only

ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}"
OPENALEX_URL = "https://api.openalex.org/works"
OPENALEX_UA = "awescholar-downloader (https://github.com/wehuman01/awescholar)"
DOWNLOAD_UA = OPENALEX_UA
OPENALEX_TIMEOUT_SECONDS = 20
OPENALEX_PER_BATCH = 50
OPENALEX_PAUSE_SECONDS = 1.0
ARXIV_PAUSE_SECONDS = 1.0
PUBLISHER_PAUSE_SECONDS = 0.5
PDF_TIMEOUT_SECONDS = 60
MAX_PDF_BYTES = 200 * 1024 * 1024
SLUG_MAX_CHARS = 80

_ARXIV_DOI_RE = re.compile(r"10\.48550/arxiv\.(.+)", flags=re.IGNORECASE)
_ARXIV_URL_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+/\d{7})(?:v\d+)?",
    flags=re.IGNORECASE,
)


def arxiv_id_for(entry: dict) -> str | None:
    """Return the arXiv ID a record points at, or None.

    Recognized shapes: the DataCite DOI ``10.48550/arXiv.<id>`` and a
    paperUrl of the form ``arxiv.org/abs/<id>`` (or /pdf/). Version
    suffixes on old-style IDs are tolerated.
    """
    m = _ARXIV_DOI_RE.match((entry.get("doi") or "").strip())
    if m:
        return m.group(1)
    m = _ARXIV_URL_RE.search(entry.get("paperUrl") or "")
    if m:
        return m.group(1)
    return None


def slugify(text: str) -> str:
    """Lowercase filesystem-safe slug, collapsed hyphens, capped in length."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug[:SLUG_MAX_CHARS].rstrip("-") or "untitled"


def target_filename(entry: dict) -> str:
    """``<year>-<title-slug>.pdf`` with DOI/arXiv fallbacks for untitled records."""
    title = entry.get("title")
    year = str(entry.get("year") or "").split(".")[0]
    if title:
        base = f"{year}-{slugify(title)}" if year else slugify(title)
    elif entry.get("doi"):
        base = "doi-" + slugify(entry["doi"].replace("/", "_"))
    elif entry.get("arxiv"):
        base = f"arxiv-{entry['arxiv']}"
    else:
        base = "untitled"
    return f"{base}.pdf"


def _fetch_bytes(url: str, timeout: int) -> bytes:
    """Fetch a URL as bytes with the project User-Agent, capped in size."""
    req = urllib.request.Request(url, headers={"User-Agent": DOWNLOAD_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        chunks = []
        remaining = MAX_PDF_BYTES
        while remaining > 0:
            chunk = resp.read(min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


def openalex_pdf_urls(dois: list[str]) -> dict[str, dict]:
    """Batch-resolve DOIs to OpenAlex ``best_oa_location.pdf_url`` records.

    Returns ``{doi_lower: {"pdf_url": str, "title": str, "year": int}}``.
    Unreachable/throttled batches are skipped and reported by absence —
    a missing record is a normal outcome, not an error.
    """
    out: dict[str, dict] = {}
    for i in range(0, len(dois), OPENALEX_PER_BATCH):
        chunk = dois[i:i + OPENALEX_PER_BATCH]
        if i:
            time.sleep(OPENALEX_PAUSE_SECONDS)
        flt = "|".join(f"https://doi.org/{d}" for d in chunk)
        url = (
            f"{OPENALEX_URL}?filter=doi:{urllib.parse.quote(flt, safe='')}"
            f"&per-page={OPENALEX_PER_BATCH}"
            f"&select=doi,best_oa_location,display_name,publication_year"
        )
        req = urllib.request.Request(url, headers={"User-Agent": OPENALEX_UA})
        try:
            with urllib.request.urlopen(req, timeout=OPENALEX_TIMEOUT_SECONDS) as resp:
                results = json.load(resp).get("results", [])
        except Exception:  # noqa: BLE001 — rate-limit/offline skips this batch
            time.sleep(OPENALEX_PAUSE_SECONDS)
            continue
        for work in results:
            doi = (work.get("doi") or "").replace("https://doi.org/", "").lower()
            loc = work.get("best_oa_location") or {}
            if not doi:
                continue
            out[doi] = {
                "pdf_url": loc.get("pdf_url"),
                "title": work.get("display_name") or "",
                "year": work.get("publication_year"),
            }
    return out


def _download_one(url: str, path: Path) -> str | None:
    """Download a URL to ``path`` when it is really a PDF.

    Returns None on success, or a short failure reason (the response was
    HTML, the host refused us, the file was unreachable…).
    """
    try:
        data = _fetch_bytes(url, PDF_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 — network failures are normal outcomes
        return f"unreachable ({type(exc).__name__})"
    if not data.startswith(b"%PDF"):
        return "not a PDF (bot-gated page or link rot)"
    path.write_bytes(data)
    return None


def _entry_hint(entry: dict) -> str:
    if entry.get("paperUrl"):
        return entry["paperUrl"]
    if entry.get("doi"):
        return f"https://doi.org/{entry['doi']}"
    if entry.get("arxiv"):
        return f"https://arxiv.org/abs/{entry['arxiv']}"
    return "(no link)"


def download_pdfs(archive_path: str | None = None, out_dir: str = "pdfs",
                  only: list[str] | None = None, force: bool = False,
                  dois: list[str] | None = None, arxiv_ids: list[str] | None = None,
                  status_cb=print) -> dict:
    """Download open-access PDFs. Returns a stats dict.

    ``archive_path`` selects archive records (scoped by ``only``); ``dois``
    and ``arxiv_ids`` download standalone papers without an archive. The
    archive file is read but never written.
    """
    targets: list[dict] = []  # {title, year, doi, arxiv, paperUrl}
    if archive_path:
        with open(archive_path, "r", encoding="utf-8") as f:
            archive = json.load(f)
        for papers in archive.values():
            if not isinstance(papers, list):
                continue
            for p in papers:
                if matches_only(p, only or []):
                    targets.append({
                        "title": p.get("title") or "",
                        "year": p.get("year"),
                        "doi": (p.get("doi") or "").strip() or None,
                        "arxiv": arxiv_id_for(p),
                        "paperUrl": p.get("paperUrl"),
                    })

    for raw in dois or []:
        m = _ARXIV_DOI_RE.match(raw.strip())
        if m:  # an arXiv DOI downloads straight from arXiv, no lookup needed
            targets.append({"title": "", "year": None, "doi": None,
                            "arxiv": m.group(1), "paperUrl": None})
        else:
            targets.append({"title": "", "year": None, "doi": raw.strip(),
                            "arxiv": None, "paperUrl": None})
    for raw in arxiv_ids or []:
        targets.append({"title": "", "year": None, "doi": None,
                        "arxiv": raw.strip(), "paperUrl": None})

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Resolve the non-arXiv DOIs through OpenAlex first — one batched call
    # beats one request per paper, and direct downloads need titles for names.
    need_lookup = [t["doi"] for t in targets if t["doi"] and not t["arxiv"]]
    resolved = openalex_pdf_urls(need_lookup) if need_lookup else {}
    for t in targets:
        if t["doi"] and not t["arxiv"]:
            info = resolved.get(t["doi"].lower()) or {}
            t["pdf_url"] = info.get("pdf_url")
            if not t["title"] and info.get("title"):
                t["title"] = info["title"]
            if not t["year"] and info.get("year"):
                t["year"] = info["year"]
        elif t["arxiv"]:
            t["pdf_url"] = ARXIV_PDF_URL.format(arxiv_id=t["arxiv"])
        else:
            t["pdf_url"] = None

    if archive_path:
        scope_note = f" (scoped to {len(targets)} matching)" if only else ""
        status_cb(f"Download candidates: {len(targets)}{scope_note}")

    downloaded = skipped = no_source = failed = 0
    used_names: set[str] = set()
    for t in targets:
        name = target_filename(t)
        while name in used_names:  # same-run slug collision: disambiguate by DOI
            suffix = slugify((t.get("doi") or t.get("arxiv") or "").replace("/", "_"))
            stem, dot, ext = name.rpartition(".")
            name = f"{stem}-{suffix}.{ext}" if dot else f"{name}-{suffix}"
        used_names.add(name)
        path = out / name

        label = t["title"] or t["doi"] or f"arXiv:{t['arxiv']}"
        if not t["pdf_url"]:
            no_source += 1
            status_cb(f"  no OA source: {label} — {_entry_hint(t)}")
            continue
        if path.exists() and not force:
            skipped += 1
            status_cb(f"  already present: {name}")
            continue
        reason = _download_one(t["pdf_url"], path)
        if reason:
            failed += 1
            status_cb(f"  failed ({reason}): {label} — open manually: {_entry_hint(t)}")
            continue
        downloaded += 1
        status_cb(f"  downloaded: {name}")
        time.sleep(ARXIV_PAUSE_SECONDS if t["arxiv"] else PUBLISHER_PAUSE_SECONDS)

    if targets:
        status_cb(
            f"\nDownloaded {downloaded} PDFs to {out_dir}/ "
            f"({skipped} already present, {no_source} without an OA source, {failed} failed)"
        )
    return {
        "candidates": len(targets),
        "downloaded": downloaded,
        "skipped_existing": skipped,
        "no_source": no_source,
        "failed": failed,
    }
