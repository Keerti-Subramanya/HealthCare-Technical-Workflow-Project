"""
Multi-Source Research Scraper
=============================

This script scrapes metadata from multiple research sources in a polite way:
- PubMed (via NCBI E-utilities API)
- CrossRef API
- ClinicalTrials.gov API
- WHO ICTRP registry (best effort)
- Generic journal/conference web pages (HTML)

Features:
- Deduplication by DOI / PMID / NCT / normalized title+year
- Polite scraping: honors robots.txt, uses contactable User-Agent, exponential backoff, respects Retry-After
- Output formats: JSONL, JSON, CSV, SQLite

Requirements:
- Python 3.9+
- Libraries: requests, beautifulsoup4, lxml, pandas

Setup:
1. Install requirements:
   pip install requests beautifulsoup4 lxml pandas

2. Set environment variables:
   export CONTACT_EMAIL="keertisubramanyasm@gmail.com"
   export NCBI_API_KEY="your_ncbi_key_if_any"   # optional

3. Run the scraper:
   python multi_source_scraper.py --query "large language models" --retmax 20 --out json

"""

import os
import re
import json
import time
import random
import logging
import argparse
import sqlite3
from urllib.parse import urlparse
from urllib import robotparser
from typing import List, Dict

import requests
import pandas as pd
from bs4 import BeautifulSoup

# ---------------------------------------------------
# Global settings
# ---------------------------------------------------
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL")
USER_AGENT = f"ResearchScraper/1.0 (mailto:{CONTACT_EMAIL})"
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}
NCBI_API_KEY = os.getenv("NCBI_API_KEY")
##CROSSREF_EMAIL = os.getenv("CROSSREF_EMAIL")
##CLINICAL_EMAIL = os.getenv("CLINICAL_EMAIL")
##WHO_API_KEY = os.getenv("WHO_API_KEY")

logger = logging.getLogger("multi_scraper")
logging.basicConfig(level=logging.INFO)

_session = None


def get_session():
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(DEFAULT_HEADERS)
        _session = s
    return _session


def can_fetch_url(url: str, user_agent: str = USER_AGENT) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        logger.warning("robots.txt unavailable at %s", robots_url)
        return True


def polite_get(url, params=None, max_retries=4, initial_backoff=1.0, timeout=30):
    if "ncbi.nlm.nih.gov" not in url and not can_fetch_url(url):
        raise PermissionError(f"robots.txt disallows fetching {url}")

    s = get_session()
    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            resp = s.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            logger.warning("Request exception: %s", exc)
            time.sleep(initial_backoff * (2 ** (attempt - 1)) + random.random() * 0.5)
            continue

        if resp.status_code == 429:
            ra = resp.headers.get("Retry-After")
            wait = int(ra) if ra and ra.isdigit() else initial_backoff * (2 ** (attempt - 1))
            logger.warning("429 Too Many Requests; retrying in %s s", wait)
            time.sleep(wait)
            continue

        if 500 <= resp.status_code < 600:
            time.sleep(initial_backoff * (2 ** (attempt - 1)) + random.random() * 0.5)
            continue

        return resp

    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts")


# ---------------------------------------------------
# PubMed via E-utilities
# ---------------------------------------------------
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def pubmed_esearch(query: str, retmax: int = 20, api_key: str | None = None) -> List[str]:
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": retmax,
        "sort": "pub+date",
        "tool": "ResearchScraper",
        "email": CONTACT_EMAIL,
    }
    if api_key:
        params["api_key"] = api_key
    r = polite_get(f"{EUTILS}/esearch.fcgi", params=params)
    data = r.json()
    return data.get("esearchresult", {}).get("idlist", [])


def pubmed_efetch(pmids: List[str], api_key: str | None = None, chunk_size: int = 200) -> str:
    xml_chunks = []
    for i in range(0, len(pmids), chunk_size):
        ids = pmids[i:i + chunk_size]
        params = {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "xml",
            "rettype": "abstract",
            "tool": "ResearchScraper",
            "email": CONTACT_EMAIL,
        }
        if api_key:
            params["api_key"] = api_key
        r = polite_get(f"{EUTILS}/efetch.fcgi", params=params)
        xml_chunks.append(r.text)
        time.sleep(0.12 if api_key else 0.34)
    return "\n".join(xml_chunks)


def parse_pubmed_xml(xml_text: str) -> List[Dict]:
    soup = BeautifulSoup(xml_text, "xml")
    out = []
    for art in soup.find_all("PubmedArticle"):
        pmid_el = art.find("PMID")
        pmid = pmid_el.get_text(strip=True) if pmid_el else None
        article = art.find("Article")
        title = article.find("ArticleTitle").get_text(" ", strip=True) if article and article.find("ArticleTitle") else None
        authors = []
        al = article.find("AuthorList") if article else None
        if al:
            for a in al.find_all("Author", recursive=False):
                coll = a.find("CollectiveName")
                if coll:
                    authors.append(coll.get_text(" ", strip=True))
                    continue
                ln = a.find("LastName").get_text(strip=True) if a.find("LastName") else ""
                fn = a.find("ForeName").get_text(strip=True) if a.find("ForeName") else ""
                name = f"{fn} {ln}".strip()
                if name:
                    authors.append(name)
        journal, year = None, None
        if article and article.find("Journal"):
            j = article.find("Journal").find("Title")
            journal = j.get_text(strip=True) if j else None
            y = article.find("Journal").find("JournalIssue").find("PubDate")
            year = y.find("Year").get_text(strip=True) if (y and y.find("Year")) else None
        doi, abstract = None, None
        aid = art.find("ArticleIdList")
        if aid:
            doi_el = aid.find("ArticleId", {"IdType": "doi"})
            doi = doi_el.get_text(strip=True) if doi_el else None
        if article and article.find("Abstract"):
            abstract_parts = [ab.get_text(" ", strip=True) for ab in article.find("Abstract").find_all("AbstractText")]
            abstract = " ".join(abstract_parts).strip()
        out.append({"pmid": pmid, "title": title, "authors": authors, "journal": journal, "year": year, "doi": doi, "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None, "abstract": abstract})
    return out


def scrape_pubmed(query: str, retmax: int = 20) -> List[Dict]:
    api_key = os.getenv("NCBI_API_KEY")
    pmids = pubmed_esearch(query, retmax=retmax, api_key=api_key)
    if not pmids:
        return []
    xml_text = pubmed_efetch(pmids, api_key=api_key)
    return parse_pubmed_xml(xml_text)


# ---------------------------------------------------
# CrossRef
# ---------------------------------------------------

def scrape_crossref(query: str, rows: int = 20) -> List[Dict]:
    url = "https://api.crossref.org/works"
    params = {"query": query, "rows": rows, "mailto": CONTACT_EMAIL}
    r = polite_get(url, params=params)
    items = r.json().get("message", {}).get("items", [])
    out = []
    for it in items:
        out.append({"doi": it.get("DOI"), "title": it.get("title", [None])[0], "authors": [" ".join(filter(None, [a.get("given"), a.get("family")])) for a in it.get("author", []) if "given" in a or "family" in a], "journal": it.get("container-title", [None])[0], "year": str(it.get("issued", {}).get("date-parts", [[None]])[0][0]), "url": it.get("URL"), "abstract": None})
    return out


# ---------------------------------------------------
# ClinicalTrials.gov
# ---------------------------------------------------

# def scrape_clinicaltrials(query: str, max_studies: int = 20) -> List[Dict]:
#     url = "https://clinicaltrials.gov/api/query/study_fields"
#     params = {"expr": query, "fields": ",".join(["NCTId", "BriefTitle", "Condition", "BriefSummary", "StartDate"]), "min_rnk": 1, "max_rnk": max_studies, "fmt": "json"}
#     r = polite_get(url, params=params)
#     studies = r.json()["StudyFieldsResponse"]["StudyFields"]
#     out = []
#     for s in studies:
#         out.append({"nct": s.get("NCTId", [None])[0], "title": s.get("BriefTitle", [None])[0], "authors": [], "journal": "ClinicalTrials.gov", "year": s.get("StartDate", [""])[0].split()[-1], "doi": None, "url": f"https://clinicaltrials.gov/study/{s.get('NCTId',[None])[0]}", "abstract": s.get("BriefSummary", [None])[0]})
#     return out

def scrape_clinicaltrials(query: str, max_studies: int = 20) -> List[Dict]:
    url = "https://clinicaltrials.gov/api/query/study_fields"
    params = {
        "expr": query,
        "fields": ",".join(["NCTId", "BriefTitle", "Condition", "BriefSummary", "StartDate"]),
        "min_rnk": 1,
        "max_rnk": max_studies,
        "fmt": "json"
    }
    r = polite_get(url, params=params)

    # Check response
    try:
        data = r.json()
    except json.JSONDecodeError:
        logger.warning("ClinicalTrials.gov returned invalid JSON. Response text: %s", r.text)
        return []

    studies = data["StudyFieldsResponse"]["StudyFields"]
    out = []
    for s in studies:
        out.append({
            "nct": s.get("NCTId", [None])[0],
            "title": s.get("BriefTitle", [None])[0],
            "authors": [],
            "journal": "ClinicalTrials.gov",
            "year": s.get("StartDate", [""])[0].split()[-1],
            "doi": None,
            "url": f"https://clinicaltrials.gov/study/{s.get('NCTId',[None])[0]}",
            "abstract": s.get("BriefSummary", [None])[0]
        })
    return out

# ---------------------------------------------------
# WHO ICTRP (placeholder — not always API accessible)
# ---------------------------------------------------

def scrape_who_ictrp(query: str, max_records: int = 20) -> List[Dict]:
    logger.warning("WHO ICTRP scraping is limited; returning empty list for now.")
    return []


# ---------------------------------------------------
# Deduplication
# ---------------------------------------------------

def normalize_title(t: str | None) -> str | None:
    return re.sub(r"[^a-z0-9]", "", t.lower()) if t else None


def deduplicate(records: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for r in records:
        key = r.get("doi") or r.get("pmid") or r.get("nct") or (normalize_title(r.get("title")) + (r.get("year") or ""))
        if key and key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ---------------------------------------------------
# Save helpers
# ---------------------------------------------------
def save_jsonl(records, path):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def save_json(records, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

def save_csv(records, path):
    pd.DataFrame(records).to_csv(path, index=False)

def save_sqlite(records, path):
    conn = sqlite3.connect(path)
    pd.DataFrame(records).to_sql("records", conn, if_exists="replace", index=False)
    conn.close()


# ---------------------------------------------------
# CLI
# ---------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Multi-source research scraper")
    parser.add_argument("--query", required=True)
    parser.add_argument("--retmax", type=int, default=20)
    parser.add_argument("--out", choices=["jsonl", "json", "csv", "sqlite"], default="json")
    parser.add_argument("--outfile", default="output.json")
    args = parser.parse_args()

    all_records = []
    all_records.extend(scrape_pubmed(args.query, retmax=args.retmax))
    all_records.extend(scrape_crossref(args.query, rows=args.retmax))
    all_records.extend(scrape_clinicaltrials(args.query, max_studies=args.retmax))
    all_records.extend(scrape_who_ictrp(args.query, max_records=args.retmax))

    records = deduplicate(all_records)

    if args.out == "jsonl":
        save_jsonl(records, args.outfile)
    elif args.out == "json":
        save_json(records, args.outfile)
    elif args.out == "csv":
        save_csv(records, args.outfile)
    elif args.out == "sqlite":
        save_sqlite(records, args.outfile)

    logger.info("Saved %d records to %s (%s)", len(records), args.outfile, args.out)


if __name__ == "__main__":
    main()
