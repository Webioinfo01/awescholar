"""PubMed E-utilities search and record normalization."""

import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
USER_AGENT = "awescholar (https://github.com/wehuman01/awescholar)"
TIMEOUT_SECONDS = 20


def _request(path: str, params: dict[str, str]) -> bytes:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{EUTILS_BASE}/{path}?{query}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        return response.read()


def _text(node: ET.Element | None, path: str) -> str:
    child = node.find(path) if node is not None else None
    return (child.text or "").strip() if child is not None else ""


def _authors(article: ET.Element) -> list[str]:
    names = []
    for author in article.findall(".//AuthorList/Author"):
        collective = _text(author, "CollectiveName")
        if collective:
            names.append(collective)
            continue
        name = " ".join(
            part for part in (_text(author, "ForeName"), _text(author, "LastName")) if part
        )
        if name:
            names.append(name)
    return names


def _abstract(article: ET.Element) -> str:
    parts = []
    for node in article.findall(".//Abstract/AbstractText"):
        text = "".join(node.itertext()).strip()
        if text:
            label = node.attrib.get("Label")
            parts.append(f"{label}: {text}" if label else text)
    return " ".join(parts)


def _record(article: ET.Element) -> dict:
    pubmed_id = _text(article, ".//PMID")
    title = " ".join(article.findtext(".//ArticleTitle", default="").split())
    journal = _text(article, ".//Journal/Title")
    year = _text(article, ".//ArticleDate/Year") or _text(article, ".//PubDate/Year")
    month = _text(article, ".//ArticleDate/Month") or _text(article, ".//PubDate/Month")
    doi = ""
    for identifier in article.findall(".//ArticleId") + article.findall(".//ELocationID"):
        kind = identifier.attrib.get("IdType") or identifier.attrib.get("EIdType")
        if kind == "doi":
            doi = (identifier.text or "").strip()
            break
    authors = _authors(article)
    return {
        "doi": doi,
        "pmid": pubmed_id,
        "title": title,
        "abstract": _abstract(article),
        "authors": authors,
        "year": f"{year}.{month}" if year and month else year,
        "venue": journal,
        "journal": journal,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/" if pubmed_id else "",
        "publication_types": ",".join(
            node.text.strip() for node in article.findall(".//PublicationType") if node.text
        ),
        "publication_date": "-".join(x for x in (year, month) if x),
        "fields_of_study": "Medicine,Biology",
        "citation_count": None,
    }


def search_pubmed(query: str, limit: int = 100) -> list[dict]:
    """Search PubMed and return normalized records with DOI-bearing papers."""
    search_xml = _request("esearch.fcgi", {
        "db": "pubmed", "term": query, "retmax": str(limit), "retmode": "json",
        "sort": "date",
    })
    import json
    ids = json.loads(search_xml).get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    time.sleep(0.1)
    xml = _request("efetch.fcgi", {
        "db": "pubmed", "id": ",".join(ids), "retmode": "xml",
    })
    records = [_record(article) for article in ET.fromstring(xml).findall(".//PubmedArticle")]
    return [record for record in records if record["doi"]]
