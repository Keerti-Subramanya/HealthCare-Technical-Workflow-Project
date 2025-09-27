"""
multi_source_scraper.py

A polite, legal, and extensible multi-source scholarly scraper that
- Uses APIs when available (PubMed via NCBI E-utilities, CrossRef, ClinicalTrials.gov)
- Falls back to crawl4ai for pages (WHO ICTRP, journals, conference pages)
- Deduplicates records by canonical identifiers and fuzzy title matching
- Stores results in a local SQLite DB
- Exports to JSON, CSV, and Excel (XLSX)

Dependencies: pip install requests crawl4ai python-dateutil tqdm openpyxl pandas

Run: python multi_source_scraper.py --query "large language models" --sources pubmed,crossref,clinicaltrials,who,journals

"""

from __future__ import annotations
import argparse
import json
import re
import sqlite3
import time
import sys
import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Iterable
import requests
from urllib.parse import quote_plus, urljoin
import difflib
import html as ihtml
from dateutil import parser as dateparser
from tqdm import tqdm
import pandas as pd

# crawl4ai import (the user had it installed earlier)
try:
    from crawl4ai import WebCrawler, CrawlerRunConfig
except Exception:
    WebCrawler = None
    CrawlerRunConfig = None

# ------------------------------- CONFIG ---------------------------------
CONTACT_EMAIL = "researcher@example.com"  # change to a real contact
USER_AGENT = f"MultiSourceScraper/1.0 (+{CONTACT_EMAIL})"
RATE_LIMIT_SECONDS = 1.0  # sleepy polite scraping
MAX_RETRIES = 3
DB_PATH = "scraper_results.db"
JSON_OUTPUT = "scraper_results.json"
CSV_OUTPUT = "scraper_results.csv"
XLSX_OUTPUT = "scraper_results.xlsx"

# Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("multi_scraper")

# ------------------------------- UTIL -----------------------------------

def polite_get(session: requests.Session, url: str, params: Optional[Dict] = None, timeout: int = 20) -> requests.Response:
    """GET with retries and rate limiting."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(RATE_LIMIT_SECONDS)
            r = session.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            log.warning("GET attempt %d failed for %s: %s", attempt, url, e)
            if attempt == MAX_RETRIES:
                raise
            time.sleep(1.5 * attempt)


def normalize_title(t: Optional[str]) -> str:
    if not t:
        return ""
    s = ihtml.unescape(t)
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_similar_title(a: str, b: str, threshold: float = 0.92) -> bool:
    if not a or not b:
        return False
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return ratio >= threshold

# ------------------------------- STORAGE --------------------------------
class Storage:
    def __init__(self, path: str = DB_PATH):
        self.conn = sqlite3.connect(path)
        self.create_table()

    def create_table(self):
        cur = self.conn.cursor()
        cur.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY,
            source TEXT,
            identifier TEXT UNIQUE,
            doi TEXT,
            pmid TEXT,
            nct TEXT,
            title TEXT,
            title_norm TEXT,
            url TEXT,
            authors TEXT,
            citation TEXT,
            raw_json TEXT,
            added_at TEXT
        )
        ''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_title_norm ON records(title_norm)')
        self.conn.commit()

    def close(self):
        self.conn.commit()
        self.conn.close()

    def find_duplicate_by_identifier(self, identifier: Optional[str]) -> Optional[int]:
        if not identifier:
            return None
        cur = self.conn.cursor()
        cur.execute('SELECT id FROM records WHERE identifier = ?', (identifier,))
        row = cur.fetchone()
        return row[0] if row else None

    def find_duplicate_by_title(self, title_norm: str) -> Optional[int]:
        cur = self.conn.cursor()
        cur.execute('SELECT id, title_norm FROM records')
        for rid, existing in cur.fetchall():
            if is_similar_title(existing or "", title_norm):
                return rid
        return None

    def insert_record(self, rec: Dict[str, Any]) -> int:
        identifier = rec.get('identifier') or rec.get('doi') or rec.get('pmid') or rec.get('nct')
        title = rec.get('title')
        title_norm = normalize_title(title)

        # Dedup by identifier
        if identifier and self.find_duplicate_by_identifier(identifier):
            log.info('Skipping duplicate by identifier: %s', identifier)
            return -1
        # Dedup by title fuzzy match
        dup = self.find_duplicate_by_title(title_norm)
        if dup:
            log.info('Skipping duplicate by similar title: %s', title)
            return -1

        cur = self.conn.cursor()
        cur.execute('''INSERT OR IGNORE INTO records
            (source, identifier, doi, pmid, nct, title, title_norm, url, authors, citation, raw_json, added_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (
            rec.get('source'),
            identifier,
            rec.get('doi'),
            rec.get('pmid'),
            rec.get('nct'),
            rec.get('title'),
            title_norm,
            rec.get('url'),
            rec.get('authors_text'),
            rec.get('journal_citation') or rec.get('citation'),
            json.dumps(rec.get('raw', {}), ensure_ascii=False),
            datetime.utcnow().isoformat()
        ))
        self.conn.commit()
        return cur.lastrowid

    def dump_all(self) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute('SELECT source,identifier,doi,pmid,nct,title,url,authors,citation,raw_json,added_at FROM records')
        rows = cur.fetchall()
        out = []
        for r in rows:
            raw = {}
            try:
                raw = json.loads(r[9] or '{}')
            except Exception:
                pass
            out.append({
                'source': r[0], 'identifier': r[1], 'doi': r[2], 'pmid': r[3], 'nct': r[4],
                'title': r[5], 'url': r[6], 'authors_text': r[7], 'citation': r[8], 'raw': raw, 'added_at': r[10]
            })
        return out

# ------------------------------- SCRAPERS -------------------------------
# (scraper classes unchanged, omitted here for brevity)
# ------------------------------- MAIN -----------------------------------

def ensure_readme_written():
    if os.path.exists('README.md'):
        return
    readme = f"""# Multi-source Scholarly Scraper

This project collects results from PubMed (NCBI), CrossRef, ClinicalTrials.gov and arbitrary pages (WHO ICTRP, journals) using APIs where available and crawl4ai as a polite fallback.

**Key points (legal & polite scraping)**
- This script uses official APIs when possible (NCBI, CrossRef, ClinicalTrials.gov).
- It sets a clear `User-Agent` with contact email: {CONTACT_EMAIL}.
- It respects rate limiting via a configurable `RATE_LIMIT_SECONDS`.
- It is the user's responsibility to obey each site's Terms of Service and robots.txt. The script includes simple checks and uses APIs where available to reduce load.

## Requirements
```bash
pip install requests crawl4ai python-dateutil tqdm openpyxl pandas
```

## How to run
```bash
python multi_source_scraper.py --query "large language models" --sources pubmed,crossref,clinicaltrials,who,journals --limit 50
```

Outputs:
- `scraper_results.db` SQLite DB with deduplicated records.
- `scraper_results.json` JSON dump of all saved records.
- `scraper_results.csv` CSV export of results.
- `scraper_results.xlsx` Excel export of results.

"""
    with open('README.md', 'w', encoding='utf-8') as f:
        f.write(readme)
    log.info('Wrote README.md')


def export_results(allr: List[Dict[str, Any]]):
    # JSON
    with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(allr, f, ensure_ascii=False, indent=2)
    log.info('Wrote %d records to %s', len(allr), JSON_OUTPUT)

    # CSV & Excel using pandas
    df = pd.DataFrame(allr)
    df.to_csv(CSV_OUTPUT, index=False, encoding='utf-8')
    log.info('Wrote CSV to %s', CSV_OUTPUT)

    df.to_excel(XLSX_OUTPUT, index=False, engine='openpyxl')
    log.info('Wrote Excel to %s', XLSX_OUTPUT)


def run(query: str, sources: List[str], limit: int = 20, journal_urls: Optional[List[str]] = None):
    ensure_readme_written()
    storage = Storage()
    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})

    # (scraping loop unchanged, omitted here for brevity)

    allr = storage.dump_all()
    export_results(allr)
    storage.close()

# ------------------------------- CLI ------------------------------------
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--query', required=True, help='Search query')
    p.add_argument('--sources', default='pubmed,crossref,clinicaltrials', help='Comma-separated sources (pubmed,crossref,clinicaltrials,who,journals)')
    p.add_argument('--limit', type=int, default=20)
    p.add_argument('--journal-urls', default=None, help='Comma-separated URLs to crawl for journals/conferences')
    args = p.parse_args()
    sources = [s.strip() for s in args.sources.split(',') if s.strip()]
    jurls = [u.strip() for u in args.journal_urls.split(',')] if args.journal_urls else None
    try:
        run(args.query, sources, limit=args.limit, journal_urls=jurls)
    except Exception as e:
        log.exception('Error during run: %s', e)
        sys.exit(1)
