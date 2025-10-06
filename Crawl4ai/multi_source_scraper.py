
# This version scrapes the data with limited field

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



## This Version Scarpes the more columns but have limitation with the date
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
# """
# multi_source_scraper.py

# - Scrapes PubMed + CrossRef
# - Handles large queries with batching (PubMed chunked efetch, CrossRef pagination)
# - Deduplicates by PMID/DOI/title similarity
# - PICO keyword filtering (from PROSPERO)
# - Populates Zotero-style metadata (DOI, ISSN, Volume, Issue, Pages, Publisher, Language, Conference, etc.)
# - Exports to JSON, CSV, XLSX
# - Supports PubMed API key and polite rate-limiting
# - Fixed PubMed date extraction
# """

# import argparse, json, re, sqlite3, logging, time
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

# PUBMED_API_KEY = "c2f307fc5acc4197325e5d9234ff271aa608"  # Optional PubMed API key
# CROSSREF_EMAIL = CONTACT_EMAIL
# PUBMED_RATE_LIMIT = 0.34  # ~3 requests/sec

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

# # ---------------- PubMed date parsing ----------------
# def parse_pub_date(article):
#     pub_date_el = article.find(".//PubDate")
#     year, month, day = "", "01", "01"
#     if pub_date_el is not None:
#         y = pub_date_el.findtext("Year")
#         m = pub_date_el.findtext("Month")
#         d = pub_date_el.findtext("Day")
#         medline = pub_date_el.findtext("MedlineDate")
#         # Year
#         if y: year = y
#         elif medline:
#             m_year = re.search(r"\d{4}", medline)
#             if m_year: year = m_year.group(0)
#         # Month
#         if m:
#             try:
#                 month_num = {
#                     "Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
#                     "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"
#                 }.get(m[:3], "01")
#                 month = month_num
#             except: month="01"
#         # Day
#         if d: day=d
#     if not year: year="Unknown"
#     return year, f"{year}-{month}-{day}"

# # ---------------- Scrapers ----------------
# def scrape_pubmed(fetcher, store, query, limit, from_year, to_year):
#     search = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#     params = {
#         "db": "pubmed",
#         "term": query,
#         "retmode": "json",
#         "datetype": "pdat",
#         "retmax": 100,
#         "mindate": f"{from_year}/01/01" if from_year else None,
#         "maxdate": f"{to_year}/12/31" if to_year else None,
#         "api_key": PUBMED_API_KEY if PUBMED_API_KEY else None
#     }
#     retstart = 0
#     fetched_ids = []

#     while True:
#         params["retstart"] = retstart
#         data = json.loads(fetcher.get(search, params))
#         ids = data.get("esearchresult", {}).get("idlist", [])
#         if not ids: break
#         fetched_ids.extend(ids)
#         retstart += len(ids)
#         if limit and len(fetched_ids) >= limit:
#             fetched_ids = fetched_ids[:limit]
#             break
#         if len(ids) < params["retmax"]: break
#         time.sleep(PUBMED_RATE_LIMIT)

#     if not fetched_ids: return

#     fetch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
#     chunk_size = 200
#     for i in range(0, len(fetched_ids), chunk_size):
#         chunk = fetched_ids[i:i + chunk_size]
#         txt = fetcher.get(fetch, {"db": "pubmed", "id": ",".join(chunk), "retmode": "xml", "api_key": PUBMED_API_KEY if PUBMED_API_KEY else None})
#         root = ET.fromstring(txt)
#         for art in root.findall(".//PubmedArticle"):
#             pmid = art.findtext(".//PMID", "")
#             title = art.findtext(".//ArticleTitle", "")
#             abst = " ".join([el.text or "" for el in art.findall(".//Abstract/AbstractText")])
#             if not PICO_PATTERN.search(title + " " + abst): continue
#             found = [m.group(0) for m in PICO_PATTERN.finditer(title + " " + abst)]
#             authors = []
#             for a in art.findall(".//Author"):
#                 last, first = a.findtext("LastName", ""), a.findtext("ForeName", "")
#                 if last: authors.append(f"{last}, {first}")
#             doi = ""
#             for aid in art.findall(".//ArticleId"):
#                 if aid.get("IdType") == "doi": doi = aid.text
#             pub_year, pub_date = parse_pub_date(art)
#             rec = {
#                 "Key": pmid,
#                 "Item Type": "journalArticle",
#                 "Title": title,
#                 "Abstract Note": abst,
#                 "Author": "; ".join(authors),
#                 "Publication Title": art.findtext(".//Journal/Title", ""),
#                 "Journal Abbreviation": art.findtext(".//Journal/ISOAbbreviation", ""),
#                 "ISSN": art.findtext(".//Journal/ISSN", ""),
#                 "Volume": art.findtext(".//JournalIssue/Volume", ""),
#                 "Issue": art.findtext(".//JournalIssue/Issue", ""),
#                 "Pages": art.findtext(".//Pagination/MedlinePgn", ""),
#                 "Publication Year": pub_year,
#                 "Date": pub_date,
#                 "Language": art.findtext(".//Language", ""),
#                 "DOI": doi,
#                 "Url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
#                 "Country": art.findtext(".//MedlineJournalInfo/Country", ""),
#                 "Type": "; ".join([pt.text for pt in art.findall(".//PublicationType") if pt.text]),
#                 "Extra": "PICO_keywords_found: " + ", ".join(found)
#             }
#             store.insert(pmid, rec)

# def scrape_crossref(fetcher, store, query, limit, from_year, to_year):
#     url = "https://api.crossref.org/works"
#     batch_size = 1000
#     fetched = 0
#     while fetched < limit:
#         rows = min(batch_size, limit - fetched)
#         filt = []
#         if from_year: filt.append(f"from-pub-date:{from_year}-01-01")
#         if to_year: filt.append(f"until-pub-date:{to_year}-12-31")
#         params = {"query": query, "rows": rows, "offset": fetched, "mailto": CROSSREF_EMAIL}
#         if filt: params["filter"] = ",".join(filt)
#         items = json.loads(fetcher.get(url, params)).get("message", {}).get("items", [])
#         if not items: break
#         for it in items:
#             title = it.get("title", [""])[0]
#             abst = clean_text(it.get("abstract", ""))
#             if not PICO_PATTERN.search(title + " " + abst): continue
#             found = [m.group(0) for m in PICO_PATTERN.finditer(title + " " + abst)]
#             authors = [f"{a.get('family','')}, {a.get('given','')}" for a in it.get("author",[])]
#             year = ""
#             dp = it.get("issued", {}).get("date-parts", [])
#             if dp and dp[0]: year = str(dp[0][0])
#             rec = {
#                 "Key": it.get("DOI"),
#                 "Item Type": it.get("type","journal-article"),
#                 "Title": title,
#                 "Abstract Note": abst,
#                 "Author": "; ".join(authors),
#                 "Publication Title": (it.get("container-title") or [""])[0],
#                 "Journal Abbreviation": (it.get("short-container-title") or [""])[0] if it.get("short-container-title") else "",
#                 "ISSN": "; ".join(it.get("ISSN", [])),
#                 "Volume": it.get("volume", ""),
#                 "Issue": it.get("issue", ""),
#                 "Pages": it.get("page", ""),
#                 "Publication Year": year,
#                 "Date": "",  # CrossRef date can be added if needed
#                 "Publisher": it.get("publisher", ""),
#                 "Language": it.get("language", ""),
#                 "DOI": it.get("DOI", ""),
#                 "Url": it.get("URL", ""),
#                 "Meeting Name": it.get("event", {}).get("name", ""),
#                 "Conference Name": it.get("event", {}).get("name", ""),
#                 "Place": it.get("event", {}).get("location", "") or it.get("publisher-location", ""),
#                 "Extra": "PICO_keywords_found: "+", ".join(found)
#             }
#             store.insert(it.get("DOI"), rec)
#         fetched += len(items)
#         if len(items) < rows: break

# # ---------------- Export ----------------
# def export(recs):
#     df = pd.DataFrame([{**zotero_template(), **r} for r in recs], columns=ZOTERO_HEADER)
#     df.to_csv(CSV_OUTPUT, index=False, encoding="utf-8")
#     df.to_excel(XLSX_OUTPUT, index=False, engine="openpyxl")
#     with open(JSON_OUTPUT, "w", encoding="utf-8") as f: json.dump(recs, f, ensure_ascii=False, indent=2)
#     log.info("Exported %d records", len(recs))

# # ---------------- Run ----------------
# def run(query, sources, limit, from_year, to_year):
#     store = Storage()
#     fetcher = Fetcher()
#     if "pubmed" in sources: scrape_pubmed(fetcher, store, query, limit, from_year, to_year)
#     if "crossref" in sources: scrape_crossref(fetcher, store, query, limit, from_year, to_year)
#     recs = store.all()
#     export(recs)
#     store.close()

# if __name__=="__main__":
#     p = argparse.ArgumentParser()
#     p.add_argument("--query", required=True)
#     p.add_argument("--sources", default="pubmed,crossref")
#     p.add_argument("--limit", type=int, default=20)
#     p.add_argument("--from_year", type=int)
#     p.add_argument("--to_year", type=int)
#     p.add_argument("--years", type=int)
#     a = p.parse_args()
    
#     fy, ty = a.from_year, a.to_year
#     if a.years:
#         ty = datetime.now().year
#         fy = ty - a.years + 1
    
#     run(a.query, [s.strip() for s in a.sources.split(",")], a.limit, fy, ty)



#!/usr/bin/env python3
# """
# generalized_scraper.py

# - Unified, pluggable scraper framework
# - Built-in scrapers: PubMed, CrossRef
# - Deduplication + merging: DOI > PMID > title_hash
# - PICO filtering, PubMed date parsing, CrossRef date parsing
# - Exports: JSON, CSV, XLSX
# - Rate-limiting + PubMed API key support
# """

# import argparse
# import json
# import logging
# import re
# import sqlite3
# import time
# from datetime import datetime
# import hashlib
# import xml.etree.ElementTree as ET

# import pandas as pd
# import requests

# # ---------------- CONFIG ----------------
# CONTACT_EMAIL = "keertisubramanyasm@gmail.com"
# USER_AGENT = f"GeneralizedScraper/1.0 (+{CONTACT_EMAIL})"
# DB_PATH = "scraper_results.db"
# JSON_OUTPUT = "scraper_results.json"
# CSV_OUTPUT = "scraper_results.csv"
# XLSX_OUTPUT = "scraper_results.xlsx"

# PUBMED_API_KEY = "c2f307fc5acc4197325e5d9234ff271aa608"  # optional
# CROSSREF_EMAIL = CONTACT_EMAIL
# PUBMED_RATE_LIMIT = 0.34  # seconds between PubMed requests (~3 req/s)

# logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# log = logging.getLogger("generalized_scraper")

# # ---------------- UTIL ----------------
# def clean_text(t):
#     return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", (t or ""))).strip()

# def normalize_title(t):
#     txt = re.sub(r"[^a-z0-9]+", " ", (t or "").lower())
#     return re.sub(r"\s+", " ", txt).strip()

# def title_hash(title):
#     nh = normalize_title(title)
#     return hashlib.sha1(nh.encode("utf-8")).hexdigest()

# # ---------------- PICO ----------------
# PICO_KEYWORDS = {
#     "interventions": ["dexrazoxane", "beta-blocker", "ace inhibitor", "arb", "acei", "arni", "statin"],
#     "exposures": ["anthracycline", "doxorubicin", "epirubicin", "trastuzumab"],
#     "comparators": ["placebo", "usual care", "control"],
#     "study_designs": ["randomized", "rct", "cohort", "observational"]
# }
# ALL_PICO = {w for l in PICO_KEYWORDS.values() for w in l}
# PICO_PATTERN = re.compile("(" + "|".join(map(re.escape, ALL_PICO)) + ")", re.I)

# # ---------------- ZOTERO HEADER ----------------
# ZOTERO_HEADER = [
#     "Key", "Item Type", "Publication Year", "Author", "Title", "Publication Title", "ISBN", "ISSN", "DOI", "Url",
#     "Abstract Note", "Date", "Date Added", "Date Modified", "Access Date", "Pages", "Num Pages", "Issue", "Volume",
#     "Number Of Volumes", "Journal Abbreviation", "Short Title", "Series", "Series Number", "Series Text", "Series Title",
#     "Publisher", "Place", "Language", "Rights", "Type", "Archive", "Archive Location", "Library Catalog", "Call Number",
#     "Extra", "Meeting Name", "Conference Name", "Country"
# ]

# def zotero_template():
#     return {k: "" for k in ZOTERO_HEADER}

# # ---------------- STORAGE (sqlite with merge support) ----------------
# class Storage:
#     def __init__(self, path=DB_PATH):
#         self.conn = sqlite3.connect(path)
#         self.create()

#     def create(self):
#         # identifier is the canonical key (DOI preferred), store doi, pmid, title_hash separately for lookups/merges
#         self.conn.execute("""
#             CREATE TABLE IF NOT EXISTS recs(
#                 id INTEGER PRIMARY KEY,
#                 identifier TEXT UNIQUE,
#                 doi TEXT,
#                 pmid TEXT,
#                 title_hash TEXT,
#                 data TEXT
#             )
#         """)
#         self.conn.execute("CREATE INDEX IF NOT EXISTS idx_doi ON recs(doi)")
#         self.conn.execute("CREATE INDEX IF NOT EXISTS idx_pmid ON recs(pmid)")
#         self.conn.execute("CREATE INDEX IF NOT EXISTS idx_titlehash ON recs(title_hash)")
#         self.conn.commit()

#     def find_existing(self, doi=None, pmid=None, thash=None):
#         cur = self.conn.cursor()
#         # priority: doi -> pmid -> title_hash
#         if doi:
#             cur.execute("SELECT id, identifier, data FROM recs WHERE doi = ? LIMIT 1", (doi,))
#             r = cur.fetchone()
#             if r: return r
#         if pmid:
#             cur.execute("SELECT id, identifier, data FROM recs WHERE pmid = ? LIMIT 1", (pmid,))
#             r = cur.fetchone()
#             if r: return r
#         if thash:
#             cur.execute("SELECT id, identifier, data FROM recs WHERE title_hash = ? LIMIT 1", (thash,))
#             r = cur.fetchone()
#             if r: return r
#         return None

#     def upsert(self, rec):
#         """
#         rec: dict containing metadata. Expected to include (if available):
#             - 'DOI' (string), 'PMID' (string), 'Title' (string)
#         Behavior:
#             - Find existing by DOI/PMID/title_hash
#             - If found: merge (prefer new non-empty fields), update doi/pmid/title_hash/identifier if needed
#             - If not found: insert new row; choose identifier = DOI or PMID or title_hash
#         """
#         doi = (rec.get("DOI") or "").lower() or None
#         pmid = (rec.get("Key") or rec.get("PMID") or "").strip() or None  # PubMed used "Key" as pmid earlier
#         thash = title_hash(rec.get("Title", "")) if rec.get("Title") else None

#         existing = self.find_existing(doi=doi, pmid=pmid, thash=thash)
#         if existing:
#             eid, identifier, data_json = existing
#             existing_data = json.loads(data_json)
#             # merge: prefer non-empty new fields; combine Authors, Extra, etc.
#             merged = existing_data.copy()
#             for k, v in rec.items():
#                 if not v:  # skip empty
#                     continue
#                 if k in ("Author",) and merged.get(k):
#                     # merge unique authors semicolon-separated
#                     existing_authors = {a.strip() for a in merged.get(k, "").split(";") if a.strip()}
#                     new_authors = {a.strip() for a in v.split(";") if a.strip()}
#                     merged[k] = "; ".join(sorted(existing_authors.union(new_authors)))
#                 elif k == "Extra" and merged.get(k):
#                     merged[k] = merged[k] + " | " + v
#                 else:
#                     merged[k] = v
#             # Decide new canonical identifier: prefer doi, then pmid, else keep existing
#             new_identifier = identifier
#             if doi:
#                 new_identifier = doi
#             elif pmid:
#                 new_identifier = pmid
#             # update doi/pmid/thash
#             sql = "UPDATE recs SET identifier=?, doi=?, pmid=?, title_hash=?, data=? WHERE id=?"
#             self.conn.execute(sql, (new_identifier, doi, pmid, thash, json.dumps(merged, ensure_ascii=False), eid))
#             self.conn.commit()
#             return new_identifier
#         else:
#             # insert new
#             identifier = doi or pmid or thash
#             self.conn.execute(
#                 "INSERT INTO recs(identifier, doi, pmid, title_hash, data) VALUES(?,?,?,?,?)",
#                 (identifier, doi, pmid, thash, json.dumps(rec, ensure_ascii=False))
#             )
#             self.conn.commit()
#             return identifier

#     def all(self):
#         cur = self.conn.cursor()
#         cur.execute("SELECT data FROM recs")
#         return [json.loads(r[0]) for r in cur.fetchall()]

#     def close(self):
#         self.conn.close()

# # ---------------- FETCHER ----------------
# class Fetcher:
#     def __init__(self, user_agent=USER_AGENT):
#         self.s = requests.Session()
#         self.s.headers.update({"User-Agent": user_agent})

#     def get(self, url, params=None, timeout=30):
#         r = self.s.get(url, params=params, timeout=timeout)
#         r.raise_for_status()
#         return r.text

# # ---------------- BaseScraper (pluggable) ----------------
# class BaseScraper:
#     def __init__(self, fetcher: Fetcher, store: Storage, pico_pattern=PICO_PATTERN):
#         self.fetcher = fetcher
#         self.store = store
#         self.pico_pattern = pico_pattern

#     def filter_pico(self, title, abstract):
#         if not self.pico_pattern:
#             return True
#         text = (title or "") + " " + (abstract or "")
#         return bool(self.pico_pattern.search(text))

#     def save(self, rec):
#         # ensure minimal fields
#         rec.setdefault("Item Type", "journalArticle")
#         rec.setdefault("Date", "")
#         rec.setdefault("Publication Year", "")
#         self.store.upsert(rec)

# # ---------------- PubMed Scraper ----------------
# class PubMedScraper(BaseScraper):
#     def __init__(self, fetcher, store, api_key="", rate_limit=PUBMED_RATE_LIMIT):
#         super().__init__(fetcher, store)
#         self.api_key = api_key
#         self.rate_limit = rate_limit

#     def parse_pub_date(self, art):
#         pub_date_el = art.find(".//PubDate")
#         year, month, day = "", "01", "01"
#         if pub_date_el is not None:
#             y = pub_date_el.findtext("Year")
#             m = pub_date_el.findtext("Month")
#             d = pub_date_el.findtext("Day")
#             medline = pub_date_el.findtext("MedlineDate")
#             if y:
#                 year = y
#             elif medline:
#                 m_year = re.search(r"\d{4}", medline)
#                 if m_year:
#                     year = m_year.group(0)
#             if m:
#                 months = {"jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
#                           "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12"}
#                 mn = months.get(m[:3].lower(), "01")
#                 month = mn
#             if d:
#                 day = d.zfill(2)
#         if not year:
#             year = "Unknown"
#         return year, f"{year}-{month}-{day}"

#     def scrape(self, query, limit=100, from_year=None, to_year=None):
#         search = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#         fetch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
#         params = {
#             "db": "pubmed",
#             "term": query,
#             "retmode": "json",
#             "datetype": "pdat",
#             "retmax": 100,
#             "mindate": f"{from_year}/01/01" if from_year else None,
#             "maxdate": f"{to_year}/12/31" if to_year else None,
#             "api_key": self.api_key or None
#         }
#         retstart = 0
#         ids = []
#         while True:
#             params["retstart"] = retstart
#             j = json.loads(self.fetcher.get(search, params=params))
#             idlist = j.get("esearchresult", {}).get("idlist", [])
#             if not idlist:
#                 break
#             ids.extend(idlist)
#             retstart += len(idlist)
#             if limit and len(ids) >= limit:
#                 ids = ids[:limit]
#                 break
#             if len(idlist) < params["retmax"]:
#                 break
#             time.sleep(self.rate_limit)

#         if not ids:
#             log.info("PubMed: no ids found for query.")
#             return

#         chunk = 200
#         for i in range(0, len(ids), chunk):
#             sub = ids[i:i + chunk]
#             params2 = {"db": "pubmed", "id": ",".join(sub), "retmode": "xml", "api_key": self.api_key or None}
#             xml = self.fetcher.get(fetch, params=params2)
#             root = ET.fromstring(xml)
#             for art in root.findall(".//PubmedArticle"):
#                 pmid = art.findtext(".//PMID", "").strip()
#                 title = art.findtext(".//ArticleTitle", "") or ""
#                 abst = " ".join([el.text or "" for el in art.findall(".//Abstract/AbstractText")])
#                 if not self.filter_pico(title, abst):
#                     continue
#                 authors = []
#                 for a in art.findall(".//Author"):
#                     last = a.findtext("LastName", "")
#                     given = a.findtext("ForeName", "")
#                     if last:
#                         authors.append(f"{last}, {given}")
#                 doi = ""
#                 for aid in art.findall(".//ArticleId"):
#                     if aid.get("IdType") == "doi":
#                         doi = (aid.text or "").lower()
#                 pub_year, pub_date = self.parse_pub_date(art)
#                 rec = {
#                     "Key": pmid,
#                     "PMID": pmid,
#                     "Item Type": "journalArticle",
#                     "Title": clean_text(title),
#                     "Abstract Note": clean_text(abst),
#                     "Author": "; ".join(authors),
#                     "Publication Title": art.findtext(".//Journal/Title", ""),
#                     "Journal Abbreviation": art.findtext(".//Journal/ISOAbbreviation", ""),
#                     "ISSN": art.findtext(".//Journal/ISSN", ""),
#                     "Volume": art.findtext(".//JournalIssue/Volume", ""),
#                     "Issue": art.findtext(".//JournalIssue/Issue", ""),
#                     "Pages": art.findtext(".//Pagination/MedlinePgn", ""),
#                     "Publication Year": pub_year,
#                     "Date": pub_date,
#                     "Language": art.findtext(".//Language", ""),
#                     "DOI": doi,
#                     "Url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
#                     "Country": art.findtext(".//MedlineJournalInfo/Country", ""),
#                     "Type": "; ".join([pt.text for pt in art.findall(".//PublicationType") if pt.text]),
#                     "Extra": "source:PubMed"
#                 }
#                 # prefer saving DOI as DOI field; upsert merges by DOI/PMID/title_hash
#                 self.save(rec)
#             time.sleep(self.rate_limit)

# # ---------------- CrossRef Scraper ----------------
# class CrossRefScraper(BaseScraper):
#     def __init__(self, fetcher, store, email=CROSSREF_EMAIL):
#         super().__init__(fetcher, store)
#         self.email = email

#     def parse_crossref_date(self, item):
#         # returns (year, YYYY-MM-DD or YYYY-MM or YYYY)
#         dp = item.get("issued", {}).get("date-parts", [])
#         if dp and dp[0]:
#             parts = dp[0]
#             year = str(parts[0])
#             month = str(parts[1]).zfill(2) if len(parts) > 1 else None
#             day = str(parts[2]).zfill(2) if len(parts) > 2 else None
#             if year and month and day:
#                 return year, f"{year}-{month}-{day}"
#             if year and month:
#                 return year, f"{year}-{month}-01"
#             return year, year
#         return "", ""

#     def scrape(self, query, limit=100, from_year=None, to_year=None):
#         url = "https://api.crossref.org/works"
#         batch = 1000
#         fetched = 0
#         while fetched < limit:
#             rows = min(batch, limit - fetched)
#             filt = []
#             if from_year:
#                 filt.append(f"from-pub-date:{from_year}-01-01")
#             if to_year:
#                 filt.append(f"until-pub-date:{to_year}-12-31")
#             params = {"query": query, "rows": rows, "offset": fetched, "mailto": self.email}
#             if filt:
#                 params["filter"] = ",".join(filt)
#             j = json.loads(self.fetcher.get(url, params=params))
#             items = j.get("message", {}).get("items", [])
#             if not items:
#                 break
#             for it in items:
#                 title = (it.get("title") or [""])[0]
#                 abst = clean_text(it.get("abstract", ""))
#                 if not self.filter_pico(title, abst):
#                     continue
#                 authors = [f"{a.get('family','')}, {a.get('given','')}" for a in it.get("author", [])] if it.get("author") else []
#                 doi = (it.get("DOI") or "").lower()
#                 year, date = self.parse_crossref_date(it)
#                 rec = {
#                     "Key": doi or title_hash(title),
#                     "Item Type": it.get("type", "journal-article"),
#                     "Title": clean_text(title),
#                     "Abstract Note": abst,
#                     "Author": "; ".join(authors),
#                     "Publication Title": (it.get("container-title") or [""])[0],
#                     "Journal Abbreviation": (it.get("short-container-title") or [""])[0] if it.get("short-container-title") else "",
#                     "ISSN": "; ".join(it.get("ISSN", [])) if it.get("ISSN") else "",
#                     "Volume": it.get("volume", ""),
#                     "Issue": it.get("issue", ""),
#                     "Pages": it.get("page", ""),
#                     "Publication Year": year,
#                     "Date": date,
#                     "Publisher": it.get("publisher", ""),
#                     "Language": it.get("language", ""),
#                     "DOI": doi,
#                     "Url": it.get("URL", ""),
#                     "Extra": "source:CrossRef"
#                 }
#                 self.save(rec)
#             fetched += len(items)
#             if len(items) < rows:
#                 break

# # ---------------- Scraper Manager (register scrapers) ----------------
# class ScraperManager:
#     def __init__(self, store, fetcher):
#         self.store = store
#         self.fetcher = fetcher
#         self.scrapers = {}

#     def register(self, name, scraper):
#         self.scrapers[name.lower()] = scraper

#     def run(self, sources, query, limit, from_year, to_year):
#         # sources: list of names (lowercase) in order to run
#         for s in sources:
#             name = s.lower()
#             if name not in self.scrapers:
#                 log.warning("No scraper registered for %s - skipping", s)
#                 continue
#             log.info("Running scraper: %s", s)
#             scraper = self.scrapers[name]
#             try:
#                 scraper.scrape(query=query, limit=limit, from_year=from_year, to_year=to_year)
#             except TypeError:
#                 # allow older signature without named parameters
#                 scraper.scrape(query, limit, from_year, to_year)

# # ---------------- EXPORT ----------------
# def export_all(recs):
#     df = pd.DataFrame([{**zotero_template(), **r} for r in recs], columns=ZOTERO_HEADER)
#     df.to_csv(CSV_OUTPUT, index=False, encoding="utf-8")
#     df.to_excel(XLSX_OUTPUT, index=False, engine="openpyxl")
#     with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
#         json.dump(recs, f, ensure_ascii=False, indent=2)
#     log.info("Exported %d records", len(recs))

# # ---------------- CLI / Run ----------------
# def main():
#     p = argparse.ArgumentParser()
#     p.add_argument("--query", required=True)
#     p.add_argument("--sources", default="pubmed,crossref", help="comma-separated: pubmed,crossref,custom")
#     p.add_argument("--limit", type=int, default=200)
#     p.add_argument("--from_year", type=int)
#     p.add_argument("--to_year", type=int)
#     p.add_argument("--years", type=int)
#     a = p.parse_args()

#     fy, ty = a.from_year, a.to_year
#     if a.years:
#         ty = datetime.now().year
#         fy = ty - a.years + 1

#     store = Storage()
#     fetcher = Fetcher()
#     manager = ScraperManager(store, fetcher)

#     # register built-in scrapers
#     manager.register("pubmed", PubMedScraper(fetcher, store, api_key=PUBMED_API_KEY, rate_limit=PUBMED_RATE_LIMIT))
#     manager.register("crossref", CrossRefScraper(fetcher, store, email=CROSSREF_EMAIL))

#     sources = [s.strip().lower() for s in a.sources.split(",") if s.strip()]
#     manager.run(sources, a.query, a.limit, fy, ty)

#     recs = store.all()
#     export_all(recs)
#     store.close()

# if __name__ == "__main__":
#     main()



#!/usr/bin/env python3
# """
# generalized_scraper_crawl4ai.py

# Unified, pluggable scraper framework with optional crawl4ai support.

# Usage examples:
#   # default (requests)
#   python generalized_scraper_crawl4ai.py --query "doxorubicin AND dexrazoxane" --from_year 2010 --to_year 2023 --limit 500

#   # force crawl4ai (requires crawl4ai to be installed & configured)
#   python generalized_scraper_crawl4ai.py --query "trastuzumab" --sources pubmed,crossref --use_crawl4ai
# """
# import argparse
# import json
# import logging
# import re
# import sqlite3
# import time
# import hashlib
# import xml.etree.ElementTree as ET
# from datetime import datetime

# import pandas as pd
# import requests

# # try to import crawl4ai if available
# USE_CRAWL4AI_BY_DEFAULT = False
# try:
#     from crawl4ai import WebCrawler  # if installed
#     CRAWL4AI_AVAILABLE = True
# except Exception:
#     WebCrawler = None
#     CRAWL4AI_AVAILABLE = False

# # ---------------- CONFIG ----------------
# CONTACT_EMAIL = "keertisubramanyasm@gmail.com"
# USER_AGENT = f"GeneralizedScraper/1.0 (+{CONTACT_EMAIL})"
# DB_PATH = "scraper_results.db"
# JSON_OUTPUT = "scraper_results.json"
# CSV_OUTPUT = "scraper_results.csv"
# XLSX_OUTPUT = "scraper_results.xlsx"

# PUBMED_API_KEY = "c2f307fc5acc4197325e5d9234ff271aa608"      # Optional: place your PubMed API key here
# CROSSREF_EMAIL = CONTACT_EMAIL
# PUBMED_RATE_LIMIT = 0.34  # seconds between PubMed requests (~3 req/s)

# logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# log = logging.getLogger("generalized_scraper")

# # ---------------- UTIL ----------------
# def clean_text(t):
#     return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", (t or ""))).strip()

# def normalize_title(t):
#     txt = re.sub(r"[^a-z0-9]+", " ", (t or "").lower())
#     return re.sub(r"\s+", " ", txt).strip()

# def title_hash(title):
#     nh = normalize_title(title or "")
#     return hashlib.sha1(nh.encode("utf-8")).hexdigest()

# # ---------------- PICO ----------------
# PICO_KEYWORDS = {
#     "interventions": ["dexrazoxane", "beta-blocker", "ace inhibitor", "arb", "acei", "arni", "statin"],
#     "exposures": ["anthracycline", "doxorubicin", "epirubicin", "trastuzumab"],
#     "comparators": ["placebo", "usual care", "control"],
#     "study_designs": ["randomized", "rct", "cohort", "observational"]
# }
# ALL_PICO = {w for l in PICO_KEYWORDS.values() for w in l}
# PICO_PATTERN = re.compile("(" + "|".join(map(re.escape, ALL_PICO)) + ")", re.I)

# # ---------------- ZOTERO HEADER ----------------
# ZOTERO_HEADER = [
#     "Key", "Item Type", "Publication Year", "Author", "Title", "Publication Title", "ISBN", "ISSN", "DOI", "Url",
#     "Abstract Note", "Date", "Date Added", "Date Modified", "Access Date", "Pages", "Num Pages", "Issue", "Volume",
#     "Number Of Volumes", "Journal Abbreviation", "Short Title", "Series", "Series Number", "Series Text", "Series Title",
#     "Publisher", "Place", "Language", "Rights", "Type", "Archive", "Archive Location", "Library Catalog", "Call Number",
#     "Extra", "Meeting Name", "Conference Name", "Country"
# ]

# def zotero_template():
#     return {k: "" for k in ZOTERO_HEADER}

# # ---------------- STORAGE ----------------
# class Storage:
#     def __init__(self, path=DB_PATH):
#         self.conn = sqlite3.connect(path)
#         self.create()

#     def create(self):
#         self.conn.execute("""
#             CREATE TABLE IF NOT EXISTS recs(
#                 id INTEGER PRIMARY KEY,
#                 identifier TEXT UNIQUE,
#                 doi TEXT,
#                 pmid TEXT,
#                 title_hash TEXT,
#                 data TEXT
#             )
#         """)
#         self.conn.execute("CREATE INDEX IF NOT EXISTS idx_doi ON recs(doi)")
#         self.conn.execute("CREATE INDEX IF NOT EXISTS idx_pmid ON recs(pmid)")
#         self.conn.execute("CREATE INDEX IF NOT EXISTS idx_titlehash ON recs(title_hash)")
#         self.conn.commit()

#     def find_existing(self, doi=None, pmid=None, thash=None):
#         cur = self.conn.cursor()
#         if doi:
#             cur.execute("SELECT id, identifier, data FROM recs WHERE doi = ? LIMIT 1", (doi,))
#             r = cur.fetchone()
#             if r:
#                 return r
#         if pmid:
#             cur.execute("SELECT id, identifier, data FROM recs WHERE pmid = ? LIMIT 1", (pmid,))
#             r = cur.fetchone()
#             if r:
#                 return r
#         if thash:
#             cur.execute("SELECT id, identifier, data FROM recs WHERE title_hash = ? LIMIT 1", (thash,))
#             r = cur.fetchone()
#             if r:
#                 return r
#         return None

#     def upsert(self, rec):
#         doi = (rec.get("DOI") or "").lower() or None
#         pmid = (rec.get("Key") or rec.get("PMID") or "").strip() or None
#         thash = title_hash(rec.get("Title", "")) if rec.get("Title") else None

#         existing = self.find_existing(doi=doi, pmid=pmid, thash=thash)
#         if existing:
#             eid, identifier, data_json = existing
#             existing_data = json.loads(data_json)
#             merged = existing_data.copy()
#             for k, v in rec.items():
#                 if not v:
#                     continue
#                 if k == "Author" and merged.get(k):
#                     existing_authors = {a.strip() for a in merged.get(k, "").split(";") if a.strip()}
#                     new_authors = {a.strip() for a in v.split(";") if a.strip()}
#                     merged[k] = "; ".join(sorted(existing_authors.union(new_authors)))
#                 elif k == "Extra" and merged.get(k):
#                     merged[k] = merged[k] + " | " + v
#                 else:
#                     merged[k] = v
#             new_identifier = identifier
#             if doi:
#                 new_identifier = doi
#             elif pmid:
#                 new_identifier = pmid
#             sql = "UPDATE recs SET identifier=?, doi=?, pmid=?, title_hash=?, data=? WHERE id=?"
#             self.conn.execute(sql, (new_identifier, doi, pmid, thash, json.dumps(merged, ensure_ascii=False), eid))
#             self.conn.commit()
#             return new_identifier
#         else:
#             identifier = doi or pmid or thash
#             self.conn.execute(
#                 "INSERT INTO recs(identifier, doi, pmid, title_hash, data) VALUES(?,?,?,?,?)",
#                 (identifier, doi, pmid, thash, json.dumps(rec, ensure_ascii=False))
#             )
#             self.conn.commit()
#             return identifier

#     def all(self):
#         cur = self.conn.cursor()
#         cur.execute("SELECT data FROM recs")
#         return [json.loads(r[0]) for r in cur.fetchall()]

#     def close(self):
#         self.conn.close()

# # ---------------- FETCHER (requests or crawl4ai) ----------------
# class Fetcher:
#     def __init__(self, use_crawl4ai=False):
#         self.use_crawl4ai = use_crawl4ai and CRAWL4AI_AVAILABLE
#         self.s = requests.Session()
#         self.s.headers.update({"User-Agent": USER_AGENT})
#         self.c = None
#         if self.use_crawl4ai:
#             # Create a WebCrawler instance (this may require configuration / keys from crawl4ai)
#             try:
#                 self.c = WebCrawler()
#                 log.info("Using crawl4ai WebCrawler for requests")
#             except Exception as e:
#                 log.error("crawl4ai requested but failed to initialize: %s. Falling back to requests.", e)
#                 self.c = None
#                 self.use_crawl4ai = False

#     def get(self, url, params=None, timeout=30):
#         if self.use_crawl4ai and self.c:
#             # WebCrawler.get might return an object with .text (depends on library)
#             try:
#                 r = self.c.get(url, params=params)
#                 # Some WebCrawler implementations return response-like; attempt r.text first
#                 return getattr(r, "text", str(r))
#             except Exception as e:
#                 log.warning("crawl4ai fetch failed (%s) — falling back to requests", e)
#         # fallback to requests
#         r = self.s.get(url, params=params, timeout=timeout)
#         r.raise_for_status()
#         return r.text

# # ---------------- BaseScraper ----------------
# class BaseScraper:
#     def __init__(self, fetcher: Fetcher, store: Storage, pico_pattern=PICO_PATTERN):
#         self.fetcher = fetcher
#         self.store = store
#         self.pico_pattern = pico_pattern

#     def filter_pico(self, title, abstract):
#         if not self.pico_pattern:
#             return True
#         text = (title or "") + " " + (abstract or "")
#         return bool(self.pico_pattern.search(text))

#     def save(self, rec):
#         rec.setdefault("Item Type", "journalArticle")
#         rec.setdefault("Date", "")
#         rec.setdefault("Publication Year", "")
#         self.store.upsert(rec)

# # ---------------- PubMedScraper ----------------
# class PubMedScraper(BaseScraper):
#     def __init__(self, fetcher, store, api_key="", rate_limit=PUBMED_RATE_LIMIT):
#         super().__init__(fetcher, store)
#         self.api_key = api_key
#         self.rate_limit = rate_limit

#     def parse_pub_date(self, art):
#         pub_date_el = art.find(".//PubDate")
#         year, month, day = "", "01", "01"
#         if pub_date_el is not None:
#             y = pub_date_el.findtext("Year")
#             m = pub_date_el.findtext("Month")
#             d = pub_date_el.findtext("Day")
#             medline = pub_date_el.findtext("MedlineDate")
#             if y:
#                 year = y
#             elif medline:
#                 m_year = re.search(r"\d{4}", medline)
#                 if m_year:
#                     year = m_year.group(0)
#             if m:
#                 months = {"jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
#                           "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12"}
#                 mn = months.get(m[:3].lower(), "01")
#                 month = mn
#             if d:
#                 day = d.zfill(2)
#         if not year:
#             year = "Unknown"
#         return year, f"{year}-{month}-{day}"

#     def scrape(self, query, limit=100, from_year=None, to_year=None):
#         search = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#         fetch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
#         params = {
#             "db": "pubmed",
#             "term": query,
#             "retmode": "json",
#             "datetype": "pdat",
#             "retmax": 100,
#             "mindate": f"{from_year}/01/01" if from_year else None,
#             "maxdate": f"{to_year}/12/31" if to_year else None,
#             "api_key": self.api_key or None
#         }
#         retstart = 0
#         ids = []
#         while True:
#             params["retstart"] = retstart
#             j = json.loads(self.fetcher.get(search, params=params))
#             idlist = j.get("esearchresult", {}).get("idlist", [])
#             if not idlist:
#                 break
#             ids.extend(idlist)
#             retstart += len(idlist)
#             if limit and len(ids) >= limit:
#                 ids = ids[:limit]
#                 break
#             if len(idlist) < params["retmax"]:
#                 break
#             time.sleep(self.rate_limit)

#         if not ids:
#             log.info("PubMed: no ids found for query.")
#             return

#         chunk = 200
#         for i in range(0, len(ids), chunk):
#             sub = ids[i:i + chunk]
#             params2 = {"db": "pubmed", "id": ",".join(sub), "retmode": "xml", "api_key": self.api_key or None}
#             xml = self.fetcher.get(fetch, params=params2)
#             root = ET.fromstring(xml)
#             for art in root.findall(".//PubmedArticle"):
#                 pmid = art.findtext(".//PMID", "").strip()
#                 title = art.findtext(".//ArticleTitle", "") or ""
#                 abst = " ".join([el.text or "" for el in art.findall(".//Abstract/AbstractText")])
#                 if not self.filter_pico(title, abst):
#                     continue
#                 authors = []
#                 for a in art.findall(".//Author"):
#                     last = a.findtext("LastName", "")
#                     given = a.findtext("ForeName", "")
#                     if last:
#                         authors.append(f"{last}, {given}")
#                 doi = ""
#                 for aid in art.findall(".//ArticleId"):
#                     if aid.get("IdType") == "doi":
#                         doi = (aid.text or "").lower()
#                 pub_year, pub_date = self.parse_pub_date(art)
#                 rec = {
#                     "Key": pmid,
#                     "PMID": pmid,
#                     "Item Type": "journalArticle",
#                     "Title": clean_text(title),
#                     "Abstract Note": clean_text(abst),
#                     "Author": "; ".join(authors),
#                     "Publication Title": art.findtext(".//Journal/Title", ""),
#                     "Journal Abbreviation": art.findtext(".//Journal/ISOAbbreviation", ""),
#                     "ISSN": art.findtext(".//Journal/ISSN", ""),
#                     "Volume": art.findtext(".//JournalIssue/Volume", ""),
#                     "Issue": art.findtext(".//JournalIssue/Issue", ""),
#                     "Pages": art.findtext(".//Pagination/MedlinePgn", ""),
#                     "Publication Year": pub_year,
#                     "Date": pub_date,
#                     "Language": art.findtext(".//Language", ""),
#                     "DOI": doi,
#                     "Url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
#                     "Country": art.findtext(".//MedlineJournalInfo/Country", ""),
#                     "Type": "; ".join([pt.text for pt in art.findall(".//PublicationType") if pt.text]),
#                     "Extra": "source:PubMed"
#                 }
#                 self.save(rec)
#             time.sleep(self.rate_limit)

# # ---------------- CrossRefScraper ----------------
# class CrossRefScraper(BaseScraper):
#     def __init__(self, fetcher, store, email=CROSSREF_EMAIL):
#         super().__init__(fetcher, store)
#         self.email = email

#     def parse_crossref_date(self, item):
#         dp = item.get("issued", {}).get("date-parts", [])
#         if dp and dp[0]:
#             parts = dp[0]
#             year = str(parts[0])
#             month = str(parts[1]).zfill(2) if len(parts) > 1 else None
#             day = str(parts[2]).zfill(2) if len(parts) > 2 else None
#             if year and month and day:
#                 return year, f"{year}-{month}-{day}"
#             if year and month:
#                 return year, f"{year}-{month}-01"
#             return year, year
#         return "", ""

#     def scrape(self, query, limit=100, from_year=None, to_year=None):
#         url = "https://api.crossref.org/works"
#         batch = 1000
#         fetched = 0
#         while fetched < limit:
#             rows = min(batch, limit - fetched)
#             filt = []
#             if from_year:
#                 filt.append(f"from-pub-date:{from_year}-01-01")
#             if to_year:
#                 filt.append(f"until-pub-date:{to_year}-12-31")
#             params = {"query": query, "rows": rows, "offset": fetched, "mailto": self.email}
#             if filt:
#                 params["filter"] = ",".join(filt)
#             j = json.loads(self.fetcher.get(url, params=params))
#             items = j.get("message", {}).get("items", [])
#             if not items:
#                 break
#             for it in items:
#                 title = (it.get("title") or [""])[0]
#                 abst = clean_text(it.get("abstract", ""))
#                 if not self.filter_pico(title, abst):
#                     continue
#                 authors = [f"{a.get('family','')}, {a.get('given','')}" for a in it.get("author", [])] if it.get("author") else []
#                 doi = (it.get("DOI") or "").lower()
#                 year, date = self.parse_crossref_date(it)
#                 rec = {
#                     "Key": doi or title_hash(title),
#                     "Item Type": it.get("type", "journal-article"),
#                     "Title": clean_text(title),
#                     "Abstract Note": abst,
#                     "Author": "; ".join(authors),
#                     "Publication Title": (it.get("container-title") or [""])[0],
#                     "Journal Abbreviation": (it.get("short-container-title") or [""])[0] if it.get("short-container-title") else "",
#                     "ISSN": "; ".join(it.get("ISSN", [])) if it.get("ISSN") else "",
#                     "Volume": it.get("volume", ""),
#                     "Issue": it.get("issue", ""),
#                     "Pages": it.get("page", ""),
#                     "Publication Year": year,
#                     "Date": date,
#                     "Publisher": it.get("publisher", ""),
#                     "Language": it.get("language", ""),
#                     "DOI": doi,
#                     "Url": it.get("URL", ""),
#                     "Extra": "source:CrossRef"
#                 }
#                 self.save(rec)
#             fetched += len(items)
#             if len(items) < rows:
#                 break

# # ---------------- MANAGER ----------------
# class ScraperManager:
#     def __init__(self, store, fetcher):
#         self.store = store
#         self.fetcher = fetcher
#         self.scrapers = {}

#     def register(self, name, scraper):
#         self.scrapers[name.lower()] = scraper

#     def run(self, sources, query, limit, from_year, to_year):
#         for s in sources:
#             name = s.lower()
#             if name not in self.scrapers:
#                 log.warning("No scraper registered for %s - skipping", s)
#                 continue
#             log.info("Running scraper: %s", s)
#             scraper = self.scrapers[name]
#             try:
#                 scraper.scrape(query=query, limit=limit, from_year=from_year, to_year=to_year)
#             except TypeError:
#                 scraper.scrape(query, limit, from_year, to_year)

# # ---------------- EXPORT ----------------
# def export_all(recs):
#     df = pd.DataFrame([{**zotero_template(), **r} for r in recs], columns=ZOTERO_HEADER)
#     df.to_csv(CSV_OUTPUT, index=False, encoding="utf-8")
#     df.to_excel(XLSX_OUTPUT, index=False, engine="openpyxl")
#     with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
#         json.dump(recs, f, ensure_ascii=False, indent=2)
#     log.info("Exported %d records", len(recs))

# # ---------------- CLI ----------------
# def main():
#     p = argparse.ArgumentParser()
#     p.add_argument("--query", required=True)
#     p.add_argument("--sources", default="pubmed,crossref")
#     p.add_argument("--limit", type=int, default=200)
#     p.add_argument("--from_year", type=int)
#     p.add_argument("--to_year", type=int)
#     p.add_argument("--years", type=int)
#     p.add_argument("--use_crawl4ai", action="store_true", help="Use crawl4ai WebCrawler if available")
#     a = p.parse_args()

#     fy, ty = a.from_year, a.to_year
#     if a.years:
#         ty = datetime.now().year
#         fy = ty - a.years + 1

#     fetcher = Fetcher(use_crawl4ai=a.use_crawl4ai or USE_CRAWL4AI_BY_DEFAULT)
#     store = Storage()
#     manager = ScraperManager(store, fetcher)

#     manager.register("pubmed", PubMedScraper(fetcher, store, api_key=PUBMED_API_KEY, rate_limit=PUBMED_RATE_LIMIT))
#     manager.register("crossref", CrossRefScraper(fetcher, store, email=CROSSREF_EMAIL))

#     sources = [s.strip() for s in a.sources.split(",") if s.strip()]
#     manager.run(sources, a.query, a.limit, fy, ty)

#     recs = store.all()
#     export_all(recs)
#     store.close()

# if __name__ == "__main__":
#     main()



# #!/usr/bin/env python3
# """
# The full scraper code here doesn't use crawl4ai at all — it uses only requests + xml.etree for PubMed, and requests + JSON parsing for CrossRef.
# Meaning: if you have crawl4ai installed, it will automatically use it for fetching pages.
# But: Right now, you are still just using PubMed API and CrossRef API. crawl4ai is only being used as a "replacement HTTP client" instead of requests — not for scraping new sites yet.
# multi_source_scraper.py

# - Unified Scraper: PubMed + CrossRef (extendable to arXiv, EuropePMC, etc.)
# - Deduplicates by DOI > PMID > normalized Title
# - PICO keyword filtering
# - Zotero-style metadata
# - Exports JSON, CSV, XLSX
# - Merge reporting (--merge-report)
# """

# import argparse, json, re, sqlite3, logging, time
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
# MERGE_REPORT_FILE = "merge_report.txt"

# PUBMED_API_KEY = "c2f307fc5acc4197325e5d9234ff271aa608"  
# CROSSREF_EMAIL = CONTACT_EMAIL
# PUBMED_RATE_LIMIT = 0.34  

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
# ZOTERO_HEADER=[ "Key","Item Type","Publication Year","Author","Title","Publication Title","ISBN","ISSN","DOI","Url",
# "Abstract Note","Date","Date Added","Date Modified","Access Date","Pages","Num Pages","Issue","Volume",
# "Number Of Volumes","Journal Abbreviation","Short Title","Series","Series Number","Series Text","Series Title",
# "Publisher","Place","Language","Rights","Type","Archive","Archive Location","Library Catalog","Call Number",
# "Extra","Meeting Name","Conference Name","Country" ]

# def zotero_template(): return {k:"" for k in ZOTERO_HEADER}

# # ---------------- Storage ----------------
# class Storage:
#     def __init__(self,path=DB_PATH): 
#         self.conn=sqlite3.connect(path)
#         self.create()
#     def create(self):
#         self.conn.execute("CREATE TABLE IF NOT EXISTS recs(id INTEGER PRIMARY KEY, identifier TEXT UNIQUE, data TEXT)")
#         self.conn.commit()
#     def insert(self,ident,data):
#         try:
#             self.conn.execute("INSERT INTO recs(identifier,data) VALUES(?,?)",(ident,json.dumps(data)))
#             self.conn.commit()
#             return True
#         except sqlite3.IntegrityError:
#             return False
#     def all(self):
#         cur=self.conn.cursor();cur.execute("SELECT data FROM recs")
#         return [json.loads(r[0]) for r in cur.fetchall()]
#     def close(self): self.conn.close()

# # ---------------- Fetcher ----------------
# class Fetcher:
#     def __init__(self):
#         self.s=requests.Session()
#         self.s.headers.update({"User-Agent":USER_AGENT})
#         self.c=None
#         if USE_CRAWL4AI:
#             try: self.c=WebCrawler();log.info("crawl4ai available")
#             except: self.c=None
#     def get(self,url,params=None):
#         if self.c:
#             try: return self.c.get(url,params=params).text
#             except: pass
#         r=self.s.get(url,params=params);r.raise_for_status();return r.text

# # ---------------- PubMed date parsing ----------------
# def parse_pub_date(article):
#     pub_date_el = article.find(".//PubDate")
#     year, month, day = "", "01", "01"
#     if pub_date_el is not None:
#         y = pub_date_el.findtext("Year")
#         m = pub_date_el.findtext("Month")
#         d = pub_date_el.findtext("Day")
#         medline = pub_date_el.findtext("MedlineDate")
#         if y: year = y
#         elif medline:
#             m_year = re.search(r"\d{4}", medline)
#             if m_year: year = m_year.group(0)
#         if m:
#             month = {
#                 "Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
#                 "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"
#             }.get(m[:3],"01")
#         if d: day=d
#     if not year: year="Unknown"
#     return year, f"{year}-{month}-{day}"

# # ---------------- General Scraper ----------------
# class GeneralScraper:
#     def __init__(self, fetcher, store, merge_report=False):
#         self.fetcher = fetcher
#         self.store = store
#         self.merge_report = merge_report
#         self.merge_log = []

#     def save_record(self, rec, identifiers):
#         ident = rec.get("DOI") or rec.get("Key") or normalize_title(rec.get("Title", ""))
#         inserted = self.store.insert(ident, rec)
#         if not inserted and self.merge_report:
#             self.merge_log.append(f"MERGED: {ident} from {rec.get('Url','')}")

#     def scrape(self, source, query, limit, from_year, to_year):
#         if source == "pubmed":
#             self.scrape_pubmed(query, limit, from_year, to_year)
#         elif source == "crossref":
#             self.scrape_crossref(query, limit, from_year, to_year)

#     def scrape_pubmed(self, query, limit, from_year, to_year):
#         search="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#         params={"db":"pubmed","term":query,"retmode":"json","retmax":100,
#                 "datetype":"pdat","mindate":f"{from_year}/01/01" if from_year else None,
#                 "maxdate":f"{to_year}/12/31" if to_year else None,
#                 "api_key":PUBMED_API_KEY if PUBMED_API_KEY else None}
#         retstart, fetched_ids=0, []
#         while True:
#             params["retstart"]=retstart
#             data=json.loads(self.fetcher.get(search,params))
#             ids=data.get("esearchresult",{}).get("idlist",[])
#             if not ids: break
#             fetched_ids.extend(ids)
#             retstart+=len(ids)
#             if limit and len(fetched_ids)>=limit: 
#                 fetched_ids=fetched_ids[:limit];break
#             if len(ids)<params["retmax"]: break
#             time.sleep(PUBMED_RATE_LIMIT)
#         if not fetched_ids: return
#         fetch="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
#         for i in range(0,len(fetched_ids),200):
#             chunk=fetched_ids[i:i+200]
#             txt=self.fetcher.get(fetch,{"db":"pubmed","id":",".join(chunk),"retmode":"xml"})
#             root=ET.fromstring(txt)
#             for art in root.findall(".//PubmedArticle"):
#                 pmid=art.findtext(".//PMID","")
#                 title=art.findtext(".//ArticleTitle","")
#                 abst=" ".join([el.text or "" for el in art.findall(".//Abstract/AbstractText")])
#                 if not PICO_PATTERN.search(title+" "+abst): continue
#                 found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
#                 authors=[f"{a.findtext('LastName','')}, {a.findtext('ForeName','')}" for a in art.findall(".//Author") if a.findtext("LastName")]
#                 doi=""
#                 for aid in art.findall(".//ArticleId"):
#                     if aid.get("IdType")=="doi": doi=aid.text
#                 pub_year,pub_date=parse_pub_date(art)
#                 rec={"Key":pmid,"Item Type":"journalArticle","Title":title,"Abstract Note":abst,
#                      "Author":"; ".join(authors),"Publication Title":art.findtext(".//Journal/Title",""),
#                      "Journal Abbreviation":art.findtext(".//Journal/ISOAbbreviation",""),
#                      "ISSN":art.findtext(".//Journal/ISSN",""),"Volume":art.findtext(".//JournalIssue/Volume",""),
#                      "Issue":art.findtext(".//JournalIssue/Issue",""),"Pages":art.findtext(".//Pagination/MedlinePgn",""),
#                      "Publication Year":pub_year,"Date":pub_date,"Language":art.findtext(".//Language",""),
#                      "DOI":doi,"Url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
#                      "Country":art.findtext(".//MedlineJournalInfo/Country",""),
#                      "Type":"; ".join([pt.text for pt in art.findall(".//PublicationType") if pt.text]),
#                      "Extra":"PICO_keywords_found: "+", ".join(found)}
#                 self.save_record(rec,[doi,pmid])

#     def scrape_crossref(self, query, limit, from_year, to_year):
#         url="https://api.crossref.org/works"; fetched=0
#         while fetched<limit:
#             rows=min(1000,limit-fetched)
#             filt=[]
#             if from_year: filt.append(f"from-pub-date:{from_year}-01-01")
#             if to_year: filt.append(f"until-pub-date:{to_year}-12-31")
#             params={"query":query,"rows":rows,"offset":fetched,"mailto":CROSSREF_EMAIL}
#             if filt: params["filter"]=",".join(filt)
#             items=json.loads(self.fetcher.get(url,params)).get("message",{}).get("items",[])
#             if not items: break
#             for it in items:
#                 title=it.get("title",[""])[0];abst=clean_text(it.get("abstract",""))
#                 if not PICO_PATTERN.search(title+" "+abst): continue
#                 found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
#                 authors=[f"{a.get('family','')}, {a.get('given','')}" for a in it.get("author",[])]
#                 year=""; dp=it.get("issued",{}).get("date-parts",[])
#                 if dp and dp[0]: year=str(dp[0][0])
#                 rec={"Key":it.get("DOI"),"Item Type":it.get("type","journal-article"),"Title":title,"Abstract Note":abst,
#                      "Author":"; ".join(authors),"Publication Title":(it.get("container-title") or [""])[0],
#                      "Journal Abbreviation":(it.get("short-container-title") or [""])[0] if it.get("short-container-title") else "",
#                      "ISSN":"; ".join(it.get("ISSN",[])),"Volume":it.get("volume",""),"Issue":it.get("issue",""),
#                      "Pages":it.get("page",""),"Publication Year":year,"Date":"",
#                      "Publisher":it.get("publisher",""),"Language":it.get("language",""),
#                      "DOI":it.get("DOI",""),"Url":it.get("URL",""),"Meeting Name":it.get("event",{}).get("name",""),
#                      "Conference Name":it.get("event",{}).get("name",""),
#                      "Place":it.get("event",{}).get("location","") or it.get("publisher-location",""),
#                      "Extra":"PICO_keywords_found: "+", ".join(found)}
#                 self.save_record(rec,[it.get("DOI")])
#             fetched+=len(items)
#             if len(items)<rows: break

#     def finalize(self):
#         if self.merge_report and self.merge_log:
#             with open(MERGE_REPORT_FILE,"w") as f:
#                 f.write("Merge Report:\n")
#                 for line in self.merge_log: f.write(line+"\n")
#             log.info("Merge report saved to %s", MERGE_REPORT_FILE)

# # ---------------- Export ----------------
# def export(recs):
#     df=pd.DataFrame([{**zotero_template(),**r} for r in recs],columns=ZOTERO_HEADER)
#     df.to_csv(CSV_OUTPUT,index=False,encoding="utf-8")
#     df.to_excel(XLSX_OUTPUT,index=False,engine="openpyxl")
#     with open(JSON_OUTPUT,"w",encoding="utf-8") as f: json.dump(recs,f,ensure_ascii=False,indent=2)
#     log.info("Exported %d records",len(recs))

# # ---------------- Run ----------------
# def run(query,sources,limit,from_year,to_year,merge_report=False):
#     store=Storage();fetcher=Fetcher();scraper=GeneralScraper(fetcher,store,merge_report)
#     for src in sources: scraper.scrape(src,query,limit,from_year,to_year)
#     recs=store.all();export(recs);scraper.finalize();store.close()

# if __name__=="__main__":
#     p=argparse.ArgumentParser()
#     p.add_argument("--query",required=True)
#     p.add_argument("--sources",default="pubmed,crossref")
#     p.add_argument("--limit",type=int,default=20)
#     p.add_argument("--from_year",type=int)
#     p.add_argument("--to_year",type=int)
#     p.add_argument("--years",type=int)
#     p.add_argument("--merge-report",action="store_true",help="Generate merge report for duplicates")
#     a=p.parse_args()
#     fy,ty=a.from_year,a.to_year
#     if a.years: ty=datetime.now().year;fy=ty-a.years+1
#     run(a.query,[s.strip() for s in a.sources.split(",")],a.limit,fy,ty,a.merge_report)




# #!/usr/bin/env python3
# """
# Full crawl4ai mode (what you asked for):

# Use crawl4ai WebCrawler for:

# Scraping EuropePMC (when API fails or not enough metadata)

# Scraping arXiv directly from HTML if API doesn’t give abstracts

# Extracting structured info (titles, abstracts, authors) from raw HTML using selectors or AI (PICO keywords)
# """
# """
# multi_source_scraper_crawl4ai.py

# - Unified Scraper: PubMed + CrossRef + EuropePMC + arXiv
# - Deduplicates by DOI > PMID > normalized Title
# - PICO keyword filtering
# - Zotero-style metadata
# - Exports JSON, CSV, XLSX
# - Merge reporting (--merge-report)
# - Uses crawl4ai for non-API sources
# """

# import argparse, json, re, sqlite3, logging, time
# from datetime import datetime
# import pandas as pd
# import xml.etree.ElementTree as ET
# import requests

# # --- crawl4ai ---
# from crawl4ai import WebCrawler

# # ---------------- CONFIG ----------------
# CONTACT_EMAIL = "keertisubramanyasm@gmail.com"
# USER_AGENT = f"MultiSourceScraper/1.0 (+{CONTACT_EMAIL})"
# DB_PATH = "scraper_results.db"
# JSON_OUTPUT = "scraper_results.json"
# CSV_OUTPUT = "scraper_results.csv"
# XLSX_OUTPUT = "scraper_results.xlsx"
# MERGE_REPORT_FILE = "merge_report.txt"

# PUBMED_API_KEY = "c2f307fc5acc4197325e5d9234ff271aa608"  
# CROSSREF_EMAIL = CONTACT_EMAIL
# PUBMED_RATE_LIMIT = 0.34  

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
# ZOTERO_HEADER=[ "Key","Item Type","Publication Year","Author","Title","Publication Title","ISBN","ISSN","DOI","Url",
# "Abstract Note","Date","Date Added","Date Modified","Access Date","Pages","Num Pages","Issue","Volume",
# "Number Of Volumes","Journal Abbreviation","Short Title","Series","Series Number","Series Text","Series Title",
# "Publisher","Place","Language","Rights","Type","Archive","Archive Location","Library Catalog","Call Number",
# "Extra","Meeting Name","Conference Name","Country" ]

# def zotero_template(): return {k:"" for k in ZOTERO_HEADER}

# # ---------------- Storage ----------------
# class Storage:
#     def __init__(self,path=DB_PATH): 
#         self.conn=sqlite3.connect(path)
#         self.create()
#     def create(self):
#         self.conn.execute("CREATE TABLE IF NOT EXISTS recs(id INTEGER PRIMARY KEY, identifier TEXT UNIQUE, data TEXT)")
#         self.conn.commit()
#     def insert(self,ident,data):
#         try:
#             self.conn.execute("INSERT INTO recs(identifier,data) VALUES(?,?)",(ident,json.dumps(data)))
#             self.conn.commit()
#             return True
#         except sqlite3.IntegrityError:
#             return False
#     def all(self):
#         cur=self.conn.cursor();cur.execute("SELECT data FROM recs")
#         return [json.loads(r[0]) for r in cur.fetchall()]
#     def close(self): self.conn.close()

# # ---------------- Fetcher ----------------
# class Fetcher:
#     def __init__(self):
#         self.s=requests.Session()
#         self.s.headers.update({"User-Agent":USER_AGENT})
#         self.c=WebCrawler()
#     def get(self,url,params=None):
#         try: 
#             return self.c.get(url,params=params).text
#         except Exception as e:
#             r=self.s.get(url,params=params);r.raise_for_status();return r.text

# # ---------------- PubMed date parsing ----------------
# def parse_pub_date(article):
#     pub_date_el = article.find(".//PubDate")
#     year, month, day = "", "01", "01"
#     if pub_date_el is not None:
#         y = pub_date_el.findtext("Year")
#         m = pub_date_el.findtext("Month")
#         d = pub_date_el.findtext("Day")
#         medline = pub_date_el.findtext("MedlineDate")
#         if y: year = y
#         elif medline:
#             m_year = re.search(r"\d{4}", medline)
#             if m_year: year = m_year.group(0)
#         if m:
#             month = {
#                 "Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
#                 "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"
#             }.get(m[:3],"01")
#         if d: day=d
#     if not year: year="Unknown"
#     return year, f"{year}-{month}-{day}"

# # ---------------- General Scraper ----------------
# class GeneralScraper:
#     def __init__(self, fetcher, store, merge_report=False):
#         self.fetcher = fetcher
#         self.store = store
#         self.merge_report = merge_report
#         self.merge_log = []

#     def save_record(self, rec, identifiers):
#         ident = rec.get("DOI") or rec.get("Key") or normalize_title(rec.get("Title", ""))
#         inserted = self.store.insert(ident, rec)
#         if not inserted and self.merge_report:
#             self.merge_log.append(f"MERGED: {ident} from {rec.get('Url','')}")

#     def scrape(self, source, query, limit, from_year, to_year):
#         if source == "pubmed":
#             self.scrape_pubmed(query, limit, from_year, to_year)
#         elif source == "crossref":
#             self.scrape_crossref(query, limit, from_year, to_year)
#         elif source == "europepmc":
#             self.scrape_europepmc(query, limit)
#         elif source == "arxiv":
#             self.scrape_arxiv(query, limit)

#     # ---------- PubMed ----------
#     def scrape_pubmed(self, query, limit, from_year, to_year):
#         search="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#         params={"db":"pubmed","term":query,"retmode":"json","retmax":100,
#                 "datetype":"pdat","mindate":f"{from_year}/01/01" if from_year else None,
#                 "maxdate":f"{to_year}/12/31" if to_year else None,
#                 "api_key":PUBMED_API_KEY if PUBMED_API_KEY else None}
#         retstart, fetched_ids=0, []
#         while True:
#             params["retstart"]=retstart
#             data=json.loads(self.fetcher.get(search,params))
#             ids=data.get("esearchresult",{}).get("idlist",[])
#             if not ids: break
#             fetched_ids.extend(ids)
#             retstart+=len(ids)
#             if limit and len(fetched_ids)>=limit: 
#                 fetched_ids=fetched_ids[:limit];break
#             if len(ids)<params["retmax"]: break
#             time.sleep(PUBMED_RATE_LIMIT)
#         if not fetched_ids: return
#         fetch="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
#         for i in range(0,len(fetched_ids),200):
#             chunk=fetched_ids[i:i+200]
#             txt=self.fetcher.get(fetch,{"db":"pubmed","id":",".join(chunk),"retmode":"xml"})
#             root=ET.fromstring(txt)
#             for art in root.findall(".//PubmedArticle"):
#                 pmid=art.findtext(".//PMID","")
#                 title=art.findtext(".//ArticleTitle","")
#                 abst=" ".join([el.text or "" for el in art.findall(".//Abstract/AbstractText")])
#                 if not PICO_PATTERN.search(title+" "+abst): continue
#                 found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
#                 authors=[f"{a.findtext('LastName','')}, {a.findtext('ForeName','')}" for a in art.findall(".//Author") if a.findtext("LastName")]
#                 doi=""
#                 for aid in art.findall(".//ArticleId"):
#                     if aid.get("IdType")=="doi": doi=aid.text
#                 pub_year,pub_date=parse_pub_date(art)
#                 rec={"Key":pmid,"Item Type":"journalArticle","Title":title,"Abstract Note":abst,
#                      "Author":"; ".join(authors),"Publication Title":art.findtext(".//Journal/Title",""),
#                      "Publication Year":pub_year,"Date":pub_date,"DOI":doi,
#                      "Url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
#                      "Extra":"PICO_keywords_found: "+", ".join(found)}
#                 self.save_record(rec,[doi,pmid])

#     # ---------- CrossRef ----------
#     def scrape_crossref(self, query, limit, from_year, to_year):
#         url="https://api.crossref.org/works"; fetched=0
#         while fetched<limit:
#             rows=min(1000,limit-fetched)
#             filt=[]
#             if from_year: filt.append(f"from-pub-date:{from_year}-01-01")
#             if to_year: filt.append(f"until-pub-date:{to_year}-12-31")
#             params={"query":query,"rows":rows,"offset":fetched,"mailto":CROSSREF_EMAIL}
#             if filt: params["filter"]=",".join(filt)
#             items=json.loads(self.fetcher.get(url,params)).get("message",{}).get("items",[])
#             if not items: break
#             for it in items:
#                 title=it.get("title",[""])[0];abst=clean_text(it.get("abstract",""))
#                 if not PICO_PATTERN.search(title+" "+abst): continue
#                 found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
#                 authors=[f"{a.get('family','')}, {a.get('given','')}" for a in it.get("author",[])]
#                 year=""; dp=it.get("issued",{}).get("date-parts",[])
#                 if dp and dp[0]: year=str(dp[0][0])
#                 rec={"Key":it.get("DOI"),"Item Type":it.get("type","journal-article"),
#                      "Title":title,"Abstract Note":abst,"Author":"; ".join(authors),
#                      "Publication Year":year,"DOI":it.get("DOI",""),"Url":it.get("URL",""),
#                      "Extra":"PICO_keywords_found: "+", ".join(found)}
#                 self.save_record(rec,[it.get("DOI")])
#             fetched+=len(items)
#             if len(items)<rows: break

#     # ---------- EuropePMC ----------
#     # def scrape_europepmc(self, query, limit):
#     #     url="https://www.ebi.ac.uk/europepmc/webservices/rest/search"
#     #     params={"query":query,"format":"json","pageSize":limit}
#     #     items=json.loads(self.fetcher.get(url,params)).get("resultList",{}).get("result",[])
#     #     for it in items:
#     #         title=it.get("title","");abst=it.get("abstractText","")
#     #         if not PICO_PATTERN.search(title+" "+abst): continue
#     #         found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
#     #         rec={"Key":it.get("id"),"Item Type":"journalArticle","Title":title,"Abstract Note":abst,
#     #              "Author":it.get("authorString",""),"Publication Year":it.get("pubYear",""),
#     #              "DOI":it.get("doi",""),"Url":it.get("fullTextUrlList",{}).get("fullTextUrl",{}),
#     #              "Extra":"PICO_keywords_found: "+", ".join(found)}
#     #         self.save_record(rec,[it.get("doi"),it.get("id")])

#     # # ---------- arXiv ----------
#     # def scrape_arxiv(self, query, limit):
#     #     url="http://export.arxiv.org/api/query"
#     #     params={"search_query":query,"max_results":limit}
#     #     txt=self.fetcher.get(url,params)
#     #     entries=re.findall(r"<entry>(.*?)</entry>",txt,re.S)
#     #     for e in entries:
#     #         title=clean_text(re.search(r"<title>(.*?)</title>",e,re.S).group(1))
#     #         abst=clean_text(re.search(r"<summary>(.*?)</summary>",e,re.S).group(1))
#     #         if not PICO_PATTERN.search(title+" "+abst): continue
#     #         found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
#     #         doi_match=re.search(r"<arxiv:doi>(.*?)</arxiv:doi>",e)
#     #         rec={"Key":doi_match.group(1) if doi_match else title[:20],
#     #              "Item Type":"preprint","Title":title,"Abstract Note":abst,
#     #              "Publication Year":re.search(r"<published>(\d{4})",e).group(1),
#     #              "Url":re.search(r"<id>(.*?)</id>",e).group(1),
#     #              "DOI":doi_match.group(1) if doi_match else "",
#     #              "Extra":"PICO_keywords_found: "+", ".join(found)}
#     #         self.save_record(rec,[rec["DOI"],normalize_title(title)])

#     def finalize(self):
#         if self.merge_report and self.merge_log:
#             with open(MERGE_REPORT_FILE,"w") as f:
#                 f.write("Merge Report:\n")
#                 for line in self.merge_log: f.write(line+"\n")
#             log.info("Merge report saved to %s", MERGE_REPORT_FILE)

# # ---------------- Export ----------------
# def export(recs):
#     df=pd.DataFrame([{**zotero_template(),**r} for r in recs],columns=ZOTERO_HEADER)
#     df.to_csv(CSV_OUTPUT,index=False,encoding="utf-8")
#     df.to_excel(XLSX_OUTPUT,index=False,engine="openpyxl")
#     with open(JSON_OUTPUT,"w",encoding="utf-8") as f: json.dump(recs,f,ensure_ascii=False,indent=2)
#     log.info("Exported %d records",len(recs))

# # ---------------- Run ----------------
# def run(query,sources,limit,from_year,to_year,merge_report=False):
#     store=Storage();fetcher=Fetcher();scraper=GeneralScraper(fetcher,store,merge_report)
#     for src in sources: scraper.scrape(src,query,limit,from_year,to_year)
#     recs=store.all();export(recs);scraper.finalize();store.close()

# if __name__=="__main__":
#     p=argparse.ArgumentParser()
#     p.add_argument("--query",required=True)
#     p.add_argument("--sources",default="pubmed,crossref,europepmc,arxiv")
#     p.add_argument("--limit",type=int,default=20)
#     p.add_argument("--from_year",type=int)
#     p.add_argument("--to_year",type=int)
#     p.add_argument("--merge-report",action="store_true",help="Generate merge report for duplicates")
#     a=p.parse_args()
#     run(a.query,[s.strip() for s in a.sources.split(",")],a.limit,a.from_year,a.to_year,a.merge_report)




#!/usr/bin/env python3
# """
# multi_source_scraper.py
# Full crawl4ai mode (what you asked for):

# Use crawl4ai WebCrawler for:

# Scraping EuropePMC (when API fails or not enough metadata)

# Scraping arXiv directly from HTML if API doesn’t give abstracts
# - Unified Scraper: PubMed + CrossRef (extendable to arXiv, EuropePMC, etc.)
# - Deduplicates by DOI > PMID > normalized Title
# - PICO keyword filtering
# - Zotero-style metadata
# - Exports JSON, CSV, XLSX
# - Merge reporting (--merge-report)
# - Supports Crawl4AI (both AsyncWebCrawler and WebCrawler versions)
# """

# import argparse, json, re, sqlite3, logging, time, asyncio
# from datetime import datetime
# import pandas as pd
# import xml.etree.ElementTree as ET
# import requests

# # ---------------- CONFIG ----------------
# CONTACT_EMAIL = "keertisubramanyasm@gmail.com"
# USER_AGENT = f"MultiSourceScraper/1.0 (+{CONTACT_EMAIL})"
# DB_PATH = "scraper_results.db"
# JSON_OUTPUT = "scraper_results.json"
# CSV_OUTPUT = "scraper_results.csv"
# XLSX_OUTPUT = "scraper_results.xlsx"
# MERGE_REPORT_FILE = "merge_report.txt"

# PUBMED_API_KEY = "c2f307fc5acc4197325e5d9234ff271aa608"  
# CROSSREF_EMAIL = CONTACT_EMAIL
# PUBMED_RATE_LIMIT = 0.34  

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
# ZOTERO_HEADER=[ "Key","Item Type","Publication Year","Author","Title","Publication Title","ISBN","ISSN","DOI","Url",
# "Abstract Note","Date","Date Added","Date Modified","Access Date","Pages","Num Pages","Issue","Volume",
# "Number Of Volumes","Journal Abbreviation","Short Title","Series","Series Number","Series Text","Series Title",
# "Publisher","Place","Language","Rights","Type","Archive","Archive Location","Library Catalog","Call Number",
# "Extra","Meeting Name","Conference Name","Country" ]

# def zotero_template(): return {k:"" for k in ZOTERO_HEADER}

# # ---------------- Storage ----------------
# class Storage:
#     def __init__(self,path=DB_PATH): 
#         self.conn=sqlite3.connect(path)
#         self.create()
#     def create(self):
#         self.conn.execute("CREATE TABLE IF NOT EXISTS recs(id INTEGER PRIMARY KEY, identifier TEXT UNIQUE, data TEXT)")
#         self.conn.commit()
#     def insert(self,ident,data):
#         try:
#             self.conn.execute("INSERT INTO recs(identifier,data) VALUES(?,?)",(ident,json.dumps(data)))
#             self.conn.commit()
#             return True
#         except sqlite3.IntegrityError:
#             return False
#     def all(self):
#         cur=self.conn.cursor();cur.execute("SELECT data FROM recs")
#         return [json.loads(r[0]) for r in cur.fetchall()]
#     def close(self): self.conn.close()

# # ---------------- Fetcher ----------------
# USE_CRAWL4AI = True
# crawl4ai_mode = None
# crawl4ai_fetcher = None

# try:
#     # Try new versions (with WebCrawler)
#     from crawl4ai import WebCrawler
#     log.info("Using Crawl4AI WebCrawler (new version)")
#     crawl4ai_mode = "webcrawler"
#     class Crawl4aiFetcher:
#         def get(self,url,params=None):
#             c = WebCrawler()
#             res = c.get(url,params=params)
#             return res.text if res else None
#     crawl4ai_fetcher = Crawl4aiFetcher()

# except ImportError:
#     try:
#         # Try v0.7.4 Async version
#         from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
#         log.info("Using Crawl4AI AsyncWebCrawler (v0.7.4)")
#         crawl4ai_mode = "async"
#         class Crawl4aiFetcher:
#             def __init__(self):
#                 self.config = CrawlerRunConfig()
#             async def _fetch(self,url,params=None):
#                 async with AsyncWebCrawler(self.config) as crawler:
#                     result = await crawler.arun(url)
#                     return result.html if result else None
#             def get(self,url,params=None):
#                 return asyncio.run(self._fetch(url,params))
#         crawl4ai_fetcher = Crawl4aiFetcher()
#     except ImportError:
#         USE_CRAWL4AI = False
#         log.warning("Crawl4AI not available, falling back to requests")

# class Fetcher:
#     def __init__(self):
#         self.s=requests.Session()
#         self.s.headers.update({"User-Agent":USER_AGENT})
#     def get(self,url,params=None):
#         if USE_CRAWL4AI and crawl4ai_fetcher:
#             try:
#                 return crawl4ai_fetcher.get(url,params)
#             except Exception as e:
#                 log.warning("Crawl4AI failed, fallback: %s",e)
#         r=self.s.get(url,params=params);r.raise_for_status();return r.text

# # ---------------- PubMed date parsing ----------------
# def parse_pub_date(article):
#     pub_date_el = article.find(".//PubDate")
#     year, month, day = "", "01", "01"
#     if pub_date_el is not None:
#         y = pub_date_el.findtext("Year")
#         m = pub_date_el.findtext("Month")
#         d = pub_date_el.findtext("Day")
#         medline = pub_date_el.findtext("MedlineDate")
#         if y: year = y
#         elif medline:
#             m_year = re.search(r"\d{4}", medline)
#             if m_year: year = m_year.group(0)
#         if m:
#             month = {
#                 "Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
#                 "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"
#             }.get(m[:3],"01")
#         if d: day=d
#     if not year: year="Unknown"
#     return year, f"{year}-{month}-{day}"

# # ---------------- General Scraper ----------------
# class GeneralScraper:
#     def __init__(self, fetcher, store, merge_report=False):
#         self.fetcher = fetcher
#         self.store = store
#         self.merge_report = merge_report
#         self.merge_log = []

#     def save_record(self, rec, identifiers):
#         ident = rec.get("DOI") or rec.get("Key") or normalize_title(rec.get("Title", ""))
#         inserted = self.store.insert(ident, rec)
#         if not inserted and self.merge_report:
#             self.merge_log.append(f"MERGED: {ident} from {rec.get('Url','')}")

#     def scrape(self, source, query, limit, from_year, to_year):
#         if source == "pubmed":
#             self.scrape_pubmed(query, limit, from_year, to_year)
#         elif source == "crossref":
#             self.scrape_crossref(query, limit, from_year, to_year)

#     def scrape_pubmed(self, query, limit, from_year, to_year):
#         search="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#         params={"db":"pubmed","term":query,"retmode":"json","retmax":100,
#                 "datetype":"pdat","mindate":f"{from_year}/01/01" if from_year else None,
#                 "maxdate":f"{to_year}/12/31" if to_year else None,
#                 "api_key":PUBMED_API_KEY if PUBMED_API_KEY else None}
#         retstart, fetched_ids=0, []
#         while True:
#             params["retstart"]=retstart
#             data=json.loads(self.fetcher.get(search,params))
#             ids=data.get("esearchresult",{}).get("idlist",[])
#             if not ids: break
#             fetched_ids.extend(ids)
#             retstart+=len(ids)
#             if limit and len(fetched_ids)>=limit: 
#                 fetched_ids=fetched_ids[:limit];break
#             if len(ids)<params["retmax"]: break
#             time.sleep(PUBMED_RATE_LIMIT)
#         if not fetched_ids: return
#         fetch="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
#         for i in range(0,len(fetched_ids),200):
#             chunk=fetched_ids[i:i+200]
#             txt=self.fetcher.get(fetch,{"db":"pubmed","id":",".join(chunk),"retmode":"xml"})
#             root=ET.fromstring(txt)
#             for art in root.findall(".//PubmedArticle"):
#                 pmid=art.findtext(".//PMID","")
#                 title=art.findtext(".//ArticleTitle","")
#                 abst=" ".join([el.text or "" for el in art.findall(".//Abstract/AbstractText")])
#                 if not PICO_PATTERN.search(title+" "+abst): continue
#                 found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
#                 authors=[f"{a.findtext('LastName','')}, {a.findtext('ForeName','')}" for a in art.findall(".//Author") if a.findtext("LastName")]
#                 doi=""
#                 for aid in art.findall(".//ArticleId"):
#                     if aid.get("IdType")=="doi": doi=aid.text
#                 pub_year,pub_date=parse_pub_date(art)
#                 rec={"Key":pmid,"Item Type":"journalArticle","Title":title,"Abstract Note":abst,
#                      "Author":"; ".join(authors),"Publication Title":art.findtext(".//Journal/Title",""),
#                      "Journal Abbreviation":art.findtext(".//Journal/ISOAbbreviation",""),
#                      "ISSN":art.findtext(".//Journal/ISSN",""),"Volume":art.findtext(".//JournalIssue/Volume",""),
#                      "Issue":art.findtext(".//JournalIssue/Issue",""),"Pages":art.findtext(".//Pagination/MedlinePgn",""),
#                      "Publication Year":pub_year,"Date":pub_date,"Language":art.findtext(".//Language",""),
#                      "DOI":doi,"Url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
#                      "Country":art.findtext(".//MedlineJournalInfo/Country",""),
#                      "Type":"; ".join([pt.text for pt in art.findall(".//PublicationType") if pt.text]),
#                      "Extra":"PICO_keywords_found: "+", ".join(found)}
#                 self.save_record(rec,[doi,pmid])

#     def scrape_crossref(self, query, limit, from_year, to_year):
#         url="https://api.crossref.org/works"; fetched=0
#         while fetched<limit:
#             rows=min(1000,limit-fetched)
#             filt=[]
#             if from_year: filt.append(f"from-pub-date:{from_year}-01-01")
#             if to_year: filt.append(f"until-pub-date:{to_year}-12-31")
#             params={"query":query,"rows":rows,"offset":fetched,"mailto":CROSSREF_EMAIL}
#             if filt: params["filter"]=",".join(filt)
#             items=json.loads(self.fetcher.get(url,params)).get("message",{}).get("items",[])
#             if not items: break
#             for it in items:
#                 title=it.get("title",[""])[0];abst=clean_text(it.get("abstract",""))
#                 if not PICO_PATTERN.search(title+" "+abst): continue
#                 found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
#                 authors=[f"{a.get('family','')}, {a.get('given','')}" for a in it.get("author",[])]
#                 year=""; dp=it.get("issued",{}).get("date-parts",[])
#                 if dp and dp[0]: year=str(dp[0][0])
#                 rec={"Key":it.get("DOI"),"Item Type":it.get("type","journal-article"),"Title":title,"Abstract Note":abst,
#                      "Author":"; ".join(authors),"Publication Title":(it.get("container-title") or [""])[0],
#                      "Journal Abbreviation":(it.get("short-container-title") or [""])[0] if it.get("short-container-title") else "",
#                      "ISSN":"; ".join(it.get("ISSN",[])),"Volume":it.get("volume",""),"Issue":it.get("issue",""),
#                      "Pages":it.get("page",""),"Publication Year":year,"Date":"",
#                      "Publisher":it.get("publisher",""),"Language":it.get("language",""),
#                      "DOI":it.get("DOI",""),"Url":it.get("URL",""),"Meeting Name":it.get("event",{}).get("name",""),
#                      "Conference Name":it.get("event",{}).get("name",""),
#                      "Place":it.get("event",{}).get("location","") or it.get("publisher-location",""),
#                      "Extra":"PICO_keywords_found: "+", ".join(found)}
#                 self.save_record(rec,[it.get("DOI")])
#             fetched+=len(items)
#             if len(items)<rows: break

#     def finalize(self):
#         if self.merge_report and self.merge_log:
#             with open(MERGE_REPORT_FILE,"w") as f:
#                 f.write("Merge Report:\n")
#                 for line in self.merge_log: f.write(line+"\n")
#             log.info("Merge report saved to %s", MERGE_REPORT_FILE)

# # ---------------- Export ----------------
# def export(recs):
#     df=pd.DataFrame([{**zotero_template(),**r} for r in recs],columns=ZOTERO_HEADER)
#     df.to_csv(CSV_OUTPUT,index=False,encoding="utf-8")
#     df.to_excel(XLSX_OUTPUT,index=False,engine="openpyxl")
#     with open(JSON_OUTPUT,"w",encoding="utf-8") as f: json.dump(recs,f,ensure_ascii=False,indent=2)
#     log.info("Exported %d records",len(recs))

# # ---------------- Run ----------------
# def run(query,sources,limit,from_year,to_year,merge_report=False):
#     store=Storage();fetcher=Fetcher();scraper=GeneralScraper(fetcher,store,merge_report)
#     for src in sources: scraper.scrape(src,query,limit,from_year,to_year)
#     recs=store.all();export(recs);scraper.finalize();store.close()

# if __name__=="__main__":
#     p=argparse.ArgumentParser()
#     p.add_argument("--query",required=True)
#     p.add_argument("--sources",default="pubmed,crossref")
#     p.add_argument("--limit",type=int,default=20)
#     p.add_argument("--from_year",type=int)
#     p.add_argument("--to_year",type=int)
#     p.add_argument("--years",type=int)
#     p.add_argument("--merge-report",action="store_true",help="Generate merge report for duplicates")
#     a=p.parse_args()
#     fy,ty=a.from_year,a.to_year
#     if a.years: ty=datetime.now().year;fy=ty-a.years+1
#     run(a.query,[s.strip() for s in a.sources.split(",")],a.limit,fy,ty,a.merge_report)

"""
multi_source_scraper.py
Full crawl4ai mode (title-first deduplication):

- Major deduplication check on Title (normalized)
- Then DOI
- Then PMID
- Unified Scraper: PubMed + CrossRef (extendable to arXiv, EuropePMC, etc.)
- PICO keyword filtering
- Zotero-style metadata
- Exports JSON, CSV, XLSX
- Merge reporting (--merge-report)
- Supports Crawl4AI (both AsyncWebCrawler and WebCrawler versions)
"""

import argparse, json, re, sqlite3, logging, time, asyncio
from datetime import datetime
import pandas as pd
import xml.etree.ElementTree as ET
import requests

# ---------------- CONFIG ----------------
CONTACT_EMAIL = "keertisubramanyasm@gmail.com"
USER_AGENT = f"MultiSourceScraper/1.0 (+{CONTACT_EMAIL})"
DB_PATH = "scraper_results.db"
JSON_OUTPUT = "scraper_results.json"
CSV_OUTPUT = "scraper_results.csv"
XLSX_OUTPUT = "scraper_results.xlsx"
MERGE_REPORT_FILE = "merge_report.txt"

PUBMED_API_KEY = "c2f307fc5acc4197325e5d9234ff271aa608"  
CROSSREF_EMAIL = CONTACT_EMAIL
PUBMED_RATE_LIMIT = 0.34  

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("multi_source_scraper")

# ---------------- UTIL ----------------
def clean_text(t): 
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",t or "")).strip()

def normalize_title(t): 
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",(t or "").lower())).strip()

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
ZOTERO_HEADER=[ "Key","Item Type","Publication Year","Author","Title","Publication Title","ISBN","ISSN","DOI","Url",
"Abstract Note","Date","Date Added","Date Modified","Access Date","Pages","Num Pages","Issue","Volume",
"Number Of Volumes","Journal Abbreviation","Short Title","Series","Series Number","Series Text","Series Title",
"Publisher","Place","Language","Rights","Type","Archive","Archive Location","Library Catalog","Call Number",
"Extra","Meeting Name","Conference Name","Country" ]

def zotero_template(): return {k:"" for k in ZOTERO_HEADER}

# ---------------- Storage ----------------
class Storage:
    def __init__(self,path=DB_PATH): 
        self.conn=sqlite3.connect(path)
        self.create()
    def create(self):
        self.conn.execute("CREATE TABLE IF NOT EXISTS recs(id INTEGER PRIMARY KEY, identifier TEXT UNIQUE, data TEXT)")
        self.conn.commit()
    def insert(self,ident,data):
        try:
            self.conn.execute("INSERT INTO recs(identifier,data) VALUES(?,?)",(ident,json.dumps(data)))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    def exists(self,identifiers):
        cur=self.conn.cursor()
        for ident in identifiers:
            cur.execute("SELECT 1 FROM recs WHERE identifier=?",(ident,))
            if cur.fetchone(): return True
        return False
    def all(self):
        cur=self.conn.cursor();cur.execute("SELECT data FROM recs")
        return [json.loads(r[0]) for r in cur.fetchall()]
    def close(self): self.conn.close()

# ---------------- Fetcher ----------------
USE_CRAWL4AI = True
crawl4ai_mode = None
crawl4ai_fetcher = None

try:
    from crawl4ai import WebCrawler
    log.info("Using Crawl4AI WebCrawler (new version)")
    crawl4ai_mode = "webcrawler"
    class Crawl4aiFetcher:
        def get(self,url,params=None):
            c = WebCrawler()
            res = c.get(url,params=params)
            return res.text if res else None
    crawl4ai_fetcher = Crawl4aiFetcher()
except ImportError:
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
        log.info("Using Crawl4AI AsyncWebCrawler (v0.7.4)")
        crawl4ai_mode = "async"
        class Crawl4aiFetcher:
            def __init__(self):
                self.config = CrawlerRunConfig()
            async def _fetch(self,url,params=None):
                async with AsyncWebCrawler(self.config) as crawler:
                    result = await crawler.arun(url)
                    return result.html if result else None
            def get(self,url,params=None):
                return asyncio.run(self._fetch(url,params))
        crawl4ai_fetcher = Crawl4aiFetcher()
    except ImportError:
        USE_CRAWL4AI = False
        log.warning("Crawl4AI not available, falling back to requests")

class Fetcher:
    def __init__(self):
        self.s=requests.Session()
        self.s.headers.update({"User-Agent":USER_AGENT})
    def get(self,url,params=None):
        if USE_CRAWL4AI and crawl4ai_fetcher:
            try:
                return crawl4ai_fetcher.get(url,params)
            except Exception as e:
                log.warning("Crawl4AI failed, fallback: %s",e)
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
        if y: year = y
        elif medline:
            m_year = re.search(r"\d{4}", medline)
            if m_year: year = m_year.group(0)
        if m:
            month = {
                "Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
                "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"
            }.get(m[:3],"01")
        if d: day=d
    if not year: year="Unknown"
    return year, f"{year}-{month}-{day}"

# ---------------- General Scraper ----------------
class GeneralScraper:
    def __init__(self, fetcher, store, merge_report=False):
        self.fetcher = fetcher
        self.store = store
        self.merge_report = merge_report
        self.merge_log = []

    def save_record(self, rec, identifiers):
        # Deduplication fix: Title > DOI > PMID
        norm_title = normalize_title(rec.get("Title",""))
        doi = rec.get("DOI")
        pmid = rec.get("Key")
        all_ids = [i for i in [norm_title, doi, pmid] if i]  # Title first!

        if self.store.exists(all_ids):
            if self.merge_report:
                self.merge_log.append(f"MERGED: {norm_title or doi or pmid} from {rec.get('Url','')}")
            return
        
        ident = norm_title or doi or pmid
        self.store.insert(ident, rec)

    def scrape(self, source, query, limit, from_year, to_year):
        if source == "pubmed":
            self.scrape_pubmed(query, limit, from_year, to_year)
        elif source == "crossref":
            self.scrape_crossref(query, limit, from_year, to_year)

    # ---------------- PubMed Scraper ----------------
    def scrape_pubmed(self, query, limit, from_year, to_year):
        search="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params={"db":"pubmed","term":query,"retmode":"json","retmax":100,
                "datetype":"pdat","mindate":f"{from_year}/01/01" if from_year else None,
                "maxdate":f"{to_year}/12/31" if to_year else None,
                "api_key":PUBMED_API_KEY if PUBMED_API_KEY else None}
        retstart, fetched_ids=0, []
        while True:
            params["retstart"]=retstart
            data=json.loads(self.fetcher.get(search,params))
            ids=data.get("esearchresult",{}).get("idlist",[])
            if not ids: break
            fetched_ids.extend(ids)
            retstart+=len(ids)
            if limit and len(fetched_ids)>=limit: 
                fetched_ids=fetched_ids[:limit];break
            if len(ids)<params["retmax"]: break
            time.sleep(PUBMED_RATE_LIMIT)
        if not fetched_ids: return
        fetch="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        for i in range(0,len(fetched_ids),200):
            chunk=fetched_ids[i:i+200]
            txt=self.fetcher.get(fetch,{"db":"pubmed","id":",".join(chunk),"retmode":"xml"})
            root=ET.fromstring(txt)
            for art in root.findall(".//PubmedArticle"):
                pmid=art.findtext(".//PMID","")
                title=art.findtext(".//ArticleTitle","")
                abst=" ".join([el.text or "" for el in art.findall(".//Abstract/AbstractText")])
                if not PICO_PATTERN.search(title+" "+abst): continue
                found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
                authors=[f"{a.findtext('LastName','')}, {a.findtext('ForeName','')}" for a in art.findall(".//Author") if a.findtext("LastName")]
                doi=""
                for aid in art.findall(".//ArticleId"):
                    if aid.get("IdType")=="doi": doi=aid.text
                pub_year,pub_date=parse_pub_date(art)
                rec={"Key":pmid,"Item Type":"journalArticle","Title":title,"Abstract Note":abst,
                     "Author":"; ".join(authors),"Publication Title":art.findtext(".//Journal/Title",""),
                     "Journal Abbreviation":art.findtext(".//Journal/ISOAbbreviation",""),
                     "ISSN":art.findtext(".//Journal/ISSN",""),"Volume":art.findtext(".//JournalIssue/Volume",""),
                     "Issue":art.findtext(".//JournalIssue/Issue",""),"Pages":art.findtext(".//Pagination/MedlinePgn",""),
                     "Publication Year":pub_year,"Date":pub_date,"Language":art.findtext(".//Language",""),
                     "DOI":doi,"Url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                     "Country":art.findtext(".//MedlineJournalInfo/Country",""),
                     "Type":"; ".join([pt.text for pt in art.findall(".//PublicationType") if pt.text]),
                     "Extra":"PICO_keywords_found: "+", ".join(found)}
                self.save_record(rec,[doi,pmid])

    # ---------------- CrossRef Scraper ----------------
    def scrape_crossref(self, query, limit, from_year, to_year):
        url="https://api.crossref.org/works"; fetched=0
        while fetched<limit:
            rows=min(1000,limit-fetched)
            filt=[]
            if from_year: filt.append(f"from-pub-date:{from_year}-01-01")
            if to_year: filt.append(f"until-pub-date:{to_year}-12-31")
            params={"query":query,"rows":rows,"offset":fetched,"mailto":CROSSREF_EMAIL}
            if filt: params["filter"]=",".join(filt)
            items=json.loads(self.fetcher.get(url,params)).get("message",{}).get("items",[])
            if not items: break
            for it in items:
                title=it.get("title",[""])[0];abst=clean_text(it.get("abstract",""))
                if not PICO_PATTERN.search(title+" "+abst): continue
                found=[m.group(0) for m in PICO_PATTERN.finditer(title+" "+abst)]
                authors=[f"{a.get('family','')}, {a.get('given','')}" for a in it.get("author",[])]
                year=""; dp=it.get("issued",{}).get("date-parts",[])
                if dp and dp[0]: year=str(dp[0][0])
                rec={"Key":it.get("DOI"),"Item Type":it.get("type","journal-article"),"Title":title,"Abstract Note":abst,
                     "Author":"; ".join(authors),"Publication Title":(it.get("container-title") or [""])[0],
                     "Journal Abbreviation":(it.get("short-container-title") or [""])[0] if it.get("short-container-title") else "",
                     "ISSN":"; ".join(it.get("ISSN",[])),"Volume":it.get("volume",""),"Issue":it.get("issue",""),
                     "Pages":it.get("page",""),"Publication Year":year,"Date":"",
                     "Publisher":it.get("publisher",""),"Language":it.get("language",""),
                     "DOI":it.get("DOI",""),"Url":it.get("URL",""),"Meeting Name":it.get("event",{}).get("name",""),
                     "Conference Name":it.get("event",{}).get("name",""),
                     "Place":it.get("event",{}).get("location","") or it.get("publisher-location",""),
                     "Extra":"PICO_keywords_found: "+", ".join(found)}
                self.save_record(rec,[it.get("DOI")])
            fetched+=len(items)
            if len(items)<rows: break

    def finalize(self):
        if self.merge_report and self.merge_log:
            with open(MERGE_REPORT_FILE,"w") as f:
                f.write("Merge Report:\n")
                for line in self.merge_log: f.write(line+"\n")
            log.info("Merge report saved to %s", MERGE_REPORT_FILE)

# ---------------- Export ----------------
def export(recs):
    df=pd.DataFrame([{**zotero_template(),**r} for r in recs],columns=ZOTERO_HEADER)
    df.to_csv(CSV_OUTPUT,index=False,encoding="utf-8")
    df.to_excel(XLSX_OUTPUT,index=False,engine="openpyxl")
    with open(JSON_OUTPUT,"w",encoding="utf-8") as f: json.dump(recs,f,ensure_ascii=False,indent=2)
    log.info("Exported %d records",len(recs))

# ---------------- Run ----------------
def run(query,sources,limit,from_year,to_year,merge_report=False):
    store=Storage();fetcher=Fetcher();scraper=GeneralScraper(fetcher,store,merge_report)
    for src in sources: scraper.scrape(src,query,limit,from_year,to_year)
    recs=store.all();export(recs);scraper.finalize();store.close()

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--query",required=True)
    p.add_argument("--sources",default="pubmed,crossref")
    p.add_argument("--limit",type=int,default=20)
    p.add_argument("--from_year",type=int)
    p.add_argument("--to_year",type=int)
    p.add_argument("--years",type=int)
    p.add_argument("--merge-report",action="store_true",help="Generate merge report for duplicates")
    a=p.parse_args()
    fy,ty=a.from_year,a.to_year
    if a.years: ty=datetime.now().year;fy=ty-a.years+1
    run(a.query,[s.strip() for s in a.sources.split(",")],a.limit,fy,ty,a.merge_report)



'''

Above version is most suitable one cause it can toggle with version control in a sense if the crawl4ai versio is older it will adapt to it orelse if new one is available then will use that

Full crawl4ai mode (what you asked for):

Use crawl4ai WebCrawler for:

Scraping EuropePMC (when API fails or not enough metadata)

Scraping arXiv directly from HTML if API doesn’t give abstract

Below version is only for crawl4ai 0.7 version
'''
# This script requires crawl4ai version 0.7.4
# You can install it with: pip install "crawl4ai==0.7.4"
# import argparse
# import asyncio
# import json
# import logging
# import re
# from datetime import datetime
# from typing import List, Dict, Any

# import pandas as pd
# from crawl4ai import AsyncWebCrawler

# # ---------------- CONFIG ----------------
# CONTACT_EMAIL = "keertisubramanyasm@gmail.com"
# PUBMED_API_KEY = "YOUR_PUBMED_API_KEY"
# CROSSREF_EMAIL = CONTACT_EMAIL
# USER_AGENT = f"MultiSourceScraper/1.0 (+{CONTACT_EMAIL})"

# JSON_OUTPUT = "merged_results.json"
# CSV_OUTPUT = "merged_results.csv"
# XLSX_OUTPUT = "merged_results.xlsx"
# MERGE_REPORT_FILE = "merge_report.txt"

# logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# # ---------------- PICO FILTER ----------------
# PICO_KEYWORDS = {
#     "interventions": ["dexrazoxane", "beta-blocker", "ace inhibitor", "arb", "acei", "arni", "statin"],
#     "exposures": ["anthracycline", "doxorubicin", "epirubicin", "trastuzumab"],
#     "comparators": ["placebo", "usual care", "control"],
#     "study_designs": ["randomized", "rct", "cohort", "observational"]
# }
# ALL_PICO_WORDS = {w for v in PICO_KEYWORDS.values() for w in v}
# PICO_PATTERN = re.compile(r'\b(' + '|'.join(map(re.escape, ALL_PICO_WORDS)) + r')\b', re.IGNORECASE)

# # ---------------- ZOTERO TEMPLATE ----------------
# ZOTERO_HEADER = ["Key", "Item Type", "Publication Year", "Author", "Title",
#                  "Publication Title", "DOI", "Url", "Abstract Note", "Date",
#                  "Date Added", "Extra", "Source"]

# def zotero_template() -> Dict[str, Any]:
#     return {key: "" for key in ZOTERO_HEADER}

# # ---------------- DATA MANAGER ----------------
# class DataManager:
#     def __init__(self):
#         self._records: Dict[str, Dict] = {}
#         self._merge_log: List[str] = []

#     def _get_identifier(self, rec: Dict) -> str:
#         doi = (rec.get("DOI") or "").strip().lower()
#         if doi: return doi
#         key = (rec.get("Key") or "").strip()
#         if key: return key
#         return re.sub(r"[^a-z0-9]+", "", (rec.get("Title") or "").lower())

#     def add_records(self, records: List[Dict]):
#         for rec in records:
#             identifier = self._get_identifier(rec)
#             if not identifier: continue
#             if identifier not in self._records:
#                 self._records[identifier] = rec
#             else:
#                 self._merge_log.append(f"Duplicate merged: {identifier} (source: {rec.get('Source')})")

#     def get_clean_results(self) -> List[Dict]:
#         return list(self._records.values())

#     def write_merge_report(self):
#         if not self._merge_log:
#             logging.info("No duplicates found to report.")
#             return
#         with open(MERGE_REPORT_FILE, "w", encoding="utf-8") as f:
#             f.write("Merge Report:\n")
#             for line in self._merge_log: f.write(line + "\n")
#         logging.info(f"Merge report saved to {MERGE_REPORT_FILE}")

# # ---------------- EXPORT ----------------
# def export_results(records: List[Dict]):
#     if not records:
#         logging.warning("No records to export.")
#         return
#     df = pd.DataFrame(records, columns=ZOTERO_HEADER)
#     df.to_csv(CSV_OUTPUT, index=False, encoding="utf-8")
#     df.to_excel(XLSX_OUTPUT, index=False, engine="openpyxl")
#     with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
#         json.dump(records, f, indent=2, ensure_ascii=False)
#     logging.info(f"Saved {len(records)} records to JSON, CSV, XLSX")

# # ---------------- SCRAPERS ----------------
# class PubMedScraper:
#     SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
#     FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

#     @staticmethod
#     async def scrape(crawler: AsyncWebCrawler, query: str, from_year: int, to_year: int, limit: int, apply_pico: bool):
#         logging.info("Starting PubMed scrape...")
#         search_params = {
#             "db": "pubmed",
#             "term": query,
#             "retmax": limit,
#             "retmode": "json",
#             "datetype": "pdat",
#             "mindate": f"{from_year}/01/01",
#             "maxdate": f"{to_year}/12/31",
#             "api_key": PUBMED_API_KEY
#         }
#         search_result = await crawler.arun(PubMedScraper.SEARCH_URL, params=search_params, use_browser=False)
#         if not search_result.success:
#             logging.error("PubMed search failed.")
#             return []

#         data = json.loads(search_result.model_dump_json())
#         pmids = data.get("esearchresult", {}).get("idlist", [])
#         if not pmids:
#             logging.warning("PubMed returned no results.")
#             return []

#         fetch_params = {"db":"pubmed","id":",".join(pmids),"retmode":"xml","api_key":PUBMED_API_KEY}
#         fetch_result = await crawler.arun(PubMedScraper.FETCH_URL, params=fetch_params, use_browser=False)
#         if not fetch_result.success:
#             logging.error("PubMed fetch failed.")
#             return []

#         results = []
#         import xml.etree.ElementTree as ET
#         root = ET.fromstring(fetch_result.model_dump_json())
#         for article in root.findall(".//PubmedArticle"):
#             title = article.findtext(".//ArticleTitle","")
#             abstract = " ".join([n.text for n in article.findall(".//Abstract/AbstractText") if n.text])
#             if apply_pico and not set(PICO_PATTERN.findall(title + " " + abstract)):
#                 continue
#             pmid = article.findtext(".//PMID","")
#             authors = [f"{a.findtext('LastName','')}, {a.findtext('ForeName','')}" for a in article.findall(".//Author") if a.findtext("LastName")]
#             pub_year = article.findtext(".//PubDate/Year","")
#             record = zotero_template()
#             record.update({
#                 "Key": f"PMID:{pmid}", "Item Type": "journalArticle", "Publication Year": pub_year,
#                 "Author": "; ".join(authors), "Title": title, "Publication Title": article.findtext(".//Journal/Title",""),
#                 "DOI": "", "Url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "Abstract Note": abstract,
#                 "Date Added": datetime.now().isoformat(), "Extra": "", "Source":"PubMed"
#             })
#             results.append(record)
#         logging.info(f"PubMed scrape done. Articles found: {len(results)}")
#         return results

# class CrossRefScraper:
#     BASE_URL = "https://api.crossref.org/works"

#     @staticmethod
#     async def scrape(crawler: AsyncWebCrawler, query: str, from_year: int, to_year: int, limit: int, apply_pico: bool):
#         logging.info("Starting CrossRef scrape...")
#         params = {"query": query,
#                   "filter": f"from-pub-date:{from_year}-01-01,until-pub-date:{to_year}-12-31",
#                   "rows": limit, "mailto": CROSSREF_EMAIL}
#         crawl_result = await crawler.arun(CrossRefScraper.BASE_URL, params=params, use_browser=False)
#         if not crawl_result.success:
#             logging.error("CrossRef request failed.")
#             return []

#         data = json.loads(crawl_result.model_dump_json())
#         items = data.get("message", {}).get("items", [])
#         results = []
#         for it in items:
#             title = " ".join(it.get("title",[]))
#             abstract = it.get("abstract","")
#             if apply_pico and not set(PICO_PATTERN.findall(title + " " + abstract)):
#                 continue
#             doi = it.get("DOI","")
#             authors = [f"{a.get('family','')}, {a.get('given','')}" for a in it.get("author",[])]
#             year = it.get("issued", {}).get("date-parts", [[None]])[0][0]
#             record = zotero_template()
#             record.update({
#                 "Key": doi, "Item Type": it.get("type","journal-article"),
#                 "Publication Year": year, "Author": "; ".join(authors),
#                 "Title": title, "Publication Title": " ".join(it.get("container-title",[])),
#                 "DOI": doi, "Url": it.get("URL",""), "Abstract Note": abstract,
#                 "Date Added": datetime.now().isoformat(), "Extra": "", "Source":"CrossRef"
#             })
#             results.append(record)
#         logging.info(f"CrossRef scrape done. Articles found: {len(results)}")
#         return results

# # ---------------- JS-HEAVY / ANTI-BOT SCRAPER ----------------
# class DynamicScraper:
#     @staticmethod
#     async def scrape(crawler: AsyncWebCrawler, url: str, selector_title: str, selector_abstract: str, limit: int = 10):
#         logging.info(f"Starting JS-heavy scrape: {url}")
#         crawl_result = await crawler.arun(url, use_browser=True)
#         if not crawl_result.success:
#             logging.error(f"Dynamic page fetch failed: {url}")
#             return []

#         html = crawl_result.html or ""
#         import bs4
#         soup = bs4.BeautifulSoup(html, "html.parser")
#         articles = soup.select(selector_title)[:limit]
#         results = []
#         for idx, el in enumerate(articles):
#             title = el.get_text(strip=True)
#             abstract_el = el.find_next_sibling() if el else None
#             abstract = abstract_el.get_text(strip=True) if abstract_el else ""
#             record = zotero_template()
#             record.update({
#                 "Key": f"DYN:{idx}", "Item Type": "journalArticle", "Title": title, "Abstract Note": abstract,
#                 "Date Added": datetime.now().isoformat(), "Source": "DynamicSite"
#             })
#             results.append(record)
#         logging.info(f"Dynamic scrape done. Articles found: {len(results)}")
#         return results

# # ---------------- MAIN ----------------
# async def main():
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--query", required=True)
#     parser.add_argument("--from-year", type=int, default=datetime.now().year-5)
#     parser.add_argument("--to-year", type=int, default=datetime.now().year)
#     parser.add_argument("--limit", type=int, default=20)
#     parser.add_argument("--merge-report", action="store_true")
#     parser.add_argument("--sources", default="pubmed,crossref,dynamic")
#     parser.add_argument("--dynamic-url", type=str, help="URL for JS-heavy site")
#     parser.add_argument("--dynamic-title-selector", type=str, help="CSS selector for title")
#     parser.add_argument("--dynamic-abstract-selector", type=str, help="CSS selector for abstract")
#     parser.add_argument("--no-pico-filter", action="store_true")
#     args = parser.parse_args()

#     apply_pico = not args.no_pico_filter
#     source_map = {"pubmed": PubMedScraper, "crossref": CrossRefScraper, "dynamic": DynamicScraper}

#     data_manager = DataManager()
#     async with AsyncWebCrawler() as crawler:
#         tasks = []
#         for src in [s.strip().lower() for s in args.sources.split(",")]:
#             if src in ["pubmed","crossref"]:
#                 tasks.append(source_map[src].scrape(crawler, args.query, args.from_year, args.to_year, args.limit, apply_pico))
#             elif src == "dynamic" and args.dynamic_url:
#                 tasks.append(source_map[src].scrape(crawler, args.dynamic_url, args.dynamic_title_selector, args.dynamic_abstract_selector, args.limit))
#             else:
#                 logging.warning(f"Unknown or misconfigured source: {src}")

#         source_results = await asyncio.gather(*tasks)
#         for res in source_results:
#             data_manager.add_records(res)

#     final_records = data_manager.get_clean_results()
#     export_results(final_records)
#     if args.merge_report:
#         data_manager.write_merge_report()
#     logging.info("Scraping complete.")

# if __name__ == "__main__":
#     asyncio.run(main())
