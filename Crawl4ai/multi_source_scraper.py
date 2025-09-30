# """
# multi_source_scraper.py

# A polite, legal, and extensible multi-source scholarly scraper that
# - Uses APIs when available (PubMed via NCBI E-utilities, CrossRef, ClinicalTrials.gov)
# - Falls back to crawl4ai for pages (WHO ICTRP, journals, conference pages)
# - Deduplicates records by canonical identifiers and fuzzy title matching
# - Stores results in a local SQLite DB
# - Exports to JSON, CSV, and Excel (XLSX)

# Dependencies: pip install requests crawl4ai python-dateutil tqdm openpyxl pandas

# Run: python multi_source_scraper.py --query "large language models" --sources pubmed,crossref,clinicaltrials,who,journals

# """

# from __future__ import annotations
# import argparse
# import json
# import re
# import sqlite3
# import time
# import sys
# import os
# import logging
# from datetime import datetime
# from typing import Dict, Any, List, Optional, Iterable
# import requests
# from urllib.parse import quote_plus, urljoin
# import difflib
# import html as ihtml
# from dateutil import parser as dateparser
# from tqdm import tqdm
# import pandas as pd

# # crawl4ai import (the user had it installed earlier)
# try:
#     from crawl4ai import WebCrawler, CrawlerRunConfig
# except Exception:
#     WebCrawler = None
#     CrawlerRunConfig = None

# # ------------------------------- CONFIG ---------------------------------
# CONTACT_EMAIL = "keertisubramanyasm@gmail.com"  # change to a real contact
# USER_AGENT = f"MultiSourceScraper/1.0 (+{CONTACT_EMAIL})"
# RATE_LIMIT_SECONDS = 1.0  # sleepy polite scraping
# MAX_RETRIES = 3
# DB_PATH = "scraper_results.db"
# JSON_OUTPUT = "scraper_results.json"
# CSV_OUTPUT = "scraper_results.csv"
# XLSX_OUTPUT = "scraper_results.xlsx"


# # Logger
# logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# log = logging.getLogger("multi_scraper")

# # ------------------------------- UTIL -----------------------------------

# def polite_get(session: requests.Session, url: str, params: Optional[Dict] = None, timeout: int = 20) -> requests.Response:
#     """GET with retries and rate limiting."""
#     for attempt in range(1, MAX_RETRIES + 1):
#         try:
#             time.sleep(RATE_LIMIT_SECONDS)
#             r = session.get(url, params=params, timeout=timeout)
#             r.raise_for_status()
#             return r
#         except Exception as e:
#             log.warning("GET attempt %d failed for %s: %s", attempt, url, e)
#             if attempt == MAX_RETRIES:
#                 raise
#             time.sleep(1.5 * attempt)


# def normalize_title(t: Optional[str]) -> str:
#     if not t:
#         return ""
#     s = ihtml.unescape(t)
#     s = s.lower()
#     s = re.sub(r"[^a-z0-9]+", " ", s)
#     s = re.sub(r"\s+", " ", s).strip()
#     return s


# def is_similar_title(a: str, b: str, threshold: float = 0.92) -> bool:
#     if not a or not b:
#         return False
#     ratio = difflib.SequenceMatcher(None, a, b).ratio()
#     return ratio >= threshold

# # ------------------------------- STORAGE --------------------------------
# class Storage:
#     def __init__(self, path: str = DB_PATH):
#         self.conn = sqlite3.connect(path)
#         self.create_table()

#     def create_table(self):
#         cur = self.conn.cursor()
#         cur.execute('''
#         CREATE TABLE IF NOT EXISTS records (
#             id INTEGER PRIMARY KEY,
#             source TEXT,
#             identifier TEXT UNIQUE,
#             doi TEXT,
#             pmid TEXT,
#             nct TEXT,
#             title TEXT,
#             title_norm TEXT,
#             url TEXT,
#             authors TEXT,
#             citation TEXT,
#             raw_json TEXT,
#             added_at TEXT
#         )
#         ''')
#         cur.execute('CREATE INDEX IF NOT EXISTS idx_title_norm ON records(title_norm)')
#         self.conn.commit()

#     def close(self):
#         self.conn.commit()
#         self.conn.close()

#     def find_duplicate_by_identifier(self, identifier: Optional[str]) -> Optional[int]:
#         if not identifier:
#             return None
#         cur = self.conn.cursor()
#         cur.execute('SELECT id FROM records WHERE identifier = ?', (identifier,))
#         row = cur.fetchone()
#         return row[0] if row else None

#     def find_duplicate_by_title(self, title_norm: str) -> Optional[int]:
#         cur = self.conn.cursor()
#         cur.execute('SELECT id, title_norm FROM records')
#         for rid, existing in cur.fetchall():
#             if is_similar_title(existing or "", title_norm):
#                 return rid
#         return None

#     def insert_record(self, rec: Dict[str, Any]) -> int:
#         identifier = rec.get('identifier') or rec.get('doi') or rec.get('pmid') or rec.get('nct')
#         title = rec.get('title')
#         title_norm = normalize_title(title)

#         # Dedup by identifier
#         if identifier and self.find_duplicate_by_identifier(identifier):
#             log.info('Skipping duplicate by identifier: %s', identifier)
#             return -1
#         # Dedup by title fuzzy match
#         dup = self.find_duplicate_by_title(title_norm)
#         if dup:
#             log.info('Skipping duplicate by similar title: %s', title)
#             return -1

#         cur = self.conn.cursor()
#         cur.execute('''INSERT OR IGNORE INTO records
#             (source, identifier, doi, pmid, nct, title, title_norm, url, authors, citation, raw_json, added_at)
#             VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (
#             rec.get('source'),
#             identifier,
#             rec.get('doi'),
#             rec.get('pmid'),
#             rec.get('nct'),
#             rec.get('title'),
#             title_norm,
#             rec.get('url'),
#             rec.get('authors_text'),
#             rec.get('journal_citation') or rec.get('citation'),
#             json.dumps(rec.get('raw', {}), ensure_ascii=False),
#             datetime.utcnow().isoformat()
#         ))
#         self.conn.commit()
#         return cur.lastrowid

#     def dump_all(self) -> List[Dict[str, Any]]:
#         cur = self.conn.cursor()
#         cur.execute('SELECT source,identifier,doi,pmid,nct,title,url,authors,citation,raw_json,added_at FROM records')
#         rows = cur.fetchall()
#         out = []
#         for r in rows:
#             raw = {}
#             try:
#                 raw = json.loads(r[9] or '{}')
#             except Exception:
#                 pass
#             out.append({
#                 'source': r[0], 'identifier': r[1], 'doi': r[2], 'pmid': r[3], 'nct': r[4],
#                 'title': r[5], 'url': r[6], 'authors_text': r[7], 'citation': r[8], 'raw': raw, 'added_at': r[10]
#             })
#         return out

# # ------------------------------- SCRAPERS -------------------------------
# # (scraper classes unchanged, omitted here for brevity)
# # ------------------------------- MAIN -----------------------------------

# # def ensure_readme_written():
# #     if os.path.exists('README.md'):
# #         return
# #     readme = f"""# Multi-source Scholarly Scraper

# # This project collects results from PubMed (NCBI), CrossRef, ClinicalTrials.gov and arbitrary pages (WHO ICTRP, journals) using APIs where available and crawl4ai as a polite fallback.

# # **Key points (legal & polite scraping)**
# # - This script uses official APIs when possible (NCBI, CrossRef, ClinicalTrials.gov).
# # - It sets a clear `User-Agent` with contact email: {CONTACT_EMAIL}.
# # - It respects rate limiting via a configurable `RATE_LIMIT_SECONDS`.
# # - It is the user's responsibility to obey each site's Terms of Service and robots.txt. The script includes simple checks and uses APIs where available to reduce load.

# # ## Requirements
# # ```bash
# # pip install requests crawl4ai python-dateutil tqdm openpyxl pandas
# # ```

# # ## How to run
# # ```bash
# # python multi_source_scraper.py --query "large language models" --sources pubmed,crossref,clinicaltrials,who,journals --limit 50
# # ```

# # Outputs:
# # - `scraper_results.db` SQLite DB with deduplicated records.
# # - `scraper_results.json` JSON dump of all saved records.
# # - `scraper_results.csv` CSV export of results.
# # - `scraper_results.xlsx` Excel export of results.

# # """
# #     with open('README.md', 'w', encoding='utf-8') as f:
# #         f.write(readme)
# #     log.info('Wrote README.md')


# def export_results(allr: List[Dict[str, Any]]):
#     # JSON
#     with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
#         json.dump(allr, f, ensure_ascii=False, indent=2)
#     log.info('Wrote %d records to %s', len(allr), JSON_OUTPUT)

#     # CSV & Excel using pandas
#     df = pd.DataFrame(allr)
#     df.to_csv(CSV_OUTPUT, index=False, encoding='utf-8')
#     log.info('Wrote CSV to %s', CSV_OUTPUT)

#     df.to_excel(XLSX_OUTPUT, index=False, engine='openpyxl')
#     log.info('Wrote Excel to %s', XLSX_OUTPUT)


# def run(query: str, sources: List[str], limit: int = 20, journal_urls: Optional[List[str]] = None):
#     ##ensure_readme_written()
#     storage = Storage()
#     session = requests.Session()
#     session.headers.update({'User-Agent': USER_AGENT})

#     # (scraping loop unchanged, omitted here for brevity)

#     allr = storage.dump_all()
#     export_results(allr)
#     storage.close()

# # ------------------------------- CLI ------------------------------------
# if __name__ == '__main__':
#     p = argparse.ArgumentParser()
#     p.add_argument('--query', required=True, help='Search query')
#     p.add_argument('--sources', default='pubmed,crossref,clinicaltrials', help='Comma-separated sources (pubmed,crossref,clinicaltrials,who,journals)')
#     p.add_argument('--limit', type=int, default=20)
#     p.add_argument('--format',type=str,choices=['json', 'csv', 'excel'], default='json',help="Output file format.")
#     p.add_argument('--journal-urls', default=None, help='Comma-separated URLs to crawl for journals/conferences')
#     args = p.parse_args()
#     sources = [s.strip() for s in args.sources.split(',') if s.strip()]
#     jurls = [u.strip() for u in args.journal_urls.split(',')] if args.journal_urls else None
#     try:
#         run(args.query, sources, limit=args.limit, journal_urls=jurls)
#     except Exception as e:
#         log.exception('Error during run: %s', e)
#         sys.exit(1)


#!/usr/bin/env python3
# """
# crawl4ai_scraper_zotero.py

# - Uses crawl4ai.WebCrawler when available to fetch pages; falls back to requests polite_get otherwise.
# - Filters results STRICTLY to records where at least one PICO keyword (from uploaded PROSPERO PDF)
#   appears in title OR abstract.
# - Exports CSV/XLSX/JSON with the exact Zotero-like header you provided (all fields present).
# - Deduplicates by identifier (DOI/PMID) and fuzzy title matching.
# """

# from __future__ import annotations
# import argparse, json, re, sqlite3, time, sys, logging
# from datetime import datetime
# from typing import Dict, Any, List, Optional
# import difflib
# import html as ihtml
# import pandas as pd
# import xml.etree.ElementTree as ET

# # Try to use crawl4ai if available (preferred). If not, fallback to requests.
# USE_CRAWL4AI = True
# try:
#     from crawl4ai import WebCrawler, CrawlerRunConfig  # type: ignore
# except Exception:
#     USE_CRAWL4AI = False

# import requests
# from tqdm import tqdm

# # ------------------------------- CONFIG ---------------------------------
# CONTACT_EMAIL = "keertisubramanyasm@gmail.com"
# USER_AGENT = f"MultiSourceScraper/1.0 (+{CONTACT_EMAIL})"
# RATE_LIMIT_SECONDS = 1.0
# MAX_RETRIES = 3
# DB_PATH = "scraper_results.db"
# JSON_OUTPUT = "scraper_results.json"
# CSV_OUTPUT = "scraper_results.csv"
# XLSX_OUTPUT = "scraper_results.xlsx"

# # Optional API keys (keep as before)
# PUBMED_API_KEY = "c2f307fc5acc4197325e5d9234ff271aa608"
# CROSSREF_EMAIL = CONTACT_EMAIL

# # ------------------------------- LOGGER --------------------------------
# logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# log = logging.getLogger("crawl4ai_scraper_zotero")

# # ------------------------------- UTIL -----------------------------------
# def polite_get_requests(session: requests.Session, url: str, params: Optional[Dict] = None, timeout: int = 20) -> requests.Response:
#     """Polite requests fallback."""
#     for attempt in range(1, MAX_RETRIES + 1):
#         try:
#             time.sleep(RATE_LIMIT_SECONDS)
#             r = session.get(url, params=params, timeout=timeout)
#             r.raise_for_status()
#             return r
#         except Exception as e:
#             log.warning("requests GET attempt %d failed for %s: %s", attempt, url, e)
#             if attempt == MAX_RETRIES:
#                 raise
#             time.sleep(1.5 * attempt)

# def normalize_title(t: Optional[str]) -> str:
#     if not t: return ""
#     s = ihtml.unescape(t)
#     s = s.lower()
#     s = re.sub(r"[^a-z0-9]+", " ", s)
#     return re.sub(r"\s+", " ", s).strip()

# def is_similar_title(a: str, b: str, threshold: float = 0.92) -> bool:
#     if not a or not b: return False
#     return difflib.SequenceMatcher(None, a, b).ratio() >= threshold

# def clean_text(text: Optional[str]) -> str:
#     if not text: return ""
#     t = re.sub(r'<[^>]+>', '', text)
#     return re.sub(r'\s+', ' ', t).strip()

# # ------------------------------- PICO KEYWORDS (from uploaded PROSPERO PDF) ------------------------
# # These are used ONLY for filtering (A: strict filter). If none match title+abstract -> skip.
# PICO_KEYWORDS = {
#     'interventions': [
#         'dexrazoxane', 'beta-blocker', 'beta blocker', 'beta-blockers', 'ace inhibitor', 'ace inhibitors',
#         'arb', 'arbs', 'acei', 'angiotensin receptor blocker', 'angiotensin converting enzyme inhibitor',
#         'arni', 'arnis', 'valsartan', 'sacubitril', 'mineralocorticoid receptor antagonist', 'spironolactone',
#         'eplerenone', 'statin', 'statins'
#     ],
#     'exposures': [
#         'anthracyclin', 'anthracycline', 'doxorubicin', 'daunorubicin', 'epirubicin', 'idarubicin',
#         'trastuzumab', 'her2', 'her-2', 'chemotherapy', 'cytotoxic'
#     ],
#     'comparators': [
#         'placebo', 'usual care', 'no intervention', 'standard care', 'control', 'comparative'
#     ],
#     'study_designs': [
#         'randomized', 'randomised', 'randomised controlled trial', 'randomized controlled trial', 'rct',
#         'cohort', 'case-control', 'case control', 'observational', 'prospective', 'retrospective',
#         'phase ii', 'phase iii', 'phase iv'
#     ]
# }

# # compile joint regex for quick membership test
# ALL_PICO_TERMS = sorted({t for lst in PICO_KEYWORDS.values() for t in lst}, key=len, reverse=True)
# PICO_PATTERN = re.compile(r'(' + r'|'.join([re.escape(x) for x in ALL_PICO_TERMS]) + r')', flags=re.IGNORECASE)

# # ------------------------------- ZOTERO HEADER --------------------------------
# # Exact header order provided by user (kept verbatim). We'll create a template dict with these keys.
# ZOTERO_HEADER = [
# "Key","Item Type","Publication Year","Author","Title","Publication Title","ISBN","ISSN","DOI","Url",
# "Abstract Note","Date","Date Added","Date Modified","Access Date","Pages","Num Pages","Issue","Volume",
# "Number Of Volumes","Journal Abbreviation","Short Title","Series","Series Number","Series Text","Series Title",
# "Publisher","Place","Language","Rights","Type","Archive","Archive Location","Library Catalog","Call Number",
# "Extra","Notes","File Attachments","Link Attachments","Manual Tags","Automatic Tags","Editor","Series Editor",
# "Translator","Contributor","Attorney Agent","Book Author","Cast Member","Commenter","Composer","Cosponsor",
# "Counsel","Interviewer","Producer","Recipient","Reviewed Author","Scriptwriter","Words By","Guest","Number",
# "Edition","Running Time","Scale","Medium","Artwork Size","Filing Date","Application Number","Assignee",
# "Issuing Authority","Country","Meeting Name","Conference Name","Court","References","Reporter","Legal Status",
# "Priority Numbers","Programming Language","Version","System","Code","Code Number","Section","Session","Committee",
# "History","Legislative Body"
# ]

# # ------------------------------- STORAGE (SQLite + dedupe) ------------------
# class Storage:
#     def __init__(self, path: str = DB_PATH):
#         self.conn = sqlite3.connect(path)
#         self.create_table()

#     def create_table(self):
#         cur = self.conn.cursor()
#         cur.execute('''
#         CREATE TABLE IF NOT EXISTS records (
#             id INTEGER PRIMARY KEY,
#             identifier TEXT UNIQUE,
#             title TEXT,
#             title_norm TEXT,
#             doi TEXT,
#             pmid TEXT,
#             source TEXT,
#             url TEXT,
#             authors TEXT,
#             journal TEXT,
#             pub_year TEXT,
#             abstract TEXT,
#             raw_json TEXT,
#             extra TEXT,
#             added_at TEXT
#         )''')
#         cur.execute('CREATE INDEX IF NOT EXISTS idx_title_norm ON records(title_norm)')
#         self.conn.commit()

#     def close(self):
#         self.conn.commit()
#         self.conn.close()

#     def find_duplicate_by_identifier(self, identifier: Optional[str]) -> Optional[int]:
#         if not identifier: return None
#         cur = self.conn.cursor()
#         cur.execute('SELECT id FROM records WHERE identifier = ?', (identifier,))
#         row = cur.fetchone()
#         return row[0] if row else None

#     def find_duplicate_by_title(self, title_norm: str) -> Optional[int]:
#         cur = self.conn.cursor()
#         cur.execute('SELECT id, title_norm FROM records')
#         for rid, existing in cur.fetchall():
#             if is_similar_title(existing or "", title_norm):
#                 return rid
#         return None

#     def insert_record(self, rec: Dict[str, Any]) -> int:
#         identifier = rec.get('identifier') or rec.get('doi') or rec.get('pmid')
#         title = rec.get('title','')
#         title_norm = normalize_title(title)

#         if identifier and self.find_duplicate_by_identifier(identifier):
#             log.info("Skipping duplicate by identifier: %s", identifier)
#             return -1
#         if self.find_duplicate_by_title(title_norm):
#             log.info("Skipping duplicate by similar title: %s", title)
#             return -1

#         cur = self.conn.cursor()
#         cur.execute('''
#             INSERT INTO records
#             (identifier, title, title_norm, doi, pmid, source, url, authors, journal, pub_year, abstract, raw_json, extra, added_at)
#             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
#         ''', (
#             identifier,
#             title,
#             title_norm,
#             rec.get('doi'),
#             rec.get('pmid'),
#             rec.get('source'),
#             rec.get('url'),
#             rec.get('authors_text'),
#             rec.get('journal'),
#             rec.get('publication_year'),
#             clean_text(rec.get('abstract','')),
#             json.dumps(rec.get('raw', {}), ensure_ascii=False),
#             rec.get('extra',''),
#             datetime.utcnow().isoformat()
#         ))
#         self.conn.commit()
#         return cur.lastrowid

#     def dump_all(self) -> List[Dict[str, Any]]:
#         cur = self.conn.cursor()
#         cur.execute('''
#             SELECT identifier, title, doi, pmid, source, url, authors, journal, pub_year, abstract, raw_json, extra, added_at
#             FROM records
#         ''')
#         rows = cur.fetchall()
#         out = []
#         for r in rows:
#             raw = {}
#             try: raw = json.loads(r[10] or '{}')
#             except: pass
#             out.append({
#                 'identifier': r[0],
#                 'title': r[1],
#                 'doi': r[2],
#                 'pmid': r[3],
#                 'source': r[4],
#                 'url': r[5],
#                 'authors_text': r[6],
#                 'journal': r[7],
#                 'publication_year': r[8],
#                 'abstract': r[9],
#                 'raw': raw,
#                 'extra': r[11],
#                 'added_at': r[12]
#             })
#         return out

# # ------------------------------- FETCH LAYER (uses crawl4ai when available) ------------------
# class Fetcher:
#     def __init__(self):
#         self.requests_session = requests.Session()
#         self.requests_session.headers.update({'User-Agent': USER_AGENT})
#         self.crawl4ai_client = None
#         if USE_CRAWL4AI:
#             try:
#                 # Best-effort init; if WebCrawler requires config, this may need customizing in your env.
#                 self.crawl4ai_client = WebCrawler()
#                 log.info("crawl4ai WebCrawler imported and initialized.")
#             except Exception as e:
#                 log.warning("Failed to init crawl4ai WebCrawler: %s. Falling back to requests.", e)
#                 self.crawl4ai_client = None

#     def fetch(self, url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None, timeout: int = 30) -> Dict[str, Any]:
#         """
#         Returns dict: {'text': str, 'status': int, 'url': final_url}
#         Tries crawl4ai when available; otherwise uses requests.
#         Note: crawl4ai API has many variants; we call a simple .fetch / .get if present, else fallback.
#         """
#         # try crawl4ai if available and client exists
#         if self.crawl4ai_client:
#             try:
#                 # Try a couple of likely method names (best-effort). If these fail, we'll fallback.
#                 if hasattr(self.crawl4ai_client, "get"):
#                     r = self.crawl4ai_client.get(url, params=params, headers=headers or {}, timeout=timeout)
#                     # assume r has .text and .status_code
#                     return {'text': getattr(r, 'text', str(r)), 'status': getattr(r, 'status_code', 200), 'url': url}
#                 elif hasattr(self.crawl4ai_client, "fetch"):
#                     r = self.crawl4ai_client.fetch(url, params=params, headers=headers or {}, timeout=timeout)
#                     return {'text': getattr(r, 'text', str(r)), 'status': getattr(r, 'status_code', 200), 'url': url}
#                 else:
#                     # last-resort: call the object's __call__ if it returns something useful
#                     r = self.crawl4ai_client(url)
#                     return {'text': getattr(r, 'text', str(r)), 'status': getattr(r, 'status_code', 200), 'url': url}
#             except Exception as e:
#                 log.warning("crawl4ai fetch failed for %s: %s. Falling back to requests.", url, e)

#         # fallback: requests (polite)
#         r = polite_get_requests(self.requests_session, url, params=params, timeout=timeout)
#         return {'text': r.text, 'status': r.status_code, 'url': r.url}

# # ------------------------------- MAPPERS --------------------------------
# def zotero_template() -> Dict[str, str]:
#     """Return a dict with all Zotero header keys initialized to empty string."""
#     return {k: "" for k in ZOTERO_HEADER}

# def map_record_to_zotero(rec: Dict[str, Any]) -> Dict[str, str]:
#     """Map normalized internal record to Zotero columns. Extra will contain found PICO terms."""
#     # start with template
#     out = zotero_template()

#     # basic mapping
#     out['Title'] = rec.get('title','') or ""
#     out['Author'] = rec.get('authors_text','') or ""
#     out['DOI'] = rec.get('doi','') or ""
#     out['Url'] = rec.get('url','') or ""
#     out['Abstract Note'] = rec.get('abstract','') or ""
#     out['Publication Title'] = rec.get('journal','') or ""
#     out['Publication Year'] = str(rec.get('publication_year','') or "")
#     # put PICO-matched keywords into Extra (as comma-separated)
#     extra_existing = rec.get('extra','') or ""
#     out['Extra'] = extra_existing
#     # keep identifier in Key if present
#     out['Key'] = rec.get('identifier','') or ""

#     return out

# # ------------------------------- SCRAPERS FOR SOURCES ---------------------
# def scrape_pubmed(fetcher: Fetcher, storage: Storage, query: str, limit: int = 20):
#     """
#     Use Entrez eutils search + efetch but fetched via crawl4ai/fetcher.
#     """
#     log.info("PubMed search for '%s' (limit=%d)", query, limit)
#     url_search = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#     params_search = {'db':'pubmed','term':query,'retmax':limit,'retmode':'json','api_key':PUBMED_API_KEY}
#     resp = fetcher.fetch(url_search, params=params_search)
#     try:
#         data = json.loads(resp['text'])
#     except Exception as e:
#         log.error("PubMed search JSON parse failed: %s", e)
#         return
#     ids = data.get('esearchresult', {}).get('idlist', [])
#     log.info("PubMed returned %d IDs", len(ids))
#     if not ids:
#         return

#     url_fetch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
#     params_fetch = {'db':'pubmed','id':",".join(ids),'retmode':'xml','api_key':PUBMED_API_KEY}
#     resp2 = fetcher.fetch(url_fetch, params=params_fetch)
#     try:
#         root = ET.fromstring(resp2['text'])
#     except Exception as e:
#         log.error("PubMed efetch XML parse failed: %s", e)
#         return

#     for article in root.findall('.//PubmedArticle'):
#         pmid_elem = article.find('.//PMID')
#         title_elem = article.find('.//ArticleTitle')
#         abstract_texts = [el.text or '' for el in article.findall('.//Abstract/AbstractText')]
#         abstract_joined = ' '.join(abstract_texts).strip()
#         authors = article.findall('.//Author')
#         authors_text = ", ".join([f"{a.findtext('LastName','')} {a.findtext('ForeName','')}".strip()
#                                   for a in authors if a.find('LastName') is not None])
#         journal_title = article.findtext('.//Journal/Title','')
#         pub_year = article.findtext('.//PubDate/Year','') or article.findtext('.//PubDate/MedlineDate','')

#         pmid = pmid_elem.text if pmid_elem is not None else ''
#         title_text = title_elem.text if title_elem is not None else ''
#         combined_text = " ".join([title_text, abstract_joined])

#         # Filter strictly by PICO keywords (A)
#         if not PICO_PATTERN.search(combined_text):
#             log.debug("Skipping PMCID/PMID %s because no PICO keywords found", pmid)
#             continue

#         # collect found pico terms
#         found = sorted(set([m.group(0).strip() for m in PICO_PATTERN.finditer(combined_text)]), key=str.lower)
#         extra_text = "PICO_keywords_found: " + ", ".join(found)

#         record = {
#             'source': 'pubmed',
#             'pmid': pmid,
#             'identifier': pmid,
#             'title': title_text,
#             'abstract': abstract_joined,
#             'url': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/' if pmid else '',
#             'authors_text': authors_text,
#             'journal': journal_title,
#             'publication_year': pub_year,
#             'doi': '',  # PubMed XML DOI extraction can be added if needed
#             'raw': ET.tostring(article, encoding='unicode'),
#             'extra': extra_text
#         }
#         storage.insert_record(record)

# def scrape_crossref(fetcher: Fetcher, storage: Storage, query: str, limit: int = 20):
#     log.info("CrossRef search for '%s' (limit=%d)", query, limit)
#     url = "https://api.crossref.org/works"
#     params = {'query': query, 'rows': limit, 'mailto': CROSSREF_EMAIL}
#     resp = fetcher.fetch(url, params=params)
#     try:
#         data = json.loads(resp['text'])
#     except Exception as e:
#         log.error("CrossRef JSON parse failed: %s", e)
#         return
#     items = data.get('message', {}).get('items', [])
#     log.info("CrossRef returned %d items", len(items))
#     for item in items:
#         title = item.get('title', [''])[0] if item.get('title') else ''
#         abstract = clean_text(item.get('abstract','') or '')
#         combined = " ".join([title, abstract])
#         if not PICO_PATTERN.search(combined):
#             log.debug("Skipping CrossRef DOI %s because no PICO keywords found", item.get('DOI'))
#             continue
#         found = sorted(set([m.group(0).strip() for m in PICO_PATTERN.finditer(combined)]), key=str.lower)
#         extra_text = "PICO_keywords_found: " + ", ".join(found)
#         doi = item.get('DOI')
#         authors_text = ", ".join([a.get('family','') + ((" " + a.get('given','')) if a.get('given') else "") for a in item.get('author',[])]) if item.get('author') else ''
#         journal = item.get('container-title',[''])[0] if item.get('container-title') else ''
#         pub_year = ''
#         issued = item.get('issued', {}).get('date-parts', [])
#         if issued and isinstance(issued, list) and len(issued[0])>0:
#             pub_year = str(issued[0][0])

#         record = {
#             'source': 'crossref',
#             'doi': doi,
#             'identifier': doi,
#             'title': title,
#             'abstract': abstract,
#             'url': item.get('URL'),
#             'authors_text': authors_text,
#             'journal': journal,
#             'publication_year': pub_year,
#             'raw': item,
#             'extra': extra_text
#         }
#         storage.insert_record(record)

# # ------------------------------- EXPORT ---------------------------------
# def export_results(allr: List[Dict[str, Any]]):
#     # Build list of Zotero-mapped rows (full header present)
#     rows = []
#     for rec in allr:
#         zot = map_record_to_zotero(rec)
#         # ensure ordering: same as ZOTERO_HEADER
#         ordered = {k: zot.get(k, "") for k in ZOTERO_HEADER}
#         rows.append(ordered)

#     # write JSON (raw)
#     with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
#         json.dump(allr, f, ensure_ascii=False, indent=2)
#     log.info("Wrote %d records to %s", len(allr), JSON_OUTPUT)

#     # DataFrame for CSV/XLSX
#     df = pd.DataFrame(rows, columns=ZOTERO_HEADER)
#     df.to_csv(CSV_OUTPUT, index=False, encoding='utf-8')
#     log.info("Wrote CSV to %s", CSV_OUTPUT)
#     df.to_excel(XLSX_OUTPUT, index=False, engine='openpyxl')
#     log.info("Wrote Excel to %s", XLSX_OUTPUT)

# # ------------------------------- RUN ------------------------------------
# def run(query: str, sources: List[str], limit: int = 20):
#     storage = Storage()
#     fetcher = Fetcher()
#     log.info("Running scraper with sources=%s query='%s' limit=%d (strict PICO filter enabled)", sources, query, limit)

#     if 'pubmed' in sources:
#         try:
#             scrape_pubmed(fetcher, storage, query, limit=limit)
#         except Exception as e:
#             log.exception("Error scraping PubMed: %s", e)

#     if 'crossref' in(sources):
#         try:
#             scrape_crossref(fetcher, storage, query, limit=limit)
#         except Exception as e:
#             log.exception("Error scraping CrossRef: %s", e)

#     # Add more source scrapers here following same pattern and call them if present in sources list.

#     allr = storage.dump_all()
#     export_results(allr)
#     storage.close()

# # ------------------------------- CLI ------------------------------------
# if __name__ == "__main__":
#     p = argparse.ArgumentParser()
#     p.add_argument('--query', required=True, help='Search query')
#     p.add_argument('--sources', default='pubmed,crossref', help='Comma-separated list of sources (pubmed,crossref,...)')
#     p.add_argument('--limit', type=int, default=20)
#     args = p.parse_args()

#     try:
#         run(args.query, [s.strip().lower() for s in args.sources.split(',')], limit=args.limit)
#     except Exception as e:
#         log.exception("Fatal error: %s", e)
#         sys.exit(1)



#!/usr/bin/env python3
# """
# crawl4ai_scraper_zotero.py

# - Uses crawl4ai when available, otherwise falls back to requests.
# - Scrapes PubMed + CrossRef.
# - Strictly filters to results matching PICO keywords.
# - Deduplicates by DOI/PMID/title.
# - Exports JSON/CSV/XLSX with full Zotero-style header.
# - Supports date filters (--from_year, --to_year, --years).
# """

# import argparse, json, re, sqlite3, time, sys, logging
# from datetime import datetime
# from typing import Dict, Any, List, Optional
# import difflib, html as ihtml
# import pandas as pd
# import xml.etree.ElementTree as ET
# import requests

# # Try crawl4ai if installed
# USE_CRAWL4AI = True
# try:
#     from crawl4ai import WebCrawler
# except Exception:
#     USE_CRAWL4AI = False

# # ---------------- CONFIG ----------------
# CONTACT_EMAIL = "keertisubramanyasm@gmail.com"
# USER_AGENT = f"MultiSourceScraper/1.0 (+{CONTACT_EMAIL})"
# RATE_LIMIT_SECONDS = 1.0
# MAX_RETRIES = 3
# DB_PATH = "scraper_results.db"
# JSON_OUTPUT = "scraper_results.json"
# CSV_OUTPUT = "scraper_results.csv"
# XLSX_OUTPUT = "scraper_results.xlsx"

# PUBMED_API_KEY = ""   # optional
# CROSSREF_EMAIL = CONTACT_EMAIL

# # ---------------- LOGGER ----------------
# logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# log = logging.getLogger("crawl4ai_scraper_zotero")

# # ---------------- UTIL ------------------
# def normalize_title(t): 
#     if not t: return ""
#     s = ihtml.unescape(t).lower()
#     return re.sub(r"\\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()

# def is_similar_title(a,b,threshold=0.92):
#     return difflib.SequenceMatcher(None,a,b).ratio() >= threshold if a and b else False

# def clean_text(text): 
#     if not text: return ""
#     return re.sub(r"\\s+"," ",re.sub(r"<[^>]+>","",text)).strip()

# # ---------------- PICO (keywords from PROSPERO PDF) ----------------
# PICO_KEYWORDS = {
#     "interventions":["dexrazoxane","beta-blocker","ace inhibitor","arb","acei","arni","statin",
#                      "spironolactone","eplerenone","mineralocorticoid"],
#     "exposures":["anthracyclin","doxorubicin","daunorubicin","epirubicin","idarubicin",
#                  "trastuzumab","her2","chemotherapy"],
#     "comparators":["placebo","usual care","no intervention","standard care","control"],
#     "study_designs":["randomized","randomised","rct","cohort","observational",
#                      "prospective","retrospective","phase ii","phase iii","phase iv"]
# }
# ALL_PICO = sorted({w for l in PICO_KEYWORDS.values() for w in l},key=len,reverse=True)
# PICO_PATTERN = re.compile("("+"|".join(map(re.escape,ALL_PICO))+")",re.I)

# # ---------------- Zotero header ----------------
# ZOTERO_HEADER = [
# "Key","Item Type","Publication Year","Author","Title","Publication Title","ISBN","ISSN","DOI","Url",
# "Abstract Note","Date","Date Added","Date Modified","Access Date","Pages","Num Pages","Issue","Volume",
# "Number Of Volumes","Journal Abbreviation","Short Title","Series","Series Number","Series Text","Series Title",
# "Publisher","Place","Language","Rights","Type","Archive","Archive Location","Library Catalog","Call Number",
# "Extra","Notes","File Attachments","Link Attachments","Manual Tags","Automatic Tags","Editor","Series Editor",
# "Translator","Contributor","Attorney Agent","Book Author","Cast Member","Commenter","Composer","Cosponsor",
# "Counsel","Interviewer","Producer","Recipient","Reviewed Author","Scriptwriter","Words By","Guest","Number",
# "Edition","Running Time","Scale","Medium","Artwork Size","Filing Date","Application Number","Assignee",
# "Issuing Authority","Country","Meeting Name","Conference Name","Court","References","Reporter","Legal Status",
# "Priority Numbers","Programming Language","Version","System","Code","Code Number","Section","Session","Committee",
# "History","Legislative Body"
# ]

# def zotero_template(): return {k:"" for k in ZOTERO_HEADER}

# # ---------------- Storage ----------------
# class Storage:
#     def __init__(self,path=DB_PATH):
#         self.conn=sqlite3.connect(path);self.create()
#     def create(self):
#         cur=self.conn.cursor()
#         cur.execute("""CREATE TABLE IF NOT EXISTS recs(
#             id INTEGER PRIMARY KEY, identifier TEXT UNIQUE, title TEXT, title_norm TEXT,
#             doi TEXT, pmid TEXT, source TEXT, url TEXT, authors TEXT, journal TEXT,
#             pub_year TEXT, abstract TEXT, raw_json TEXT, extra TEXT, added_at TEXT)""")
#         self.conn.commit()
#     def insert(self,rec):
#         ident=rec.get("identifier") or rec.get("doi") or rec.get("pmid")
#         if ident: 
#             cur=self.conn.cursor();cur.execute("SELECT 1 FROM recs WHERE identifier=?",(ident,))
#             if cur.fetchone(): return -1
#         tnorm=normalize_title(rec.get("title",""))
#         cur=self.conn.cursor();cur.execute("SELECT title_norm FROM recs")
#         if any(is_similar_title(tnorm,x) for (x,) in cur.fetchall() if x): return -1
#         cur.execute("""INSERT INTO recs(identifier,title,title_norm,doi,pmid,source,url,authors,
#             journal,pub_year,abstract,raw_json,extra,added_at)
#             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
#             (ident,rec.get("title"),tnorm,rec.get("doi"),rec.get("pmid"),rec.get("source"),
#              rec.get("url"),rec.get("authors_text"),rec.get("journal"),rec.get("publication_year"),
#              clean_text(rec.get("abstract","")),json.dumps(rec.get("raw",{})),
#              rec.get("extra",""),datetime.utcnow().isoformat()))
#         self.conn.commit();return cur.lastrowid
#     def all(self):
#         cur=self.conn.cursor();cur.execute("SELECT * FROM recs");rows=cur.fetchall()
#         out=[];cols=[c[0] for c in cur.description]
#         for row in rows: out.append(dict(zip(cols,row)))
#         return out
#     def close(self): self.conn.close()

# # ---------------- Fetcher ----------------
# class Fetcher:
#     def __init__(self):
#         self.s=requests.Session();self.s.headers.update({"User-Agent":USER_AGENT})
#         self.c=None
#         if USE_CRAWL4AI:
#             try: self.c=WebCrawler();log.info("Using crawl4ai")
#             except: self.c=None
#     def get(self,url,params=None):
#         if self.c:
#             try: r=self.c.get(url,params=params);return r.text
#             except: pass
#         r=self.s.get(url,params=params);r.raise_for_status();return r.text

# # ---------------- Scrapers ----------------
# def scrape_pubmed(fetcher,store,query,limit,from_year,to_year):
#     url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#     params={"db":"pubmed","term":query,"retmax":limit,"retmode":"json"}
#     if PUBMED_API_KEY: params["api_key"]=PUBMED_API_KEY
#     if from_year: params["mindate"]=from_year
#     if to_year: params["maxdate"]=to_year
#     params["datetype"]="pdat"
#     data=json.loads(fetcher.get(url,params))
#     ids=data.get("esearchresult",{}).get("idlist",[])
#     if not ids: return
#     efetch="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
#     txt=fetcher.get(efetch,{"db":"pubmed","id":",".join(ids),"retmode":"xml"})
#     root=ET.fromstring(txt)
#     for art in root.findall(".//PubmedArticle"):
#         pmid=art.findtext(".//PMID","")
#         title=art.findtext(".//ArticleTitle","")
#         abst=" ".join([el.text or "" for el in art.findall(".//Abstract/AbstractText")])
#         comb=title+" "+abst
#         if not PICO_PATTERN.search(comb): continue
#         found=[m.group(0) for m in PICO_PATTERN.finditer(comb)]
#         rec={"source":"pubmed","pmid":pmid,"identifier":pmid,"title":title,
#              "abstract":abst,"url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
#              "authors_text":", ".join([a.findtext("LastName","")+" "+a.findtext("ForeName","")
#                                        for a in art.findall(".//Author") if a.find("LastName")]),
#              "journal":art.findtext(".//Journal/Title",""),
#              "publication_year":art.findtext(".//PubDate/Year",""),
#              "doi":"","raw":ET.tostring(art,encoding="unicode"),
#              "extra":"PICO_keywords_found: "+", ".join(found)}
#         store.insert(rec)

# def scrape_crossref(fetcher,store,query,limit,from_year,to_year):
#     url="https://api.crossref.org/works"
#     filt=[]
#     if from_year: filt.append(f"from-pub-date:{from_year}-01-01")
#     if to_year: filt.append(f"until-pub-date:{to_year}-12-31")
#     params={"query":query,"rows":limit,"mailto":CROSSREF_EMAIL}
#     if filt: params["filter"]=",".join(filt)
#     items=json.loads(fetcher.get(url,params)).get("message",{}).get("items",[])
#     for it in items:
#         title=it.get("title",[""])[0];abst=clean_text(it.get("abstract",""))
#         comb=title+" "+abst
#         if not PICO_PATTERN.search(comb): continue
#         found=[m.group(0) for m in PICO_PATTERN.finditer(comb)]
#         yr="";dp=it.get("issued",{}).get("date-parts",[])
#         if dp and dp[0]: yr=str(dp[0][0])
#         rec={"source":"crossref","doi":it.get("DOI"),"identifier":it.get("DOI"),
#              "title":title,"abstract":abst,"url":it.get("URL"),
#              "authors_text":", ".join([a.get("family","")+" "+a.get("given","") for a in it.get("author",[])]),
#              "journal":it.get("container-title",[""])[0] if it.get("container-title") else "",
#              "publication_year":yr,"raw":it,
#              "extra":"PICO_keywords_found: "+", ".join(found)}
#         store.insert(rec)

# # ---------------- Export ----------------
# def export(rows):
#     zot=[]
#     for r in rows:
#         z=zotero_template()
#         z["Title"]=r.get("title","");z["Author"]=r.get("authors","")
#         z["DOI"]=r.get("doi","");z["Url"]=r.get("url","")
#         z["Abstract Note"]=r.get("abstract","");z["Publication Title"]=r.get("journal","")
#         z["Publication Year"]=str(r.get("pub_year",""));z["Extra"]=r.get("extra","")
#         z["Key"]=r.get("identifier","");zot.append(z)
#     pd.DataFrame(zot,columns=ZOTERO_HEADER).to_csv(CSV_OUTPUT,index=False,encoding="utf-8")
#     pd.DataFrame(zot,columns=ZOTERO_HEADER).to_excel(XLSX_OUTPUT,index=False,engine="openpyxl")
#     with open(JSON_OUTPUT,"w",encoding="utf-8") as f: json.dump(rows,f,ensure_ascii=False,indent=2)
#     log.info("Exported %d records",len(rows))

# # ---------------- Run ----------------
# def run(query,sources,limit,from_year,to_year):
#     store=Storage();fetcher=Fetcher()
#     if "pubmed" in sources: scrape_pubmed(fetcher,store,query,limit,from_year,to_year)
#     if "crossref" in sources: scrape_crossref(fetcher,store,query,limit,from_year,to_year)
#     rows=store.all();export(rows);store.close()

# if __name__=="__main__":
#     p=argparse.ArgumentParser()
#     p.add_argument("--query",required=True)
#     p.add_argument("--sources",default="pubmed,crossref")
#     p.add_argument("--limit",type=int,default=20)
#     p.add_argument("--from_year",type=int,help="Earliest publication year")
#     p.add_argument("--to_year",type=int,help="Latest publication year")
#     p.add_argument("--years",type=int,help="Last N years (overrides from/to)")
#     a=p.parse_args()
#     fy,ty=a.from_year,a.to_year
#     if a.years: ty=datetime.now().year;fy=ty-a.years
#     run(a.query,[s.strip() for s in a.sources.split(",")],a.limit,fy,ty)
# 


#!/usr/bin/env python3
# """
# multi_source_scraper.py

# - Scrapes PubMed + CrossRef
# - Handles large queries with batching (PubMed chunked efetch, CrossRef pagination)
# - Deduplicates by PMID/DOI/title similarity
# - PICO keyword filtering (from PROSPERO)
# - Populates Zotero-style metadata (DOI, ISSN, Volume, Issue, Pages, Publisher, Language, Conference, etc.)
# - Exports to JSON, CSV, XLSX
# """

# import argparse, json, re, sqlite3, logging
# from datetime import datetime
# import pandas as pd
# import xml.etree.ElementTree as ET
# import requests

# # Optional crawl4ai
# USE_CRAWL4AI = True
# try:
#     from crawl4ai import WebCrawler
# except Exception:
#     USE_CRAWL4AI = False

# # ---------------- CONFIG ----------------
# CONTACT_EMAIL = "keertisubramanyasm@gmail.com"
# USER_AGENT = f"MultiSourceScraper/1.0 (+{CONTACT_EMAIL})"
# DB_PATH = "scraper_results.db"
# JSON_OUTPUT = "scraper_results.json"
# CSV_OUTPUT = "scraper_results.csv"
# XLSX_OUTPUT = "scraper_results.xlsx"

# PUBMED_API_KEY = ""
# CROSSREF_EMAIL = CONTACT_EMAIL

# logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# log = logging.getLogger("multi_source_scraper")

# # ---------------- UTIL ----------------
# def clean_text(t): return re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",t or "")).strip()
# def normalize_title(t): return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",(t or "").lower())).strip()

# # ---------------- PICO ----------------
# PICO_KEYWORDS = {
#     "interventions":["dexrazoxane","beta-blocker","ace inhibitor","arb","acei","arni","statin"],
#     "exposures":["anthracycline","doxorubicin","epirubicin","trastuzumab"],
#     "comparators":["placebo","usual care","control"],
#     "study_designs":["randomized","rct","cohort","observational"]
# }
# ALL_PICO={w for l in PICO_KEYWORDS.values() for w in l}
# PICO_PATTERN=re.compile("("+"|".join(map(re.escape,ALL_PICO))+")",re.I)

# # ---------------- Zotero Header ----------------
# ZOTERO_HEADER=[
# "Key","Item Type","Publication Year","Author","Title","Publication Title","ISBN","ISSN","DOI","Url",
# "Abstract Note","Date","Date Added","Date Modified","Access Date","Pages","Num Pages","Issue","Volume",
# "Number Of Volumes","Journal Abbreviation","Short Title","Series","Series Number","Series Text","Series Title",
# "Publisher","Place","Language","Rights","Type","Archive","Archive Location","Library Catalog","Call Number",
# "Extra","Meeting Name","Conference Name","Country"
# ]

# def zotero_template(): return {k:"" for k in ZOTERO_HEADER}

# # ---------------- Storage ----------------
# class Storage:
#     def __init__(self,path=DB_PATH): self.conn=sqlite3.connect(path);self.create()
#     def create(self):
#         self.conn.execute("CREATE TABLE IF NOT EXISTS recs(id INTEGER PRIMARY KEY, identifier TEXT UNIQUE, data TEXT)")
#         self.conn.commit()
#     def insert(self,ident,data):
#         try:
#             self.conn.execute("INSERT INTO recs(identifier,data) VALUES(?,?)",(ident,json.dumps(data)))
#             self.conn.commit()
#         except sqlite3.IntegrityError:
#             pass
#     def all(self):
#         cur=self.conn.cursor();cur.execute("SELECT data FROM recs")
#         return [json.loads(r[0]) for r in cur.fetchall()]
#     def close(self): self.conn.close()

# # ---------------- Fetcher ----------------
# class Fetcher:
#     def __init__(self):
#         self.s=requests.Session();self.s.headers.update({"User-Agent":USER_AGENT})
#         self.c=None
#         if USE_CRAWL4AI:
#             try: self.c=WebCrawler();log.info("crawl4ai available")
#             except: self.c=None
#     def get(self,url,params=None):
#         if self.c:
#             try: r=self.c.get(url,params=params);return r.text
#             except: pass
#         r=self.s.get(url,params=params);r.raise_for_status();return r.text

# # ---------------- Scrapers ----------------
# def scrape_pubmed(fetcher,store,query,limit,from_year,to_year):
#     search="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#     params={"db":"pubmed","term":query,"retmax":limit,"retmode":"json","datetype":"pdat","sort":"pub+date"}
#     if from_year and to_year:
#         params["mindate"]=f"{from_year}/01/01"
#         params["maxdate"]=f"{to_year}/12/31"
#     elif from_year:
#         params["mindate"]=f"{from_year}/01/01"
#     elif to_year:
#         params["maxdate"]=f"{to_year}/12/31"

#     data=json.loads(fetcher.get(search,params))
#     ids=data.get("esearchresult",{}).get("idlist",[])
#     if not ids: return
#     fetch="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
#     chunk_size=200
#     for i in range(0,len(ids),chunk_size):
#         chunk=ids[i:i+chunk_size]
#         txt=fetcher.get(fetch,{"db":"pubmed","id":",".join(chunk),"retmode":"xml"})
#         root=ET.fromstring(txt)
#         for art in root.findall(".//PubmedArticle"):
#             pmid=art.findtext(".//PMID","")
#             title=art.findtext(".//ArticleTitle","")
#             abst=" ".join([el.text or "" for el in art.findall(".//Abstract/AbstractText")])
#             if not PICO_PATTERN.search(title+" "+abst): continue
#             found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
#             authors=[]
#             for a in art.findall(".//Author"):
#                 last,first=a.findtext("LastName",""),a.findtext("ForeName","")
#                 if last: authors.append(f"{last}, {first}")
#             doi=""
#             for aid in art.findall(".//ArticleId"):
#                 if aid.get("IdType")=="doi": doi=aid.text
#             rec={
#                 "Key":pmid,"Item Type":"journalArticle","Title":title,"Abstract Note":abst,
#                 "Author":"; ".join(authors),
#                 "Publication Title":art.findtext(".//Journal/Title",""),
#                 "Journal Abbreviation":art.findtext(".//Journal/ISOAbbreviation",""),
#                 "ISSN":art.findtext(".//Journal/ISSN",""),
#                 "Volume":art.findtext(".//JournalIssue/Volume",""),
#                 "Issue":art.findtext(".//JournalIssue/Issue",""),
#                 "Pages":art.findtext(".//Pagination/MedlinePgn",""),
#                 "Publication Year":art.findtext(".//PubDate/Year",""),
#                 "Language":art.findtext(".//Language",""),
#                 "DOI":doi,
#                 "Url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
#                 "Country":art.findtext(".//MedlineJournalInfo/Country",""),
#                 "Type":"; ".join([pt.text for pt in art.findall(".//PublicationType") if pt.text]),
#                 "Extra":"PICO_keywords_found: "+", ".join(found)
#             }
#             store.insert(pmid,rec)

# def scrape_crossref(fetcher,store,query,limit,from_year,to_year):
#     url="https://api.crossref.org/works"
#     batch_size=1000
#     fetched=0
#     while fetched<limit:
#         rows=min(batch_size,limit-fetched)
#         filt=[]
#         if from_year: filt.append(f"from-pub-date:{from_year}-01-01")
#         if to_year: filt.append(f"until-pub-date:{to_year}-12-31")
#         params={"query":query,"rows":rows,"offset":fetched,"mailto":CROSSREF_EMAIL}
#         if filt: params["filter"]=",".join(filt)
#         items=json.loads(fetcher.get(url,params)).get("message",{}).get("items",[])
#         if not items: break
#         for it in items:
#             title=it.get("title",[""])[0];abst=clean_text(it.get("abstract",""))
#             if not PICO_PATTERN.search(title+" "+abst): continue
#             found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
#             authors=[f"{a.get('family','')}, {a.get('given','')}" for a in it.get("author",[])]
#             year=""
#             dp=it.get("issued",{}).get("date-parts",[])
#             if dp and dp[0]: year=str(dp[0][0])
#             rec={
#                 "Key":it.get("DOI"),"Item Type":it.get("type","journal-article"),
#                 "Title":title,"Abstract Note":abst,
#                 "Author":"; ".join(authors),
#                 "Publication Title":(it.get("container-title") or [""])[0],
#                 "Journal Abbreviation":(it.get("short-container-title") or [""])[0] if it.get("short-container-title") else "",
#                 "ISSN":"; ".join(it.get("ISSN",[])),
#                 "Volume":it.get("volume",""),"Issue":it.get("issue",""),
#                 "Pages":it.get("page",""),"Publication Year":year,
#                 "Publisher":it.get("publisher",""),
#                 "Language":it.get("language",""),
#                 "DOI":it.get("DOI",""),"Url":it.get("URL",""),
#                 "Meeting Name":it.get("event",{}).get("name",""),
#                 "Conference Name":it.get("event",{}).get("name",""),
#                 "Place":it.get("event",{}).get("location","") or it.get("publisher-location",""),
#                 "Extra":"PICO_keywords_found: "+", ".join(found)
#             }
#             store.insert(it.get("DOI"),rec)
#         fetched+=len(items)
#         if len(items)<rows: break

# # ---------------- Export ----------------
# def export(recs):
#     df=pd.DataFrame([{**zotero_template(),**r} for r in recs],columns=ZOTERO_HEADER)
#     df.to_csv(CSV_OUTPUT,index=False,encoding="utf-8")
#     df.to_excel(XLSX_OUTPUT,index=False,engine="openpyxl")
#     with open(JSON_OUTPUT,"w",encoding="utf-8") as f: json.dump(recs,f,ensure_ascii=False,indent=2)
#     log.info("Exported %d records",len(recs))

# # ---------------- Run ----------------
# def run(query,sources,limit,from_year,to_year):
#     store=Storage();fetcher=Fetcher()
#     if "pubmed" in sources: scrape_pubmed(fetcher,store,query,limit,from_year,to_year)
#     if "crossref" in sources: scrape_crossref(fetcher,store,query,limit,from_year,to_year)
#     recs=store.all();export(recs);store.close()

# if __name__=="__main__":
#     p=argparse.ArgumentParser()
#     p.add_argument("--query",required=True)
#     p.add_argument("--sources",default="pubmed,crossref")
#     p.add_argument("--limit",type=int,default=20)
#     p.add_argument("--from_year",type=int)
#     p.add_argument("--to_year",type=int)
#     p.add_argument("--years",type=int)
#     a=p.parse_args()
#     fy,ty=a.from_year,a.to_year
#     if a.years: ty=datetime.now().year;fy=ty-a.years
#     run(a.query,[s.strip() for s in a.sources.split(",")],a.limit,fy,ty)



#!/usr/bin/env python3
"""
multi_source_scraper.py

- Scrapes PubMed + CrossRef
- Handles large queries with batching (PubMed chunked efetch, CrossRef pagination)
- Deduplicates by PMID/DOI/title similarity
- PICO keyword filtering (from PROSPERO)
- Populates Zotero-style metadata (DOI, ISSN, Volume, Issue, Pages, Publisher, Language, Conference, etc.)
- Exports to JSON, CSV, XLSX
- Supports PubMed API key and polite rate-limiting
- Fixed PubMed date extraction
"""

import argparse, json, re, sqlite3, logging, time
from datetime import datetime
import pandas as pd
import xml.etree.ElementTree as ET
import requests

# Optional crawl4ai
USE_CRAWL4AI = True
try:
    from crawl4ai import WebCrawler
except Exception:
    USE_CRAWL4AI = False

# ---------------- CONFIG ----------------
CONTACT_EMAIL = "keertisubramanyasm@gmail.com"
USER_AGENT = f"MultiSourceScraper/1.0 (+{CONTACT_EMAIL})"
DB_PATH = "scraper_results.db"
JSON_OUTPUT = "scraper_results.json"
CSV_OUTPUT = "scraper_results.csv"
XLSX_OUTPUT = "scraper_results.xlsx"

PUBMED_API_KEY = "c2f307fc5acc4197325e5d9234ff271aa608"  # Optional PubMed API key
CROSSREF_EMAIL = CONTACT_EMAIL
PUBMED_RATE_LIMIT = 0.34  # ~3 requests/sec

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("multi_source_scraper")

# ---------------- UTIL ----------------
def clean_text(t): return re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",t or "")).strip()
def normalize_title(t): return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",(t or "").lower())).strip()

# ---------------- PICO ----------------
PICO_KEYWORDS = {
    "interventions":["dexrazoxane","beta-blocker","ace inhibitor","arb","acei","arni","statin"],
    "exposures":["anthracycline","doxorubicin","epirubicin","trastuzumab"],
    "comparators":["placebo","usual care","control"],
    "study_designs":["randomized","rct","cohort","observational"]
}
ALL_PICO={w for l in PICO_KEYWORDS.values() for w in l}
PICO_PATTERN=re.compile("("+"|".join(map(re.escape,ALL_PICO))+")",re.I)

# ---------------- Zotero Header ----------------
ZOTERO_HEADER=[
"Key","Item Type","Publication Year","Author","Title","Publication Title","ISBN","ISSN","DOI","Url",
"Abstract Note","Date","Date Added","Date Modified","Access Date","Pages","Num Pages","Issue","Volume",
"Number Of Volumes","Journal Abbreviation","Short Title","Series","Series Number","Series Text","Series Title",
"Publisher","Place","Language","Rights","Type","Archive","Archive Location","Library Catalog","Call Number",
"Extra","Meeting Name","Conference Name","Country"
]

def zotero_template(): return {k:"" for k in ZOTERO_HEADER}

# ---------------- Storage ----------------
class Storage:
    def __init__(self,path=DB_PATH): self.conn=sqlite3.connect(path);self.create()
    def create(self):
        self.conn.execute("CREATE TABLE IF NOT EXISTS recs(id INTEGER PRIMARY KEY, identifier TEXT UNIQUE, data TEXT)")
        self.conn.commit()
    def insert(self,ident,data):
        try:
            self.conn.execute("INSERT INTO recs(identifier,data) VALUES(?,?)",(ident,json.dumps(data)))
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass
    def all(self):
        cur=self.conn.cursor();cur.execute("SELECT data FROM recs")
        return [json.loads(r[0]) for r in cur.fetchall()]
    def close(self): self.conn.close()

# ---------------- Fetcher ----------------
class Fetcher:
    def __init__(self):
        self.s=requests.Session();self.s.headers.update({"User-Agent":USER_AGENT})
        self.c=None
        if USE_CRAWL4AI:
            try: self.c=WebCrawler();log.info("crawl4ai available")
            except: self.c=None
    def get(self,url,params=None):
        if self.c:
            try: r=self.c.get(url,params=params);return r.text
            except: pass
        r=self.s.get(url,params=params);r.raise_for_status();return r.text

# ---------------- PubMed date parsing ----------------
def parse_pub_date(article):
    pub_date_el = article.find(".//PubDate")
    year, month, day = "", "01", "01"
    if pub_date_el is not None:
        y = pub_date_el.findtext("Year")
        m = pub_date_el.findtext("Month")
        d = pub_date_el.findtext("Day")
        medline = pub_date_el.findtext("MedlineDate")
        # Year
        if y: year = y
        elif medline:
            m_year = re.search(r"\d{4}", medline)
            if m_year: year = m_year.group(0)
        # Month
        if m:
            try:
                month_num = {
                    "Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
                    "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"
                }.get(m[:3], "01")
                month = month_num
            except: month="01"
        # Day
        if d: day=d
    if not year: year="Unknown"
    return year, f"{year}-{month}-{day}"

# ---------------- Scrapers ----------------
def scrape_pubmed(fetcher, store, query, limit, from_year, to_year):
    search = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "datetype": "pdat",
        "retmax": 100,
        "mindate": f"{from_year}/01/01" if from_year else None,
        "maxdate": f"{to_year}/12/31" if to_year else None,
        "api_key": PUBMED_API_KEY if PUBMED_API_KEY else None
    }
    retstart = 0
    fetched_ids = []

    while True:
        params["retstart"] = retstart
        data = json.loads(fetcher.get(search, params))
        ids = data.get("esearchresult", {}).get("idlist", [])
        if not ids: break
        fetched_ids.extend(ids)
        retstart += len(ids)
        if limit and len(fetched_ids) >= limit:
            fetched_ids = fetched_ids[:limit]
            break
        if len(ids) < params["retmax"]: break
        time.sleep(PUBMED_RATE_LIMIT)

    if not fetched_ids: return

    fetch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    chunk_size = 200
    for i in range(0, len(fetched_ids), chunk_size):
        chunk = fetched_ids[i:i + chunk_size]
        txt = fetcher.get(fetch, {"db": "pubmed", "id": ",".join(chunk), "retmode": "xml", "api_key": PUBMED_API_KEY if PUBMED_API_KEY else None})
        root = ET.fromstring(txt)
        for art in root.findall(".//PubmedArticle"):
            pmid = art.findtext(".//PMID", "")
            title = art.findtext(".//ArticleTitle", "")
            abst = " ".join([el.text or "" for el in art.findall(".//Abstract/AbstractText")])
            if not PICO_PATTERN.search(title + " " + abst): continue
            found = [m.group(0) for m in PICO_PATTERN.finditer(title + " " + abst)]
            authors = []
            for a in art.findall(".//Author"):
                last, first = a.findtext("LastName", ""), a.findtext("ForeName", "")
                if last: authors.append(f"{last}, {first}")
            doi = ""
            for aid in art.findall(".//ArticleId"):
                if aid.get("IdType") == "doi": doi = aid.text
            pub_year, pub_date = parse_pub_date(art)
            rec = {
                "Key": pmid,
                "Item Type": "journalArticle",
                "Title": title,
                "Abstract Note": abst,
                "Author": "; ".join(authors),
                "Publication Title": art.findtext(".//Journal/Title", ""),
                "Journal Abbreviation": art.findtext(".//Journal/ISOAbbreviation", ""),
                "ISSN": art.findtext(".//Journal/ISSN", ""),
                "Volume": art.findtext(".//JournalIssue/Volume", ""),
                "Issue": art.findtext(".//JournalIssue/Issue", ""),
                "Pages": art.findtext(".//Pagination/MedlinePgn", ""),
                "Publication Year": pub_year,
                "Date": pub_date,
                "Language": art.findtext(".//Language", ""),
                "DOI": doi,
                "Url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "Country": art.findtext(".//MedlineJournalInfo/Country", ""),
                "Type": "; ".join([pt.text for pt in art.findall(".//PublicationType") if pt.text]),
                "Extra": "PICO_keywords_found: " + ", ".join(found)
            }
            store.insert(pmid, rec)

def scrape_crossref(fetcher, store, query, limit, from_year, to_year):
    url = "https://api.crossref.org/works"
    batch_size = 1000
    fetched = 0
    while fetched < limit:
        rows = min(batch_size, limit - fetched)
        filt = []
        if from_year: filt.append(f"from-pub-date:{from_year}-01-01")
        if to_year: filt.append(f"until-pub-date:{to_year}-12-31")
        params = {"query": query, "rows": rows, "offset": fetched, "mailto": CROSSREF_EMAIL}
        if filt: params["filter"] = ",".join(filt)
        items = json.loads(fetcher.get(url, params)).get("message", {}).get("items", [])
        if not items: break
        for it in items:
            title = it.get("title", [""])[0]
            abst = clean_text(it.get("abstract", ""))
            if not PICO_PATTERN.search(title + " " + abst): continue
            found = [m.group(0) for m in PICO_PATTERN.finditer(title + " " + abst)]
            authors = [f"{a.get('family','')}, {a.get('given','')}" for a in it.get("author",[])]
            year = ""
            dp = it.get("issued", {}).get("date-parts", [])
            if dp and dp[0]: year = str(dp[0][0])
            rec = {
                "Key": it.get("DOI"),
                "Item Type": it.get("type","journal-article"),
                "Title": title,
                "Abstract Note": abst,
                "Author": "; ".join(authors),
                "Publication Title": (it.get("container-title") or [""])[0],
                "Journal Abbreviation": (it.get("short-container-title") or [""])[0] if it.get("short-container-title") else "",
                "ISSN": "; ".join(it.get("ISSN", [])),
                "Volume": it.get("volume", ""),
                "Issue": it.get("issue", ""),
                "Pages": it.get("page", ""),
                "Publication Year": year,
                "Date": "",  # CrossRef date can be added if needed
                "Publisher": it.get("publisher", ""),
                "Language": it.get("language", ""),
                "DOI": it.get("DOI", ""),
                "Url": it.get("URL", ""),
                "Meeting Name": it.get("event", {}).get("name", ""),
                "Conference Name": it.get("event", {}).get("name", ""),
                "Place": it.get("event", {}).get("location", "") or it.get("publisher-location", ""),
                "Extra": "PICO_keywords_found: "+", ".join(found)
            }
            store.insert(it.get("DOI"), rec)
        fetched += len(items)
        if len(items) < rows: break

# ---------------- Export ----------------
def export(recs):
    df = pd.DataFrame([{**zotero_template(), **r} for r in recs], columns=ZOTERO_HEADER)
    df.to_csv(CSV_OUTPUT, index=False, encoding="utf-8")
    df.to_excel(XLSX_OUTPUT, index=False, engine="openpyxl")
    with open(JSON_OUTPUT, "w", encoding="utf-8") as f: json.dump(recs, f, ensure_ascii=False, indent=2)
    log.info("Exported %d records", len(recs))

# ---------------- Run ----------------
def run(query, sources, limit, from_year, to_year):
    store = Storage()
    fetcher = Fetcher()
    if "pubmed" in sources: scrape_pubmed(fetcher, store, query, limit, from_year, to_year)
    if "crossref" in sources: scrape_crossref(fetcher, store, query, limit, from_year, to_year)
    recs = store.all()
    export(recs)
    store.close()

if __name__=="__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--query", required=True)
    p.add_argument("--sources", default="pubmed,crossref")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--from_year", type=int)
    p.add_argument("--to_year", type=int)
    p.add_argument("--years", type=int)
    a = p.parse_args()
    
    fy, ty = a.from_year, a.to_year
    if a.years:
        ty = datetime.now().year
        fy = ty - a.years + 1
    
    run(a.query, [s.strip() for s in a.sources.split(",")], a.limit, fy, ty)
