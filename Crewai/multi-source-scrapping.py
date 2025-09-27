import os
import json
import requests
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai_tools import BaseTool
from langchain_openai import ChatOpenAI

# Load environment variables from .env file
load_dotenv()

# ==============================================================================
#  sección 1: Definiciones de herramientas personalizadas (anteriormente en tools.py)
# ==============================================================================

# --- Configuración de raspado educado ---
# Identifique su bot con un User-Agent claro.
# Reemplace con su correo electrónico real para fines de contacto.
HEADERS = {
    'User-Agent': 'CrewAI-Biomedical-Scraper/1.0 (mailto:your-email@example.com)',
    'From': 'your-email@example.com'
}

# --- Definiciones de herramientas ---

class PubMedSearchTool(BaseTool):
    name: str = "PubMed Search Tool (NCBI API)"
    description: str = "Searches PubMed for a given query using the NCBI E-utilities API and returns article details in JSON format."

    def _run(self, query: str) -> str:
        """
        Uses NCBI E-utilities API to search PubMed. This is the official and preferred method.
        """
        try:
            # Step 1: Search for article IDs (PMIDs)
            search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            search_params = {
                "db": "pubmed",
                "term": query,
                "retmax": 15,  # Limit the number of results
                "retmode": "json",
                "api_key": os.getenv("NCBI_API_KEY")
            }
            search_res = requests.get(search_url, params=search_params, headers=HEADERS)
            search_res.raise_for_status()
            pmids = search_res.json().get("esearchresult", {}).get("idlist", [])

            if not pmids:
                return "[]"

            # Step 2: Fetch summaries for the found PMIDs
            summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            summary_params = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "json",
                "api_key": os.getenv("NCBI_API_KEY")
            }
            summary_res = requests.get(summary_url, params=summary_params, headers=HEADERS)
            summary_res.raise_for_status()
            results = summary_res.json().get("result", {})

            # Step 3: Format the results
            articles = []
            for pmid in pmids:
                article_data = results.get(pmid)
                if article_data:
                    articles.append({
                        "source": "PubMed",
                        "pmid": pmid,
                        "doi": next((item['value'] for item in article_data.get('articleids', []) if item['idtype'] == 'doi'), None),
                        "title": article_data.get("title", ""),
                        "authors": [author['name'] for author in article_data.get("authors", [])],
                        "journal": article_data.get("fulljournalname", ""),
                        "pub_date": article_data.get("pubdate", ""),
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                    })
            return json.dumps(articles, indent=2)
        except requests.exceptions.RequestException as e:
            return f"Error communicating with PubMed API: {e}"
        except Exception as e:
            return f"An unexpected error occurred during PubMed search: {e}"


class ClinicalTrialsSearchTool(BaseTool):
    name: str = "ClinicalTrials.gov Search Tool (API)"
    description: str = "Searches ClinicalTrials.gov for a given query using their official API (v2) and returns trial details."

    def _run(self, query: str) -> str:
        """
        Uses the official ClinicalTrials.gov API v2.
        """
        try:
            base_url = "https://clinicaltrials.gov/api/v2/studies"
            params = {
                "query.term": query,
                "pageSize": 15,
                "format": "json"
            }
            response = requests.get(base_url, params=params, headers=HEADERS)
            response.raise_for_status()
            data = response.json().get('studies', [])

            trials = []
            for item in data:
                protocol = item.get('protocolSection', {})
                id_module = protocol.get('identificationModule', {})
                status_module = protocol.get('statusModule', {})

                trials.append({
                    "source": "ClinicalTrials.gov",
                    "trial_id": id_module.get('nctId'),
                    "title": id_module.get('briefTitle'),
                    "status": status_module.get('overallStatus'),
                    "conditions": [cond for cond in protocol.get('conditionsModule', {}).get('conditions', [])],
                    "url": f"https://clinicaltrials.gov/study/{id_module.get('nctId')}"
                })
            return json.dumps(trials, indent=2)
        except requests.exceptions.RequestException as e:
            return f"Error communicating with ClinicalTrials.gov API: {e}"
        except Exception as e:
            return f"An unexpected error occurred during ClinicalTrials.gov search: {e}"


class CrossRefSearchTool(BaseTool):
    name: str = "CrossRef Search Tool"
    description: str = "Searches CrossRef for publications using its API, useful for finding DOIs and conference papers."

    def _run(self, query: str) -> str:
        """
        Uses the official CrossRef REST API.
        """
        try:
            base_url = "https://api.crossref.org/works"
            # The 'mailto' param is required by the CrossRef API for politeness
            params = {
                "query.bibliographic": query,
                "rows": 15,
                "mailto": HEADERS.get('From')
            }
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json().get('message', {}).get('items', [])

            articles = []
            for item in data:
                authors = [f"{author.get('given', '')} {author.get('family', '')}".strip() for author in item.get('author', [])]
                articles.append({
                    "source": "CrossRef",
                    "doi": item.get('DOI'),
                    "title": ''.join(item.get('title', [])),
                    "authors": authors,
                    "publisher": item.get('publisher'),
                    "type": item.get('type'),
                    "url": item.get('URL')
                })
            return json.dumps(articles, indent=2)
        except requests.exceptions.RequestException as e:
            return f"Error communicating with CrossRef API: {e}"
        except Exception as e:
            return f"An unexpected error occurred during CrossRef search: {e}"

# --- Instanciar herramientas para su uso ---
pubmed_tool = PubMedSearchTool()
clinicaltrials_tool = ClinicalTrialsSearchTool()
crossref_tool = CrossRefSearchTool()


# ==============================================================================
# sección 2: Orquestación principal de la tripulación (anteriormente en main.py)
# ==============================================================================

# --- Configuración ---
SEARCH_QUERY = "large language models in clinical diagnosis"
LLM = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)

# --- Definiciones de agentes ---

# Agente para buscar en PubMed
pubmed_researcher = Agent(
    role="PubMed Medical Research Specialist",
    goal=f"Search PubMed for the most relevant articles related to '{SEARCH_QUERY}'.",
    backstory="An expert in navigating the NCBI database to find seminal and recent medical research papers.",
    tools=[pubmed_tool],
    llm=LLM,
    verbose=False,
    allow_delegation=False,
)

# Agente para buscar en ClinicalTrials.gov
clinical_trial_researcher = Agent(
    role="Clinical Trial Information Retriever",
    goal=f"Find relevant clinical trials on ClinicalTrials.gov for the query '{SEARCH_QUERY}'.",
    backstory="A specialist in clinical trial databases, skilled at identifying ongoing and completed studies.",
    tools=[clinicaltrials_tool],
    llm=LLM,
    verbose=False,
    allow_delegation=False,
)

# Agente para buscar en CrossRef
crossref_researcher = Agent(
    role="Academic Publication Cross-Referencer",
    goal=f"Use CrossRef to find publications, conference papers, and pre-prints about '{SEARCH_QUERY}'.",
    backstory="A meticulous librarian who excels at using the CrossRef database to uncover a wide range of academic works.",
    tools=[crossref_tool],
    llm=LLM,
    verbose=False,
    allow_delegation=False,
)

# Agente para consolidar y desduplicar resultados
data_consolidator = Agent(
    role="Data Integration and Validation Expert",
    goal="Combine research data from all sources, eliminate duplicates, and format the final result as a clean JSON array.",
    backstory=(
        "You are an expert data analyst. Your primary skill is to merge datasets from various sources, "
        "intelligently identify and remove duplicate entries based on unique identifiers, and present "
        "the final, clean data in a structured format."
    ),
    llm=LLM,
    verbose=True,
    allow_delegation=False,
)

# --- Definiciones de tareas ---

task_pubmed = Task(
    description=f"Conduct a thorough search on PubMed for the query: '{SEARCH_QUERY}'. Return the raw JSON output from the tool.",
    expected_output="A JSON string containing a list of articles found on PubMed.",
    agent=pubmed_researcher
)

task_clinicaltrials = Task(
    description=f"Conduct a search on ClinicalTrials.gov for the query: '{SEARCH_QUERY}'. Return the raw JSON output from the tool.",
    expected_output="A JSON string containing a list of clinical trials.",
    agent=clinical_trial_researcher
)

task_crossref = Task(
    description=f"Conduct a search on CrossRef for the query: '{SEARCH_QUERY}'. Return the raw JSON output from the tool.",
    expected_output="A JSON string containing a list of publications from CrossRef.",
    agent=crossref_researcher
)

# La tarea de consolidación depende de los resultados de las tareas anteriores.
task_consolidate = Task(
    description=(
        "Review the JSON outputs from the PubMed, ClinicalTrials.gov, and CrossRef searches. Your job is to:\n"
        "1. Combine all entries from the different sources into a single list.\n"
        "2. Identify and remove duplicate entries. A duplicate is an entry that refers to the same publication or trial.\n"
        "3. Prioritize unique identifiers for de-duplication: use DOI first, then PMID, then Trial ID. If none are available, use a normalized version of the title to check for duplicates.\n"
        "4. Ensure the final output is a single, valid JSON array of unique objects. Do NOT include any explanations, just the JSON."
    ),
    expected_output="A single, clean, de-duplicated JSON array containing the combined results.",
    agent=data_consolidator,
    context=[task_pubmed, task_clinicaltrials, task_crossref]
)

# --- Definición de tripulación ---
research_crew = Crew(
    agents=[pubmed_researcher, clinical_trial_researcher, crossref_researcher, data_consolidator],
    tasks=[task_pubmed, task_clinicaltrials, task_crossref, task_consolidate],
    process=Process.sequential,
    verbose=2,
)

# --- Ejecutar la tripulación ---
if __name__ == "__main__":
    print(f"🚀 Starting research crew for query: '{SEARCH_QUERY}'")
    result = research_crew.kickoff()

    print("\n\n✅ Crew execution finished. Final De-duplicated Results:")
    
    # Intenta analizar e imprimir el resultado final en JSON de forma agradable
    try:
        final_data = json.loads(result)
        print(json.dumps(final_data, indent=2, ensure_ascii=False))
        
        # Guardar en un archivo
        output_filename = "consolidated_results.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
        print(f"\n📄 Results saved to {output_filename}")

    except json.JSONDecodeError:
        print("\nCould not parse the final output as JSON. Here is the raw output:")
        print(result)