#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CardioProtect Universal Merger
------------------------------
Merges all batch_results/*.csv into one master dataset.
- Deduplicates by DOI, Title, or PMID (Key)
- Keeps Zotero-style headers
- Saves as CSV, XLSX, and JSON
"""

import os, re, json, pandas as pd
from glob import glob

INPUT_DIR = "batch_results"
OUTPUT_CSV = "CardioProtect_Universal_Merged.csv"
OUTPUT_XLSX = "CardioProtect_Universal_Merged.xlsx"
OUTPUT_JSON = "CardioProtect_Universal_Merged.json"
MERGE_REPORT = "CardioProtect_Merge_Report.txt"

# Normalize titles (same as scraper)
def normalize_title(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (t or "").lower())).strip()

# Collect and merge
all_files = glob(os.path.join(INPUT_DIR, "*.csv"))
if not all_files:
    print("⚠️ No batch CSV files found in", INPUT_DIR)
    exit()

dfs = []
for f in all_files:
    print(f"📥 Reading {os.path.basename(f)}")
    try:
        df = pd.read_csv(f)
        df["__source_file"] = os.path.basename(f)
        dfs.append(df)
    except Exception as e:
        print(f"⚠️ Could not read {f}: {e}")

merged = pd.concat(dfs, ignore_index=True)

# Deduplicate by DOI, Key, or normalized title
merged["__norm_title"] = merged["Title"].apply(normalize_title)
before = len(merged)

merged = merged.sort_values(["Publication Year", "Title"], ascending=[False, True])
merged = merged.drop_duplicates(subset=["DOI"], keep="first")
merged = merged.drop_duplicates(subset=["Key"], keep="first")
merged = merged.drop_duplicates(subset=["__norm_title"], keep="first")

after = len(merged)
removed = before - after

print(f"✅ Merged {len(all_files)} files → {after} unique records (removed {removed} duplicates)")

# Export
merged.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
merged.to_excel(OUTPUT_XLSX, index=False, engine="openpyxl")

records = merged.to_dict(orient="records")
with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

# Merge report
with open(MERGE_REPORT, "w", encoding="utf-8") as f:
    f.write(f"Total files merged: {len(all_files)}\n")
    f.write(f"Records before deduplication: {before}\n")
    f.write(f"Records after deduplication: {after}\n")
    f.write(f"Duplicates removed: {removed}\n\n")
    f.write("Files merged:\n" + "\n".join(os.path.basename(f) for f in all_files))

print("📦 Universal files saved:")
print(" -", OUTPUT_CSV)
print(" -", OUTPUT_XLSX)
print(" -", OUTPUT_JSON)
print(" -", MERGE_REPORT)
