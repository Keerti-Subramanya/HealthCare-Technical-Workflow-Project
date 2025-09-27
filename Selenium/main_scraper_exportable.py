import json
import re
import requests
import time
import argparse # To handle command-line arguments
import pandas as pd # To handle data and export to CSV/Excel
from urllib.parse import quote_plus
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Configuration ---
NCBI_EMAIL = "your.email@example.com"
HEADERS = {
    'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- API and Base URLs ---
PUBMED_API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
CLINICAL_TRIALS_API_BASE = "https://clinicaltrials.gov/api/v2/"
CROSSREF_API_BASE = "https://api.crossref.org/"
WHO_ICTRP_BASE = "https://trialsearch.who.int/"

# --- Helper Function ---
def get_chrome_driver():
    """Initializes a headless Chrome WebDriver."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,1024")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(45)
    return driver

# --- Data Saving Function ---
def save_data(data, file_format):
    """Saves the data to the specified file format."""
    if not data:
        print("No data to save.")
        return

    # Convert the list of dictionaries to a pandas DataFrame for easy export
    df = pd.DataFrame(data)
    filename = "scraped_data"
    
    if file_format == 'json':
        output_path = f"{filename}.json"
        df.to_json(output_path, orient='records', indent=2, force_ascii=False)
        print(f"✅ Data successfully saved to {output_path}")
    elif file_format == 'csv':
        output_path = f"{filename}.csv"
        # Use utf-8-sig encoding for better compatibility with Excel
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"✅ Data successfully saved to {output_path}")
    elif file_format == 'excel':
        output_path = f"{filename}.xlsx"
        df.to_excel(output_path, index=False)
        print(f"✅ Data successfully saved to {output_path}")
    else:
        print(f"❌ Error: Unsupported file format '{file_format}'")


# --- Scraper Functions (Unchanged from previous version) ---

def scrape_pubmed_api(query, limit=10):
    print(f"Scraping PubMed (API) for '{query}'...")
    results = []
    api_headers = {'User-Agent': f'MyScraper/1.0 ({NCBI_EMAIL})'}
    search_url = f"{PUBMED_API_BASE}esearch.fcgi?db=pubmed&term={quote_plus(query)}&retmax={limit}&sort=relevance&retmode=json"
    try:
        response = requests.get(search_url, headers=api_headers)
        response.raise_for_status()
        pmids = response.json()['esearchresult']['idlist']
        if not pmids: return []
        summary_url = f"{PUBMED_API_BASE}esummary.fcgi?db=pubmed&id={','.join(pmids)}&retmode=json"
        summary_response = requests.get(summary_url, headers=api_headers)
        summary_response.raise_for_status()
        summaries = summary_response.json()['result']
        for pmid in pmids:
            article = summaries[pmid]
            authors = ", ".join([author['name'] for author in article.get('authors', [])])
            results.append({"id": pmid, "source": "PubMed", "title": article.get('title', 'N/A'), "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "authors": authors, "journal_citation": f"{article.get('fulljournalname', '')}. {article.get('pubdate', '')}.", "year": article.get('pubdate', '').split(' ')[0] if article.get('pubdate') else None, "abstract": "N/A"})
    except Exception as e:
        print(f"Error fetching from PubMed API: {e}")
    print(f"Found {len(results)} results from PubMed.")
    return results

def scrape_clinical_trials_api(query, limit=10):
    print(f"Scraping ClinicalTrials.gov (API) for '{query}'...")
    results = []
    url = f"{CLINICAL_TRIALS_API_BASE}studies?query.term={quote_plus(query)}&pageSize={limit}"
    try:
        response = requests.get(url, headers=HEADERS); response.raise_for_status()
        data = response.json().get('studies', [])
        for study in data:
            proto = study.get('protocolSection', {}); ident = proto.get('identificationModule', {}); desc = proto.get('descriptionModule', {})
            results.append({"id": ident.get('nctId'), "source": "ClinicalTrials.gov", "title": ident.get('briefTitle'), "url": f"https://clinicaltrials.gov/study/{ident.get('nctId')}", "authors": study.get('protocolSection', {}).get('contactsLocationsModule', {}).get('centralContact', [{}])[0].get('name'), "journal_citation": None, "year": ident.get('studyFirstPostDateStruct', {}).get('date', '')[:4], "abstract": desc.get('briefSummary', 'N/A')})
    except Exception as e:
        print(f"Error fetching from ClinicalTrials.gov API: {e}")
    print(f"Found {len(results)} results from ClinicalTrials.gov.")
    return results

def scrape_crossref_api(query, limit=10):
    print(f"Scraping CrossRef (API) for '{query}'...")
    results = []
    url = f"{CROSSREF_API_BASE}works?query.bibliographic={quote_plus(query)}&rows={limit}&mailto={NCBI_EMAIL}"
    try:
        response = requests.get(url, headers=HEADERS); response.raise_for_status()
        items = response.json()['message']['items']
        for item in items:
            authors = ", ".join([f"{author.get('given', '')} {author.get('family', '')}".strip() for author in item.get('author', [])])
            year_parts = item.get('issued', {}).get('date-parts', [[None]])[0]; year = year_parts[0] if year_parts[0] else None
            results.append({"id": item.get('DOI'), "source": "CrossRef", "title": ''.join(item.get('title', [])), "url": item.get('URL'), "authors": authors, "journal_citation": ''.join(item.get('container-title', [])), "year": str(year) if year else None, "abstract": item.get('abstract', 'N/A').replace('<jats:p>', '').replace('</jats:p>', '')})
    except Exception as e:
        print(f"Error fetching from CrossRef API: {e}")
    print(f"Found {len(results)} results from CrossRef.")
    return results

def scrape_who_ictrp_selenium(query, limit=10):
    print(f"Scraping WHO ICTRP (Selenium) for '{query}'...")
    results = []
    url = f"{WHO_ICTRP_BASE}trial_search.aspx?searchtext={quote_plus(query)}"
    driver = get_chrome_driver()
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.results_details_box"))); time.sleep(2)
        cards = driver.find_elements(By.CSS_SELECTOR, "div.results_details_box")
        for card in cards[:limit]:
            try:
                title_el = card.find_element(By.CSS_SELECTOR, "a"); title = title_el.text.strip(); link = title_el.get_attribute("href")
                details = card.text; trial_id_match = re.search(r"Trial ID:\s*(\S+)", details); trial_id = trial_id_match.group(1) if trial_id_match else link
                results.append({"id": trial_id, "source": "WHO ICTRP", "title": title, "url": link, "authors": None, "journal_citation": None, "year": None, "abstract": "N/A"})
                time.sleep(0.5)
            except Exception: continue
    except Exception as e:
        print(f"An error occurred during WHO ICTRP scraping: {e}")
    finally:
        driver.quit()
    print(f"Found {len(results)} results from WHO ICTRP.")
    return results

# --- Main Execution ---
def main():
    """Main function to run all scrapers and combine results."""
    parser = argparse.ArgumentParser(description="Scrape scientific literature from multiple sources.")
    parser.add_argument("--query", type=str, default="large language models in medicine", help="The search query.")
    parser.add_argument("--limit", type=int, default=10, help="Max number of results per source.")
    parser.add_argument("--format", type=str, choices=['json', 'csv', 'excel'], default='json', help="Output file format.")
    args = parser.parse_args()
    
    # Run scrapers with a polite delay
    all_source_results = [
        scrape_pubmed_api(args.query, args.limit),
        scrape_clinical_trials_api(args.query, args.limit),
        scrape_crossref_api(args.query, args.limit),
        scrape_who_ictrp_selenium(args.query, args.limit)
    ]
    
    # Combine and de-duplicate results
    all_results = []
    processed_ids = set()
    for result_list in all_source_results:
        time.sleep(1) # Polite delay between processing sources
        for item in result_list:
            if item.get("id") and item["id"] not in processed_ids:
                all_results.append(item)
                processed_ids.add(item["id"])
    
    print(f"\n--- Total unique results found: {len(all_results)} ---")
    
    # Save the combined, de-duplicated data to the chosen format
    save_data(all_results, args.format)

if __name__ == "__main__":
    main()