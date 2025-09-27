# Multi-Source Scientific Literature Scraper

This project provides a Python script to scrape and aggregate scientific literature from multiple sources. It prioritizes official APIs for speed and reliability, de-duplicates results, and can export the final dataset into **JSON**, **CSV**, or **Excel** files.

---

## Features ✨

-   **Multi-Source Aggregation**: Gathers data from PubMed, ClinicalTrials.gov, CrossRef, and the WHO ICTRP.
-   **API-First Approach**: Uses fast and reliable APIs, reducing script breakage.
-   **De-duplication**: Removes duplicate entries based on unique identifiers (PMID, NCT ID, DOI, etc.).
-   **Flexible Export**: Save your data in the format you need: JSON, CSV, or Excel.
-   **Customizable via Command Line**: Easily change the search query, result limit, and output format without editing code.

---

## Setup and Installation

### 1. Prerequisites

-   Python 3.7+
-   Google Chrome browser installed.

### 2. Create a Virtual Environment (Recommended)

```bash
# On macOS/Linux
python3 -m venv venv
source venv/bin/activate

# On Windows
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install Required Libraries

This version requires `pandas` for data handling and `openpyxl` for Excel support.

```bash
pip install requests selenium webdriver-manager pandas openpyxl
```

### 4. Configure Your Email for APIs

Open the script (`main_scraper_exportable.py`) and change the placeholder email to your own. This is a courtesy for using the NCBI and CrossRef APIs.

```python
NCBI_EMAIL = "your.email@example.com"
```

---

## How to Run the Scraper 🏃‍♂️

You can now control the scraper directly from your terminal using command-line arguments.

### Basic Usage (uses default settings)

This will search for "large language models in medicine", get 10 results per source, and save the output as `scraped_data.json`.

```bash
python main_scraper_exportable.py
```

### Specify Output Format

Use the `--format` flag to choose between `json`, `csv`, or `excel`.

```bash
# Save output as a CSV file
python main_scraper_exportable.py --format csv

# Save output as an Excel file
python main_scraper_exportable.py --format excel
```

### Specify Query and Limit

Use the `--query` and `--limit` flags to customize your search.

```bash
python main_scraper_exportable.py --query "obesity and gut microbiome" --limit 25 --format excel
```

---

## Output Files 📁

The script will generate one of the following files in the same directory, depending on your choice:

-   `scraped_data.json`
-   `scraped_data.csv`
-   `scraped_data.xlsx`


The CSV and Excel files will contain the scraped data in a clean, tabular format, ready for analysis.