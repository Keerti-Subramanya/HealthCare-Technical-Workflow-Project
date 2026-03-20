#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
json_to_xlsx.py — Convert cached JSON(s) → Excel(s)
---------------------------------------------------
💡 Usage examples:

# Convert a single cache
python json_to_xlsx.py --json partial_caches/DOI_10_1186_s40959_025_00368_9_default_cache.json \
                       --template CardioProtect_MetaAnalysis_DataTemplate.xlsx

# Convert all caches → recovered/*.xlsx
python json_to_xlsx.py --all --template CardioProtect_MetaAnalysis_DataTemplate.xlsx
"""

import os, json, argparse, pandas as pd

def json_to_excel(json_path, template_xlsx, out_path):
    """Convert a single cache JSON file into Excel."""
    print(f"🧩 Loading cache JSON: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    xl = pd.ExcelFile(template_xlsx)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet in xl.sheet_names:
            cols = list(xl.parse(sheet, nrows=1).columns)
            rows = data.get(sheet, [{c: "NR" for c in cols}])
            if isinstance(rows, dict):
                rows = [rows]
            df = pd.DataFrame(rows)
            for c in cols:
                if c not in df.columns:
                    df[c] = "NR"
            df = df.reindex(columns=cols)
            df.to_excel(writer, sheet_name=sheet[:31], index=False)

    print(f"✅ Excel rebuilt → {out_path}")

def process_all_caches(template_xlsx, cache_dir="partial_caches", output_dir="recovered"):
    """Convert all *_cache.json files into Excel and save under recovered/"""
    os.makedirs(output_dir, exist_ok=True)
    json_files = [os.path.join(cache_dir, f) for f in os.listdir(cache_dir) if f.endswith("_cache.json")]

    if not json_files:
        print(f"❌ No cache files found in {cache_dir}")
        return

    for json_path in json_files:
        base = os.path.splitext(os.path.basename(json_path))[0].replace("_cache", "")
        out_path = os.path.join(output_dir, f"Recovered_{base}.xlsx")
        json_to_excel(json_path, template_xlsx, out_path)

    print(f"\n🎯 All recovered Excel files saved in: {os.path.abspath(output_dir)}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="Path to single *_cache.json file")
    ap.add_argument("--template", required=True, help="Path to Excel template (e.g. CardioProtect_MetaAnalysis_DataTemplate.xlsx)")
    ap.add_argument("--all", action="store_true", help="Convert all *_cache.json in partial_caches/")
    args = ap.parse_args()

    if args.all:
        process_all_caches(args.template)
    elif args.json:
        base = os.path.splitext(os.path.basename(args.json))[0].replace("_cache", "")
        out_dir = "recovered"
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"Recovered_{base}.xlsx")
        json_to_excel(args.json, args.template, out_path)
    else:
        print("⚠️ Please specify --json <path> or --all")
