# from transformers import pipeline
# import pandas as pd
# from tqdm import tqdm

# # === 1️⃣ Load your CSV ===
# input_csv = "scraper_results.csv"
# output_csv = "scraper_results_summarized_test.csv"  # new file
# df = pd.read_csv(input_csv)

# # === Optional: only process first 10 rows for testing ===
# df = df.head(10)

# # === 2️⃣ Automatically find the text column (most text-heavy) ===
# possible_text_cols = sorted(df.columns, key=lambda c: df[c].astype(str).str.len().mean(), reverse=True)
# text_column = possible_text_cols[0]
# print(f"🧠 Using column '{text_column}' for summarization.")

# # === 3️⃣ Initialize the summarizer (CPU mode) ===
# summarizer = pipeline("summarization", model="facebook/bart-large-cnn", device=-1)

# # === 4️⃣ Function to summarize each record ===
# def summarize_text(text):
#     if pd.isna(text) or not str(text).strip():
#         return ""
#     try:
#         summary = summarizer(str(text), max_length=130, min_length=30, do_sample=False)
#         return summary[0]['summary_text']
#     except Exception as e:
#         return f"Error: {e}"

# # === 5️⃣ Apply summarization row by row with progress bar ===
# tqdm.pandas()
# df["summarized_data"] = df[text_column].progress_apply(summarize_text)

# # === 6️⃣ Summarize the entire dataset (global summary) ===
# combined_text = " ".join(df["summarized_data"].astype(str).tolist())
# try:
#     overall_summary = summarizer(combined_text, max_length=250, min_length=80, do_sample=False)[0]['summary_text']
# except Exception as e:
#     overall_summary = f"Error: {e}"

# # === 7️⃣ Add overall summary as a new column (same for all rows) ===
# df["overall_summary"] = overall_summary

# # === 8️⃣ Save as a NEW CSV file ===
# df.to_csv(output_csv, index=False)
# print(f"✅ Summarization complete!")
# print(f"💾 New file saved as: {output_csv}")

# from transformers import pipeline, AutoTokenizer
# import pandas as pd
# from tqdm import tqdm
# import time
# import math

# # ---------- CONFIG ----------
# INPUT_CSV = "scraper_results.csv"
# OUTPUT_CSV = "scraper_results_summarized_test.csv"   # new file
# TEST_ROWS = 10   # keep for quick testing; set to None or remove to run full file
# MODEL_NAME = "facebook/bart-large-cnn" # If you have a long-context model available (LED / Longformer-encoder-decoder), you can replace MODEL_NAME with something like "allenai/led-base-16384" and increase model_max_len handling — that lets you send longer input without hierarchical summarization.
# DEVICE = -1  # -1 for CPU, or set 0 for GPU if available
# CHUNK_BY_TOKENS = True   # True => use tokenizer-based chunking (recommended)
# SIMPLE_CHUNK_SIZE = 8    # used if CHUNK_BY_TOKENS=False
# TOKEN_BUFFER = 50        # leave this many tokens free from model max length

# # ---------- LOAD DATA ----------
# df = pd.read_csv(INPUT_CSV)
# if TEST_ROWS:
#     df = df.head(TEST_ROWS)

# # auto-detect the text column (most text-heavy)
# possible_text_cols = sorted(df.columns, key=lambda c: df[c].astype(str).str.len().mean(), reverse=True)
# text_column = possible_text_cols[0]
# print(f"Using text column: {text_column!r} (rows: {len(df)})\n")

# # ---------- INITIALIZE SUMMARIZER & TOKENIZER ----------
# summarizer = pipeline("summarization", model=MODEL_NAME, device=DEVICE)
# tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
# model_max_len = getattr(tokenizer, "model_max_length", 1024)
# print(f"Model max tokens (approx): {model_max_len}")

# # ---------- HELPER FUNCTIONS ----------
# def summarize_text(text, max_length=130, min_length=30):
#     if not text or not str(text).strip():
#         return ""
#     try:
#         out = summarizer(str(text), max_length=max_length, min_length=min_length, do_sample=False)
#         return out[0]["summary_text"]
#     except Exception as e:
#         return f"Error: {e}"

# def chunk_summaries_by_tokens(summaries, tokenizer, max_tokens, buffer=TOKEN_BUFFER):
#     """Accumulate summaries until adding the next would exceed max_tokens-buffer."""
#     chunks = []
#     current = []
#     current_tokens = 0
#     for s in summaries:
#         if not s or not str(s).strip():
#             continue
#         toks = len(tokenizer(s, truncation=False)["input_ids"])
#         # account for a small separator token between joined summaries (+1)
#         if current_tokens + toks + 1 <= max_tokens - buffer:
#             current.append(s)
#             current_tokens += toks + 1
#         else:
#             if current:
#                 chunks.append(current)
#             current = [s]
#             current_tokens = toks + 1
#     if current:
#         chunks.append(current)
#     return chunks

# def chunk_list(lst, n):
#     for i in range(0, len(lst), n):
#         yield lst[i:i+n]

# # ---------- STEP 1: per-row summarization (if needed) ----------
# if "summarized_data" not in df.columns:
#     print("Summarizing rows (per-record)...")
#     tqdm.pandas()
#     df["summarized_data"] = df[text_column].progress_apply(lambda t: summarize_text(t, max_length=130, min_length=30))
# else:
#     print("Found existing 'summarized_data' column — using it.")

# # ---------- STEP 2: hierarchical summarization for overall summary ----------
# row_summaries = df["summarized_data"].astype(str).tolist()
# row_summaries = [s for s in row_summaries if s.strip()]  # drop empty strings

# if not row_summaries:
#     overall_summary = ""
# else:
#     print("\nCreating chunk summaries to avoid input truncation...")
#     if CHUNK_BY_TOKENS:
#         chunks = chunk_summaries_by_tokens(row_summaries, tokenizer, model_max_len)
#         print(f" -> Created {len(chunks)} chunk(s) using token-aware chunking (buffer={TOKEN_BUFFER}).")
#     else:
#         chunks = list(chunk_list(row_summaries, SIMPLE_CHUNK_SIZE))
#         print(f" -> Created {len(chunks)} chunk(s) using simple chunk size = {SIMPLE_CHUNK_SIZE}.")

#     chunk_summaries = []
#     start = time.time()
#     for i, chunk in enumerate(tqdm(chunks, desc="Summarizing chunks")):
#         joined = " ".join(chunk)
#         # tune lengths per-chunk (shorter than final)
#         try:
#             cs = summarize_text(joined, max_length=200, min_length=40)
#         except Exception as e:
#             cs = f"Error: {e}"
#         chunk_summaries.append(cs)

#     # If only one chunk, that's our overall summary; otherwise summarize chunk summaries
#     if len(chunk_summaries) == 1:
#         overall_summary = chunk_summaries[0]
#     else:
#         print("\nSummarizing the chunk-summaries to produce the final overall summary...")
#         combined = " ".join(chunk_summaries)
#         overall_summary = summarize_text(combined, max_length=250, min_length=80)

# # ---------- STEP 3: attach and save (to NEW file) ----------
# df["overall_summary"] = overall_summary
# df.to_csv(OUTPUT_CSV, index=False)

# print(f"\nDone. Saved new file: {OUTPUT_CSV}")
# print("\nShort preview of overall summary:\n", overall_summary[:600], "...")


''' For entire file'''
# from transformers import pipeline
# import pandas as pd
# from tqdm import tqdm

# # Optional tip section
# print("""
# 💡 TIP:
# - Ensure your CSV file is in the same folder or provide full path below.
# - Change 'text_column' to the column containing text to summarize (e.g. 'Abstract', 'Text', 'Description').
# - A new file 'summarized_output.csv' will be created — original file remains unchanged.
# """)

# # Load CSV file
# file_path = "scraper_results.csv"  # Change if needed
# df = pd.read_csv(file_path)

# # Replace with the actual column name in your CSV (e.g., 'Abstract', 'text', etc.)
# text_column = "Abstract"
# if text_column not in df.columns:
#     print(f"⚠️ Column '{text_column}' not found. Available columns: {list(df.columns)}")
#     exit()

# # Initialize summarization model
# summarizer = pipeline("summarization", model="facebook/bart-large-cnn", device=-1)

# # Function to summarize a single record
# def summarize_text(text):
#     if not isinstance(text, str) or len(text.strip()) == 0:
#         return ""
#     try:
#         summary = summarizer(text, max_length=130, min_length=30, do_sample=False)
#         return summary[0]['summary_text']
#     except Exception as e:
#         print(f"⚠️ Skipped one record due to: {e}")
#         return ""

# # Apply summarization per record with progress bar
# tqdm.pandas(desc="Summarizing each record")
# df["summarized_data"] = df[text_column].progress_apply(summarize_text)

# # Combine all individual summaries into one large text
# combined_text = " ".join(df["summarized_data"].dropna().astype(str).tolist())

# # Summarize the combined text to create a true overall summary
# try:
#     overall = summarizer(combined_text, max_length=300, min_length=100, do_sample=False)
#     overall_summary = overall[0]["summary_text"]
# except Exception as e:
#     print(f"⚠️ Failed overall summary: {e}")
#     overall_summary = ""

# # Add the same overall summary (for context) or as a single-row column if preferred
# df["overall_summary"] = overall_summary

# # Save to new CSV file
# output_path = "summarized_output.csv"
# df.to_csv(output_path, index=False)

# print(f"✅ Summarization complete! Results saved to: {output_path}")


from transformers import pipeline
import pandas as pd
from tqdm import tqdm

# Optional tip section
print("""
💡 TIP:
- Ensure your CSV file is in the same folder or provide full path below.
- Change 'text_column' to the column containing text to summarize (e.g. 'Abstract', 'Text', 'Description').
- A new file 'summarized_output.csv' will be created — original file remains unchanged.
""")

# Load CSV file
file_path = "scraper_results.csv"  # Change if needed
df = pd.read_csv(file_path)

# Only take the first 10 rows
df = df.head(10)

# Replace with the actual column name in your CSV (e.g., 'Abstract', 'text', etc.)
text_column = "Abstract Note"
if text_column not in df.columns:
    print(f"⚠️ Column '{text_column}' not found. Available columns: {list(df.columns)}")
    exit()

# Initialize summarization model
summarizer = pipeline("summarization", model="facebook/bart-large-cnn", device=-1)

# Function to summarize a single record
def summarize_text(text):
    if not isinstance(text, str) or len(text.strip()) == 0:
        return ""
    try:
        summary = summarizer(text, max_length=130, min_length=30, do_sample=False)
        return summary[0]['summary_text']
    except Exception as e:
        print(f"⚠️ Skipped one record due to: {e}")
        return ""

# Apply summarization per record with progress bar
tqdm.pandas(desc="Summarizing each record")
df["summarized_data"] = df[text_column].progress_apply(summarize_text)

# Combine all individual summaries into one large text
combined_text = " ".join(df["summarized_data"].dropna().astype(str).tolist())

# Summarize the combined text to create a true overall summary
try:
    overall = summarizer(combined_text, max_length=300, min_length=100, do_sample=False)
    overall_summary = overall[0]["summary_text"]
except Exception as e:
    print(f"⚠️ Failed overall summary: {e}")
    overall_summary = ""

# Add the same overall summary (for context) or as a single-row column if preferred
df["overall_summary"] = overall_summary

# Save to new CSV file
output_path = "summarized_output.csv"
df.to_csv(output_path, index=False)

print(f"✅ Summarization complete! Results saved to: {output_path}")
