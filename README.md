## HealthCare Technical Workflow Project
This repository contains a specialized data pipeline developed for the CardioProtect initiative. The project focuses on the automated retrieval and structured extraction of medical research data concerning cardioprotective agents, utilizing both web scraping and Local LLMs (Ollama).

🚀 Project Overview
The primary goal of this workflow is to bridge the gap between unstructured medical publications and actionable data. By combining high-precision scraping with AI-driven extraction, the project identifies human-based research (RCTs and observational studies) related to anthracycline-induced cardiotoxicity and protective interventions.

📂 Repository Structure
1. Web Scraper Module (/WebScraper)
This module contains the core logic for multi-source data acquisition.

Sources: PubMed (E-Utils API) and CrossRef.

Logic: Implements a Strict PICO (Population, Intervention, Comparison, Outcome) filtering system.

Key Features:

Automated API-based extraction (avoiding brittle HTML scraping).

Built-in human-only filters to exclude animal or in-vitro studies.

Multi-format export (JSON, CSV, XLSX) and SQLite database logging.

2. Clinical Extraction (/CardioProtect_Agent_Window)
This section handles the "Reasoning" layer of the project, focusing on PDF parsing and data structuring.

Initial Tech Stack: Ollama (Local LLM), Python.

Technical Challenge: During development, the Ollama-based automated extraction encountered performance limitations and consistency issues with complex medical PDF structures.

Hybrid Resolution: To ensure 100% data integrity for the clinical template, a Manual Extraction process was implemented. Each PDF was parsed and verified manually to extract specific entities such as:

Drug dosages and delivery methods.

Patient demographics and baseline cardiac function.

Cardioprotective outcomes (LVEF changes, biomarker levels).

🛠️ Technical Implementation
Data Acquisition
The scraper uses the requests library to interface with NCBI and CrossRef APIs. It includes robust error handling, rate limiting (to respect API guidelines), and a normalization engine to ensure titles and DOIs are unique.

PICO Filtering
The system uses regex-based patterns to validate:

Exposures: Anthracyclines (Doxorubicin, Epirubicin, etc.).

Interventions: Beta-blockers, ACE inhibitors, Statins, and SGLT2 inhibitors.

Population: Strict inclusion of "Human/Adult" terms while excluding animal-based terminology.

🚧 Current Status & Future Scope
This project was developed during a professional internship. While the data acquisition and extraction phases are complete, the following modules remain as future areas of development:

Exploratory Data Analysis (EDA): Visualizing trends in cardioprotective research over the last decade.

Predictive Analysis: Developing models to predict the efficacy of specific agents based on the manually validated clinical parameters.

👨‍💻 Author
Keerti Subramanya
Data Science Intern
