#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
merge_previews.py — Combine all per-PDF preview Excel files into one merged workbook.
Usage:
    python merge_previews.py --template CardioProtect_MetaAnalysis_DataTemplate.xlsx \
                             --preview_dir multi_previews/<session_id>
"""

import os, argparse, pandas as pd

def merge_previews(template_xlsx, preview_dir, output=None):
    if not os.path.exists(preview_dir):
        raise FileNotFoundError(f"Preview directory not found: {preview_dir}")

    preview_files = [os.path.join(preview_dir, f) for f in os.listdir(preview_dir)
                     if f.startswith("Recovered_") and f.endswith(".xlsx")]
    if not preview_files:
        raise ValueError("No preview Excel files found.")

    xl = pd.ExcelFile(template_xlsx)
    all_sheets = xl.sheet_names
    merged = {s: [] for s in all_sheets}

    print(f"📂 Merging {len(preview_files)} previews from {preview_dir}")

    for pf in preview_files:
        print(f" → {os.path.basename(pf)}")
        try:
            book = pd.ExcelFile(pf)
            for s in all_sheets:
                try:
                    df = book.parse(s)
                    if not df.empty:
                        merged[s].append(df)
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠️ Failed reading {pf}: {e}")

    # Write combined workbook
    output = output or os.path.join(preview_dir, "CardioProtect_Final_Merged.xlsx")
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for s in all_sheets:
            base_cols = list(xl.parse(s, nrows=1).columns)
            if merged[s]:
                df = pd.concat(merged[s], ignore_index=True)
            else:
                df = pd.DataFrame([{c: "NR" for c in base_cols}])
            for c in base_cols:
                if c not in df.columns:
                    df[c] = "NR"
            df = df.reindex(columns=base_cols)
            df.to_excel(writer, sheet_name=s[:31], index=False)

    print(f"\n🎯 Merged Excel created → {output}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, help="Path to CardioProtect_MetaAnalysis_DataTemplate.xlsx")
    parser.add_argument("--preview_dir", required=True, help="Directory containing preview_*.xlsx files")
    parser.add_argument("--output", help="Optional output path for merged workbook")
    args = parser.parse_args()
    merge_previews(args.template, args.preview_dir, args.output)
