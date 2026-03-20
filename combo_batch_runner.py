#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CardioProtect Combinatorial Batch Runner
----------------------------------------
Runs every Exposure × Intervention pair automatically.
Each query = one scraper run with renaming + timestamping.
Now uses a shared global database for automatic deduplication.
"""

import os, itertools, subprocess, datetime

from multi_source_scraper import DB_PATH

EXPOSURES = [
    "anthracycline", "doxorubicin", "daunorubicin",
    "epirubicin", "idarubicin", "trastuzumab", "herceptin"
]

INTERVENTIONS = [
    "dexrazoxane", "carvedilol", "enalapril", "lisinopril",
    "losartan", "valsartan", "sacubitril/valsartan",
    "atorvastatin", "rosuvastatin", "spironolactone",
    "eplerenone", "dapagliflozin", "empagliflozin"
]



BASE_CMD = (
    "python multi_source_scraper.py "
    "--query \"({exp}) AND ({intv}) AND (cancer OR oncology) "
    "--sources pubmed,crossref --from_year 2010 --to_year 2025 "
    "--limit 1000 --merge_report "
    f"--db_path "   # <--- shared DB path added here
)

OUTPUT_DIR = "batch_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# simple run log
RUN_LOG = os.path.join(OUTPUT_DIR, "Batch_Run_Log.txt")
with open(RUN_LOG, "a", encoding="utf-8") as log:
    log.write(f"\n=== Batch run started: {datetime.datetime.now()} ===\n")

for exp, intv in itertools.product(EXPOSURES, INTERVENTIONS):
    tag = f"{exp}_{intv}".replace("/", "-").replace(" ", "_")
    print(f"\n🚀 Running {tag} ...")

    cmd = BASE_CMD.format(exp=exp, intv=intv)
    start_time = datetime.datetime.now()

    subprocess.run(cmd, shell=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    for ext in ["csv", "xlsx", "json", "txt"]:
        for fn in os.listdir("."):
            if fn.startswith("scraper_results") and fn.endswith(ext):
                new_name = os.path.join(OUTPUT_DIR, f"{tag}_{ts}.{ext}")
                os.rename(fn, new_name)
                print(f"→ Saved {new_name}")

    duration = (datetime.datetime.now() - start_time).total_seconds() / 60
    with open(RUN_LOG, "a", encoding="utf-8") as log:
        log.write(f"{tag} completed in {duration:.2f} min\n")

print("\n✅ All batches finished. Shared DB:",DB_PATH)
