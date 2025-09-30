# Multi-Source Academic Scraper

This project provides a polite, responsible, and legal way to scrape metadata from multiple academic and clinical trial sources. It consolidates results into a unified dataset, removes duplicates, and saves them in **SQLite, JSON, CSV, and Excel formats**.

## Features
- Sources:
  - PubMed (via NCBI E-utilities API)
  - CrossRef API
  - ClinicalTrials.gov API
  - WHO ICTRP (via crawl4ai)
  - Journal / Conference sites (via crawl4ai)
- Deduplication using identifiers (PMID, DOI, NCT ID) and fuzzy title matching.
- Responsible scraping with custom `User-Agent`, retry logic, and rate limiting.
- Outputs stored in:
  - `scraper_results.db` (SQLite database)
  - `scraper_results.json` (JSON file)
  - `scraper_results.csv` (CSV file)
  - `scraper_results.xlsx` (Excel file)

## Requirements
- Python 3.9+
- Install dependencies:
  ```bash
  pip install requests crawl4ai openpyxl pandas
  ```

## How to Run
1. Clone or download this repository.
2. Run the script with a search query:
   ```bash
   python multi_source_scraper.py "large language models"
   ```
3. The scraper will fetch results from all supported sources.
4. After completion, check the output files:
   - `scraper_results.json` → structured JSON data
   - `scraper_results.csv` → CSV version for spreadsheets
   - `scraper_results.xlsx` → Excel workbook
   - `scraper_results.db` → SQLite database for advanced queries

## Legal & Ethical Use
- Use only for academic or research purposes.
- Respect each source’s terms of service.
- Avoid high-frequency queries. This script uses rate-limiting and retries to stay polite.
- Provide a valid contact email in the User-Agent string.

## Extending the Scraper
- Add new sources by writing additional API clients or crawl4ai parsers.
- Improve deduplication by extending the fuzzy match rules.
- Customize export formats as needed.

## Example Output (JSON snippet)
```json
[
  {
    "source": "PubMed",
    "id": "12345678",
    "title": "An overview of large language models",
    "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
    "authors": "Smith J, Doe P",
    "journal": "Journal of AI Research, 2023"
  }
]
```
PUBMED_API_KEY = "c2f307fc5acc4197325e5d9234ff271aa608"