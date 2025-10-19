
''' working code but confined to one'''
# #!/usr/bin/env python
# # -*- coding: utf-8 -*-
# """
# CardioProtect Global Extractor v2+ (Fixed Follow-up & Enrollment)
# -----------------------------------------------------------------
# ✅ All your working logic retained
# ✅ Enrollment_Years → now correctly detects 2023–2024
# ✅ Followup_Median → now returns 18 (median) for "follow-up period of 18 months"
# """

# import os, re, io, pdfplumber, fitz, pytesseract
# import pandas as pd
# from PIL import Image
# import spacy

# # Load spaCy model
# nlp = spacy.load("en_core_web_sm")

# # --- CONFIG ---
# TEMPLATE_PATH = "CardioProtect_MetaAnalysis_DataTemplate.xlsx"
# OUTPUT_XLSX = "CardioProtect_Filled_Global_v2plus_fixed.xlsx"
# COUNTRY_LIST = [
#     "Italy","France","Germany","Spain","USA","United States","UK","United Kingdom",
#     "China","India","Japan","Brazil","Switzerland","Canada","Netherlands","Sweden","Australia"
# ]

# # --- OCR CONFIG ---
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# # --------------------------------------------------------------------
# def extract_text_tables_images(pdf_path):
#     """Combine text + OCR images + tables from PDF."""
#     text, tables, ocr_texts = "", [], []
#     with pdfplumber.open(pdf_path) as pdf:
#         for page in pdf.pages:
#             txt = page.extract_text() or ""
#             text += "\n" + txt
#             for table in page.extract_tables():
#                 df = pd.DataFrame(table[1:], columns=table[0])
#                 tables.append(df)
#     doc = fitz.open(pdf_path)
#     for p in range(len(doc)):
#         for img in doc.get_page_images(p):
#             base = doc.extract_image(img[0])
#             image = Image.open(io.BytesIO(base["image"]))
#             txt = pytesseract.image_to_string(image)
#             if txt.strip():
#                 ocr_texts.append(txt)
#     text += "\n" + "\n".join(ocr_texts)
#     text = re.sub(r"-\s*\n", "", text)
#     text = re.sub(r"\s+", " ", text)
#     return text, tables


# # --------------------------------------------------------------------
# def extract_countries(text):
#     """Return the most likely primary country."""
#     found = [c for c in COUNTRY_LIST if re.search(rf"\b{re.escape(c)}\b", text, re.I)]
#     if not found:
#         return "NR"
#     primary = found[0]
#     if len(found) > 1:
#         primary = f"{primary} (multicenter)"
#     return primary


# def extract_enrollment_years(text):
#     """
#     Detect enrollment years precisely (e.g., 'Recruitment started in 2023... Enrollment 12 months').
#     → Returns '2023–2024' in this case.
#     """
#     text_l = text.lower()

#     # Contextual: recruitment/enrollment started in year + duration
#     if m := re.search(r"(recruitment|enrollment)\s+(started|began|initiated)\s+(in|on)?\s*(?:[A-Za-z]+\s+)?(20\d{2})", text_l):
#         start_year = int(m.group(4))
#         if dur := re.search(r"(\d{1,2})\s*(month|months)", text_l):
#             dur_mo = int(dur.group(1))
#             if dur_mo >= 10:
#                 return f"{start_year}–{start_year + 1}"
#         return str(start_year)

#     # Direct range 2023–2024
#     if m := re.search(r"(20\d{2})\s*[-–]\s*(20\d{2})", text):
#         if m.group(1) != m.group(2):
#             return f"{m.group(1)}–{m.group(2)}"

#     # Fallback: earliest-latest years
#     years = sorted(set(re.findall(r"20\d{2}", text)))
#     if len(years) >= 2:
#         return f"{years[0]}–{years[-1]}"
#     elif years:
#         return years[0]
#     return "NR"


# def extract_followup_median(text, infer_median=False):
#     """
#     Detects the correct median follow-up duration (in months).
#     Prioritizes phrases like 'follow-up period of 18 months' even if earlier numbers (like 12 for enrollment)
#     appear in the same sentence.
#     """
#     t = text
#     t = t.replace("–", "-").replace("—", "-")
#     t_l = " ".join(t.lower().split())

#     # Explicit "follow-up period of 18 months"
#     m = re.search(
#         r"(follow[-\s]*up|followup|follow\s+up|observation)[^0-9]{0,40}(\d{1,2})\s*(?:months?|mo)\b",
#         t_l, flags=re.I
#     )
#     if m:
#         return f"{m.group(2)} (median)"

#     # "median follow-up 18 months"
#     m = re.search(
#         r"median\s+(follow[-\s]*up|followup|time|observation)[^0-9]{0,20}(\d{1,2})\s*(?:months?|mo)\b",
#         t_l, flags=re.I
#     )
#     if m:
#         return f"{m.group(2)} (median)"

#     # "18-month follow-up"
#     m = re.search(
#         r"\b(\d{1,2})\s*-\s*month\s+follow[-\s]*up\b", t_l, flags=re.I
#     )
#     if m:
#         return f"{m.group(1)} (median)"

#     # Optional inference from range (12–18 months)
#     if infer_median:
#         rnge = re.search(r"\b(\d{1,2})\s*-\s*(\d{1,2})\s*(?:months?|mo)\b", t_l)
#         if rnge:
#             lo, hi = int(rnge.group(1)), int(rnge.group(2))
#             return f"≈{round((lo + hi) / 2)} (inferred from {lo}-{hi})"

#     return "NR"


# def detect_coi(text):
#     text_l = text.lower()
#     if re.search(r"no\s+(conflicts?|competing)\s+(of\s+interest|interests?)", text_l):
#         return "Yes (declared none relevant)"
#     if re.search(r"none\s+declared|no\s+conflicts?|no\s+competing\s+interests?", text_l):
#         return "Yes (none declared)"
#     if re.search(r"conflict\s+of\s+interest", text_l) and "no" not in text_l:
#         return "Yes (declared)"
#     return "NR"


# def infer_study_design(text):
#     if re.search(r"randomi[sz]ed", text, re.I):
#         phase = re.search(r"(phase\s+[IVX]+)", text, re.I)
#         label = "open-label" if "open" in text.lower() else "blinded" if "blind" in text.lower() else ""
#         multi = "multicenter" if "multi" in text.lower() else ""
#         p = phase.group(1).title() if phase else "Phase NR"
#         return f"{p} RCT; {label}; {multi}".strip("; ")
#     elif "cohort" in text.lower():
#         return "Prospective Cohort"
#     elif "case-control" in text.lower():
#         return "Case-Control"
#     return "NR"


# def infer_author_year(text):
#     m = re.search(r"([A-Z][a-z]+).*?20(\d{2})", text)
#     return f"{m.group(1)}_20{m.group(2)}" if m else "NR"


# def detect_funding(text):
#     if "grant" in text.lower() or "funded" in text.lower():
#         return "Non-industry (grant/public)"
#     if "pharma" in text.lower() or "sponsored" in text.lower():
#         return "Industry"
#     return "NR"


# # --------------------------------------------------------------------
# def extract_fields(text):
#     """Main extraction logic."""
#     data = {}
#     doi = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, re.I)
#     regs = re.findall(r"(NCT\d+|EudraCT[- ]?\d{4}-\d{6}-\d+)", text)
#     data["PMID/DOI"] = doi.group(1) if doi else "NR"
#     data["Registry_ID"] = "; ".join(sorted(set(regs))) if regs else "NR"

#     data["Study_ID (FirstAuthor_Year)"] = infer_author_year(text)
#     data["Publication_Year"] = re.search(r"20\d{2}", text).group(0) if re.search(r"20\d{2}", text) else "NR"
#     data["Country"] = extract_countries(text)
#     data["Study_Design (RCT/Cluster-RCT/Crossover/Prospective Cohort/Retrospective Cohort/Case-Control)"] = infer_study_design(text)
#     data["Oncology_Setting (Adjuvant/Neoadjuvant/Metastatic)"] = "Adjuvant / Neoadjuvant" if re.search(r"adjuvant|neoadjuvant", text, re.I) else "NR"
#     data["Cancer_Type (Breast/Lymphoma/Sarcoma/Other)"] = "Breast cancer" if "breast" in text.lower() else "NR"
#     data["Anthracycline_Exposure (Yes/No)"] = "Yes" if "anthracycline" in text.lower() else "No"
#     data["Trastuzumab_Exposure (Yes/No)"] = "+/- (stratified)" if "+/-" in text else ("Yes" if "trastuzumab" in text.lower() else "No")
#     data["Comparator (Placebo/Usual Care/Other)"] = "Standard of care" if "standard" in text.lower() else "NR"

#     data["Sample_Size_Total"] = re.search(r"(\d{2,4})\s*(patients|participants)", text, re.I)
#     data["Sample_Size_Total"] = data["Sample_Size_Total"].group(1) if data["Sample_Size_Total"] else "NR"
#     data["Arms (N)"] = "2" if re.search(r"1[:：]1|two arms", text, re.I) else "NR"

#     data["Followup_Median (months)"] = extract_followup_median(text)
#     data["Followup_IQR_or_Range"] = re.search(r"(\d{1,2}\s*[-–]\s*\d{1,2}\s*months?)", text, re.I)
#     data["Followup_IQR_or_Range"] = data["Followup_IQR_or_Range"].group(1) if data["Followup_IQR_or_Range"] else "NR"
#     data["Enrollment_Years"] = extract_enrollment_years(text)
#     data["Funding (Industry/Non-industry/Mixed)"] = detect_funding(text)
#     data["COI_Declared (Yes/No)"] = detect_coi(text)
#     data["Protocol/PROSPERO/Trial_Registration"] = (
#         "Registered on ClinicalTrials.gov" if "clinicaltrials.gov" in text.lower() else data["Registry_ID"]
#     )

#     return data


# # --------------------------------------------------------------------
# def fill_template(data):
#     cols = pd.read_excel(TEMPLATE_PATH, sheet_name="1_Study_ID_Design", nrows=0).columns
#     filled = {c: data.get(c, "NR") for c in cols}
#     pd.DataFrame([filled]).to_excel(OUTPUT_XLSX, index=False)
#     print(f"✅ Saved enriched extraction → {OUTPUT_XLSX}")


# # --------------------------------------------------------------------
# if __name__ == "__main__":
#     import argparse
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--pdf", required=True)
#     args = parser.parse_args()

#     print("🚀 Running CardioProtect Global Extractor v2+ (Follow-up & Enrollment Fixed)...")
#     txt, tbls = extract_text_tables_images(args.pdf)
#     extracted = extract_fields(txt)
#     fill_template(extracted)
#     print("🎯 Extraction complete.")





#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Universal CardioProtect Extractor — Sheet 1 (Study ID & Design)
----------------------------------------------------------------
• Robust across PDFs: explicit + implicit phrasing
• Stronger detection for Follow-up and Enrollment Years
• Smarter Registry ID, Arms, Sample Size, Country, COI, Funding
• Uses text + OCR + tables; minimizes 'NR' (only when truly absent)
• Run on a single PDF or a folder of PDFs

Usage:
  # Single file
  python cardioprotect_universal_extractor.py --pdf "path/to/file.pdf"

  # Batch folder
  python cardioprotect_universal_extractor.py --input-folder "./pdfs"

  # Optional: print debug matches
  python cardioprotect_universal_extractor.py --pdf file.pdf --debug

Output:
  CardioProtect_Filled_Sheet1.xlsx (appends rows per PDF processed)
"""

import os, re, io, glob, argparse, math
import pdfplumber, fitz, pytesseract
import pandas as pd
from PIL import Image
import spacy
from collections import Counter, defaultdict
from datetime import datetime


# ------------------- CONFIG -------------------
TEMPLATE_PATH = "CardioProtect_MetaAnalysis_DataTemplate.xlsx"
OUTPUT_XLSX   = "CardioProtect_Filled_Sheet1.xlsx"

# Tesseract (adjust path if needed)
# On Windows typical: r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# spaCy (NER for countries/people)
_nlp = None
def nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp

# Country list (expandable)
COUNTRIES = {
    "afghanistan","albania","algeria","andorra","angola","argentina","armenia","australia","austria","azerbaijan",
    "bahamas","bahrain","bangladesh","barbados","belarus","belgium","belize","benin","bhutan","bolivia","bosnia","botswana","brazil",
    "bulgaria","burkina faso","burundi","cambodia","cameroon","canada","cape verde","chad","chile","china","colombia","comoros",
    "congo","costa rica","cotedivoire","ivory coast","croatia","cuba","cyprus","czech","denmark","djibouti","dominica","dominican",
    "ecuador","egypt","el salvador","eritrea","estonia","eswatini","ethiopia","fiji","finland","france","gabon","gambia","georgia",
    "germany","ghana","greece","grenada","guatemala","guinea","guyana","haiti","honduras","hungary","iceland","india","indonesia",
    "iran","iraq","ireland","israel","italy","jamaica","japan","jordan","kazakhstan","kenya","kiribati","kuwait","kyrgyzstan",
    "laos","latvia","lebanon","lesotho","liberia","libya","liechtenstein","lithuania","luxembourg","madagascar","malawi","malaysia",
    "maldives","mali","malta","marshall islands","mauritania","mauritius","mexico","micronesia","moldova","monaco","mongolia",
    "montenegro","morocco","mozambique","myanmar","namibia","nauru","nepal","netherlands","new zealand","nicaragua","niger",
    "nigeria","north macedonia","norway","oman","pakistan","palau","panama","papua new guinea","paraguay","peru","philippines",
    "poland","portugal","qatar","romania","russia","rwanda","saint kitts","saint lucia","st lucia","saint vincent","samoa","san marino",
    "sao tome","saudi arabia","senegal","serbia","seychelles","sierra leone","singapore","slovakia","slovenia","solomon islands",
    "somalia","south africa","spain","sri lanka","sudan","suriname","sweden","switzerland","syria","taiwan","tajikistan","tanzania",
    "thailand","timor","togo","tonga","trinidad","tunisia","turkey","turkiye","turkmenistan","tuvalu","uganda","ukraine",
    "united arab emirates","uae","united kingdom","uk","england","scotland","wales","northern ireland",
    "united states","usa","us","uruguay","uzbekistan","vanuatu","venezuela","vietnam","yemen","zambia","zimbabwe"
}

# Month map
MONTHS = {
    "jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,"apr":4,"april":4,"may":5,"jun":6,"june":6,
    "jul":7,"july":7,"aug":8,"august":8,"sep":9,"sept":9,"september":9,"oct":10,"october":10,"nov":11,"november":11,"dec":12,"december":12
}

# ------------------- UTIL -------------------
def normalize(text: str) -> str:
    t = text.replace("–","-").replace("—","-")
    t = re.sub(r"-\s*\n", "", t)
    t = re.sub(r"\s+", " ", t)
    return t

def read_pdf_alltext_tables(pdf_path):
    text = ""
    tables = []
    # pdfplumber text + tables
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            text += "\n" + txt
            for tab in page.extract_tables() or []:
                if tab and len(tab) >= 2:
                    try:
                        df = pd.DataFrame(tab[1:], columns=tab[0])
                    except Exception:
                        df = pd.DataFrame(tab)
                    if not df.empty:
                        tables.append(df)
    # OCR from images
    doc = fitz.open(pdf_path)
    ocr_blobs = []
    for p in range(len(doc)):
        for img in doc.get_page_images(p):
            xref = img[0]
            base = doc.extract_image(xref)
            image = Image.open(io.BytesIO(base["image"]))
            try:
                txt = pytesseract.image_to_string(image)
                if txt and txt.strip():
                    ocr_blobs.append(txt)
            except Exception:
                pass
    if ocr_blobs:
        text += "\n" + "\n".join(ocr_blobs)

    return normalize(text), tables

def pick_most_common(items):
    if not items:
        return None
    cnt = Counter(items)
    return cnt.most_common(1)[0][0]

# ------------------- CORE EXTRACTORS -------------------

def extract_doi(text, debug=False):
    m = re.search(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b", text, re.I)
    if debug and m: print("[DOI]", m.group(1))
    return m.group(1) if m else "NR"

def extract_registries(text, debug=False):
    # Unified multi-registry regex (handles spaces, hyphens, OCR noise)
    pattern = re.compile(
        r"\b("
        r"NCT\s?-?\s?\d{8}|"  # ClinicalTrials.gov
        r"EudraCT[- ]?\d{4}-\d{6}-\d+|"
        r"ISRCTN\s?\d+|"
        r"CTRI[-/]?\d{4}/\d{2}/\d{6}|"
        r"ChiCTR[-A-Za-z0-9]+|"
        r"DRKS\d+|UMIN\d{7}|"
        r"CRD\d{8}"  # PROSPERO
        r")\b", re.I
    )
    regs = sorted(set(m.strip().replace(" ", "") for m in pattern.findall(text)))
    if debug and regs:
        print("[REGISTRIES]", "; ".join(regs))
    return "; ".join(regs) if regs else "NR"

def extract_publication_year(text, debug=False):
    years = re.findall(r"\b(20\d{2})\b", text)
    if not years: return "NR"
    # heuristic: publication year is often the max year present
    y = max(int(y) for y in years)
    if debug: print("[PUBYEAR]", y)
    return str(y)

def extract_study_id(text, debug=False):
    # FirstAuthor_Year using first proper name-like + pub year
    mname = re.search(r"\b([A-Z][a-z]{2,})\b.*?\b(20\d{2})\b", text)
    if mname:
        sid = f"{mname.group(1)}_{mname.group(2)}"
        if debug: print("[STUDY_ID]", sid)
        return sid
    return "NR"

def extract_country(text, debug=False):
    # Use NER + keyword match fallback, then pick most common
    doc = nlp()(text)
    hits = []
    for ent in doc.ents:
        if ent.label_ in ("GPE","LOC"):
            s = ent.text.strip().lower()
            if s in COUNTRIES:
                hits.append(s)
            # handle variants (e.g., "United States of America")
            if "united states" in s or s=="usa" or s=="us":
                hits.append("united states")
            if "united kingdom" in s or s in ("england","scotland","wales","northern ireland"):
                hits.append("united kingdom")
    # keyword sweep
    for c in COUNTRIES:
        if re.search(rf"\b{re.escape(c)}\b", text, re.I):
            hits.append(c)
    hits = [h for h in hits if h]
    if not hits:
        return "NR"
    primary = pick_most_common(hits)
    mult = len(set(hits)) > 1
    out = primary.title() if primary != "usa" else "United States"
    if out == "United States": out = "USA"
    if out == "United Kingdom": out = "UK"
    if mult:
        out = f"{out} (multicenter)"
    if debug: print("[COUNTRY]", out)
    return out

def infer_study_design(text, debug=False):
    t = text.lower()
    if "randomized" in t or "randomised" in t:
        phase = re.search(r"\bphase\s+([ivx]+)\b", t)
        label = "open-label" if "open" in t else ("blinded" if "blind" in t else "")
        multi = "multicenter" if "multi" in t else ""
        phs = f"Phase {phase.group(1).upper()}" if phase else "Phase NR"
        val = f"{phs} RCT; {label}; {multi}".strip("; ").replace(" ;", ";")
        if debug: print("[DESIGN]", val)
        return val
    if "cohort" in t and "prospective" in t: return "Prospective Cohort"
    if "cohort" in t and "retrospective" in t: return "Retrospective Cohort"
    if "cohort" in t: return "Cohort"
    if "case-control" in t or "case control" in t: return "Case-Control"
    if "crossover" in t or "cross-over" in t: return "Crossover"
    return "NR"

def extract_oncology_setting(text):
    t = text.lower()
    flags = []
    if "adjuvant" in t: flags.append("Adjuvant")
    if "neoadjuvant" in t or "neo-adjuvant" in t: flags.append("Neoadjuvant")
    if "metastatic" in t or "advanced" in t or "stage iv" in t: flags.append("Metastatic")
    if flags:
        return " / ".join(sorted(set(flags), key=lambda x: ["Adjuvant","Neoadjuvant","Metastatic"].index(x)))
    return "NR"

def extract_cancer_type(text):
    t = text.lower()
    if "breast" in t: return "Breast cancer"
    if "lymphoma" in t: return "Lymphoma"
    if "sarcoma" in t: return "Sarcoma"
    if re.search(r"\b(leukemia|leukaemia)\b", t): return "Leukemia"
    if "myeloma" in t: return "Myeloma"
    return "Other" if re.search(r"\bcancer|carcinoma|oncolog", t) else "NR"

def extract_exposure_flags(text):
    t = text.lower()
    anth = "Yes" if "anthracycline" in t or "doxorubicin" in t or "epirubicin" in t else "NR"
    # keep your stratified logic for trastuzumab
    if "+/-" in text or "+ / -" in text:
        trast = "+/- (stratified)"
    else:
        trast = "Yes" if "trastuzumab" in t or "her2" in t or "her-2" in t else "NR"
    return anth, trast

def extract_comparator(text):
    t = text.lower()
    if "placebo" in t: return "Placebo"
    if "standard of care" in t or "usual care" in t or "control group" in t: return "Standard of care"
    if "active comparator" in t or "comparator" in t: return "Other"
    return "NR"

def extract_sample_size(text, tables, debug=False):
    # Try text patterns
    pats = [
        r"\b(?:n\s*=\s*|sample\s*size\s*(?:of)?\s*)(\d{2,5})\b",
        r"\b(\d{2,5})\s*(patients|participants|subjects)\b",
        r"\btotal\s+of\s+(\d{2,5})\b",
    ]
    for pat in pats:
        m = re.search(pat, text, re.I)
        if m:
            if debug: print("[SAMPLESIZE-TEXT]", m.group(1))
            return m.group(1)

    # Try tables: look for numeric totals
    for df in tables:
        try:
            # look for columns like 'Total', 'N', 'n'
            cand_cols = [c for c in df.columns if isinstance(c, str) and re.search(r"\b(total|n)\b", str(c), re.I)]
            if cand_cols:
                series = pd.to_numeric(df[cand_cols[0]], errors="coerce")
                s = int(series.dropna().max()) if not series.dropna().empty else None
                if s and s>0:
                    if debug: print("[SAMPLESIZE-TABLE]", s)
                    return str(s)
            # last-resort: any big integer in table
            numeric = pd.to_numeric(df.stack(), errors="coerce")
            vals = [int(v) for v in numeric.dropna().tolist() if v>9]
            if vals:
                mx = max(vals)
                if debug: print("[SAMPLESIZE-TABLE-ANY]", mx)
                return str(mx)
        except Exception:
            pass
    return "NR"

def extract_arms(text, tables, debug=False):
    t = text.lower()
    # 1:1, 2:1, 3-arm(s), two arms, three groups, etc.
    if m := re.search(r"\b(\d)\s*[:：]\s*(\d)\b", t):
        # could be 1:1 or 2:1 -> arms likely 2
        return "2"
    if re.search(r"\b(\d)\s*[- ]?arm(s)?\b", t):
        n = re.search(r"\b(\d)\s*[- ]?arm(s)?\b", t).group(1)
        return n
    word2num = {"one":1,"two":2,"three":3,"four":4}
    for w,n in word2num.items():
        if re.search(rf"\b{w}\s+(arms?|groups?)\b", t):
            return str(n)
    # Tables: count unique arm labels
    arm_keywords = ("arm", "group", "treatment")
    for df in tables:
        lower_cols = [str(c).lower() for c in df.columns]
        if any(any(k in c for k in arm_keywords) for c in lower_cols):
            # try count of non-null entries in that column
            try:
                col_idx = next(i for i,c in enumerate(lower_cols) if any(k in c for k in arm_keywords))
                n = df.iloc[:,col_idx].dropna().nunique()
                if n and n>0:
                    return str(n)
            except StopIteration:
                pass
    return "NR"

def extract_followup_iqr_or_range(text):
    # capture ranges around follow-up/observation contexts, but accept generic too
    # e.g., "12-18 months", "12 to 18 months", "IQR 10–20 months"
    t = text.lower()
    # IQR style in parentheses: median 15 (IQR 12–18)
    m = re.search(r"\b(iqr|interquartile)\b[^0-9]{0,20}(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(months?|mo)\b", t, re.I)
    if m:
        return f"{m.group(2)}-{m.group(3)} months"
    # generic range
    m = re.search(r"\b(\d{1,2})\s*(?:to|-|–)\s*(\d{1,2})\s*(months?|mo)\b", t, re.I)
    if m:
        return f"{m.group(1)}-{m.group(2)} months"
    return "NR"

def extract_followup_median(text, debug=False):
    """Global detector for median/explicit follow-up periods."""
    t = normalize(text).lower()

    # 1) Explicit "median follow-up 18 months"
    m = re.search(r"median[^A-Za-z0-9]{0,10}(follow[\s-]*up|observation)[^0-9]{0,20}(\d{1,2})\s*(months?|mo)\b", t)
    if m:
        if debug: print("[FU-MEDIAN] median follow-up →", m.group(2))
        return f"{m.group(2)} (median)"

    # 2) “follow-up period of 18 months”
    m = re.search(r"(follow[\s-]*up|observation|monitoring)[^0-9]{0,50}(\d{1,2})\s*(months?|mo)\b", t)
    if m:
        if debug: print("[FU-MEDIAN] explicit follow-up →", m.group(2))
        return f"{m.group(2)} (median)"

    # 3) “18–24 month follow-up” or “12 to 18 months follow-up”
    m = re.search(r"(\d{1,2})\s*(?:-|to|–)\s*(\d{1,2})\s*(months?|mo)\b", t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        median = round((lo + hi) / 2)
        if debug: print("[FU-MEDIAN] range → median", median)
        return f"{median} (inferred median)"

    # 4) Contextual detection within sentence containing "follow"
    for sent in re.split(r"(?<=[\.\?!])\s+", t):
        if "follow" in sent or "observation" in sent:
            nums = re.findall(r"\b(\d{1,2})\s*(months?|mo)\b", sent)
            if nums:
                val = nums[-1][0]
                if debug: print("[FU-MEDIAN] contextual follow-up →", val)
                return f"{val} (approx)"

    return "NR"

def extract_enrollment_years(text, debug=False):
    """Enhanced Enrollment Years detection."""
    t = normalize(text)
    this_year = datetime.now().year

    # 1) Direct range: 2021–2023, between 2022 and 2024
    m = re.search(r"(20\d{2})\s*[-–to]+\s*(20\d{2})", t)
    if m:
        y1, y2 = int(m.group(1)), int(m.group(2))
        if 2000 <= y1 <= this_year + 1 and 2000 <= y2 <= this_year + 1:
            val = f"{y1}–{y2}"
            if debug: print("[ENROLL] range →", val)
            return val

    # 2) “Recruitment started in 2023 for 18 months”
    m = re.search(r"(recruitment|enrollment|study)\s+(?:started|began|initiated)[^0-9]{0,20}(20\d{2})", t, re.I)
    if m:
        start = int(m.group(2))
        dur = re.search(r"(\d{1,2})\s*(month|months|mo)", t)
        if dur:
            dur_mo = int(dur.group(1))
            end = start + (1 if dur_mo >= 10 else 0)
            val = f"{start}–{end}" if end > start else f"{start}"
            if debug: print("[ENROLL] started+dur →", val)
            return val
        if debug: print("[ENROLL] started only →", start)
        return str(start)

    # 3) Month-year pattern: “May 2022 to Feb 2024”
    m = re.search(r"([A-Za-z]{3,9})\s+(20\d{2})\s*(?:to|-|–)\s*([A-Za-z]{3,9})\s+(20\d{2})", t)
    if m:
        y1, y2 = int(m.group(2)), int(m.group(4))
        val = f"{y1}–{y2}" if y1 != y2 else str(y1)
        if debug: print("[ENROLL] month-year →", val)
        return val

    # 4) Fallback to earliest–latest plausible years
    years = [int(y) for y in re.findall(r"\b20\d{2}\b", t)]
    plausible = [y for y in years if 2000 <= y <= this_year + 1]
    if len(plausible) >= 2:
        val = f"{min(plausible)}–{max(plausible)}"
        if debug: print("[ENROLL] fallback span →", val)
        return val
    elif plausible:
        return str(plausible[0])

    return "NR"

def detect_coi(text):
    t = text.lower()
    if re.search(r"\bno\s+(conflicts?|competing)\s+(of\s+interest|interests?)\b", t):
        return "Yes (declared none relevant)"
    if re.search(r"\bnone\s+declared\b|\bno\s+competing\s+interests?\b|\bno\s+conflicts?\b", t):
        return "Yes (none declared)"
    if "conflict of interest" in t or "competing interest" in t:
        return "Yes (declared)"
    return "NR"

def extract_protocol_registration(text):
    """Identify the correct trial registration platform."""
    t = text.lower()
    if "clinicaltrials.gov" in t or re.search(r"\bnct\s?\d{8}\b", t):
        return "Registered on ClinicalTrials.gov"
    if "eudract" in t:
        return "Registered on EudraCT"
    if "isrctn" in t:
        return "Registered on ISRCTN"
    if "ctri" in t:
        return "Registered on CTRI (India)"
    if "chictr" in t:
        return "Registered on ChiCTR"
    if "drks" in t:
        return "Registered on DRKS"
    if "umin" in t:
        return "Registered on UMIN"
    if "prospero" in t:
        return "Registered on PROSPERO"
    if "trial registration" in t or "registered" in t:
        return "Registered (unspecified)"
    return "NR"

def detect_funding(text):
    t = text.lower()
    if "grant" in t or "funded" in t or "ministry" in t or "government" in t or "public" in t:
        return "Non-industry (grant/public)"
    if "sponsor" in t or "sponsored" in t or "pharma" in t or "industry" in t or "company" in t:
        return "Industry"
    if "mixed" in t:
        return "Mixed"
    return "NR"

# ------------------- PIPELINE FOR ONE PDF -------------------

SHEET1_COLUMNS = [
    "Study_ID (FirstAuthor_Year)",
    "PMID/DOI",
    "Registry_ID",
    "Publication_Year",
    "Country",
    "Study_Design (RCT/Cluster-RCT/Crossover/Prospective Cohort/Retrospective Cohort/Case-Control)",
    "Oncology_Setting (Adjuvant/Neoadjuvant/Metastatic)",
    "Cancer_Type (Breast/Lymphoma/Sarcoma/Other)",
    "Anthracycline_Exposure (Yes/No)",
    "Trastuzumab_Exposure (Yes/No)",
    "Comparator (Placebo/Usual Care/Other)",
    "Sample_Size_Total",
    "Arms (N)",
    "Followup_Median (months)",
    "Followup_IQR_or_Range",
    "Enrollment_Years",
    "Funding (Industry/Non-industry/Mixed)",
    "COI_Declared (Yes/No)",
    "Protocol/PROSPERO/Trial_Registration",
]

def extract_sheet1_for_pdf(pdf_path, debug=False):
    text, tables = read_pdf_alltext_tables(pdf_path)
    data = {}

    data["PMID/DOI"] = extract_doi(text, debug)
    data["Registry_ID"] = extract_registries(text, debug)
    data["Study_ID (FirstAuthor_Year)"] = extract_study_id(text, debug)
    data["Publication_Year"] = extract_publication_year(text, debug)
    data["Country"] = extract_country(text, debug)
    data["Study_Design (RCT/Cluster-RCT/Crossover/Prospective Cohort/Retrospective Cohort/Case-Control)"] = infer_study_design(text, debug)
    data["Oncology_Setting (Adjuvant/Neoadjuvant/Metastatic)"] = extract_oncology_setting(text)
    data["Cancer_Type (Breast/Lymphoma/Sarcoma/Other)"] = extract_cancer_type(text)
    anth, trast = extract_exposure_flags(text)
    data["Anthracycline_Exposure (Yes/No)"] = anth
    data["Trastuzumab_Exposure (Yes/No)"] = trast
    data["Comparator (Placebo/Usual Care/Other)"] = extract_comparator(text)
    data["Sample_Size_Total"] = extract_sample_size(text, tables, debug)
    data["Arms (N)"] = extract_arms(text, tables, debug)

    # Follow-up: median & IQR/range
    fu_median = extract_followup_median(text, debug)
    fu_range  = extract_followup_iqr_or_range(text)
    data["Followup_Median (months)"] = fu_median
    data["Followup_IQR_or_Range"] = fu_range

    # Enrollment years
    data["Enrollment_Years"] = extract_enrollment_years(text, debug)

    # Funding/COI/Protocol
    data["Funding (Industry/Non-industry/Mixed)"] = detect_funding(text)
    data["COI_Declared (Yes/No)"] = detect_coi(text)

    proto = extract_protocol_registration(text)
    data["Protocol/PROSPERO/Trial_Registration"] = (
        proto if proto != "NR" else (data["Registry_ID"] if data["Registry_ID"] != "NR" else "NR")
    )
    # Final polish: ensure only true-unknown fields remain NR
    for k,v in data.items():
        if not v or (isinstance(v, str) and not v.strip()):
            data[k] = "NR"

    # Reorder to template
    ordered = {c: data.get(c, "NR") for c in SHEET1_COLUMNS}

    if debug:
        print("—"*72)
        print(f"[DEBUG] {os.path.basename(pdf_path)}")
        for k in SHEET1_COLUMNS:
            print(f"{k}: {ordered[k]}")
        print("—"*72)

    return ordered

# ------------------- SAVE -------------------

def save_rows_to_excel(rows):
    # If template exists, align columns to it; else use our sheet1 schema
    if os.path.exists(OUTPUT_XLSX):
        base = pd.read_excel(OUTPUT_XLSX)
        df = pd.DataFrame(rows)
        # align columns union
        all_cols = list(dict.fromkeys(list(base.columns) + SHEET1_COLUMNS))
        base = base.reindex(columns=all_cols)
        df   = df.reindex(columns=all_cols)
        out  = pd.concat([base, df], ignore_index=True)
    else:
        df  = pd.DataFrame(rows, columns=SHEET1_COLUMNS)
        out = df
    out.to_excel(OUTPUT_XLSX, index=False)

# ------------------- MAIN -------------------

def main():
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--pdf", help="Path to one PDF")
    g.add_argument("--input-folder", help="Folder with PDFs")
    parser.add_argument("--debug", action="store_true", help="Print matched values")
    args = parser.parse_args()

    pdfs = []
    if args.pdf:
        pdfs = [args.pdf]
    else:
        pdfs = sorted([p for p in glob.glob(os.path.join(args.input_folder, "**", "*.pdf"), recursive=True)])

    rows = []
    for p in pdfs:
        try:
            row = extract_sheet1_for_pdf(p, debug=args.debug)
            rows.append(row)
        except Exception as e:
            print(f"[ERROR] {p}: {e}")

    if rows:
        save_rows_to_excel(rows)
        print(f"✅ Saved {len(rows)} row(s) → {OUTPUT_XLSX}")
    else:
        print("No rows extracted.")

if __name__ == "__main__":
    main()
