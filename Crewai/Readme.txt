# Multi-Source Biomedical Literature Scraper using CrewAI

This project uses the CrewAI framework to intelligently search, gather, and de-duplicate biomedical and academic literature from multiple trusted sources. It's designed to be a "polite" scraper by prioritizing official APIs over web scraping.

## 🎯 What it Does

Given a search query (e.g., "large language models in clinical diagnosis"), this script will:
1.  **Search Multiple Sources**: Concurrently searches across:
    * **PubMed**: Via the official NCBI E-utilities API.
    * **ClinicalTrials.gov**: Via the official clinicaltrials.gov API v2.
    * **CrossRef**: Via their public REST API to find publications and DOIs.
2.  **Consolidate Data**: Gathers the results from all sources.
3.  **De-duplicate Results**: An intelligent agent analyzes the combined data to remove duplicate entries, prioritizing unique identifiers like DOIs, PMIDs, and Trial IDs.
4.  **Output Clean JSON**: The final, clean, and de-duplicated list of results is printed to the console and saved to `consolidated_results.json`.

## ✨ Key Features

* **API-First Approach**: Ensures reliable, fast, and respectful data collection.
* **Intelligent De-duplication**: Uses an LLM-powered agent to merge results and remove redundancies.
* **Extensible Framework**: Built with CrewAI, making it easy to add new data sources (e.g., a web scraper for the WHO ICTRP) as new agents and tasks.
* **Environment-Friendly**: Keeps API keys and sensitive information out of the code using a `.env` file.

## 🛠️ Setup and Installation

### Prerequisites
* Python 3.8+
* An OpenAI API Key

### Step-by-Step Instructions

1.  **Clone the Repository**
    ```bash
    git clone <your-repository-url>
    cd <your-repository-name>
    ```

2.  **Install Dependencies**
    It's recommended to use a virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```
    Then, install the required packages:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set Up Environment Variables**
    Create a file named `.env` in the project's root directory. Copy the contents of `.env.example` (if you have one) or create it from scratch:
    ```env
    # .env
    OPENAI_API_KEY="your-openai-api-key-here"
    ```
    Replace `"your-openai-api-key-here"` with your actual key.

## 🚀 How to Run the Code

1.  **Configure Your Search**
    Open the `main.py` file and change the `SEARCH_QUERY` variable to your desired topic:
    ```python
    # main.py
    SEARCH_QUERY = "your new research topic here"
    ```

2.  **Execute the Script**
    Run the main script from your terminal:
    ```bash
    python main.py
    ```

The script will start the CrewAI agents, and you will see the process logs in your terminal. Once completed, the final de-duplicated JSON will be printed and saved to `consolidated_results.json`.

## ⚖️ A Note on Polite Scraping

This project adheres to best practices for automated data collection:
* **APIs are Preferred**: We use official APIs wherever possible. This is the most robust and respectful method.
* **User-Agent Identification**: All API requests are sent with a `User-Agent` string that identifies the script, its purpose, and provides a contact email. Please change the placeholder email in `tools.py` to your own.
* **Respect `robots.txt`**: If you extend this project with web scraping tools (like for WHO ICTRP), always check and respect the `robots.txt` file of the target website.
* **No Commercial Use**: This tool is intended for educational and research purposes. Always comply with the Terms of Service of the data providers.