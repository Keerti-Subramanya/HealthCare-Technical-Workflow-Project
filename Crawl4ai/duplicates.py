import pandas as pd
import os

def export_duplicate_titles_to_csv(input_file_path, output_file_path, title_column_name='Title'):
    """
    Reads a CSV, identifies rows with duplicate values in the specified column,
    and exports those duplicate rows to a new CSV file.

    Args:
        input_file_path (str): The path to the source CSV file.
        output_file_path (str): The path where the duplicate data will be saved.
        title_column_name (str): The name of the column to check for duplicates.
    """
    try:
        # 1. Read the CSV file
        df = pd.read_csv('E:\Healthcare Technical Workflow\Crawl4ai\scraper_results.csv')

        # Basic check for column existence
        if title_column_name not in df.columns:
            print(f"❌ Error: Column '{title_column_name}' not found in the CSV file.")
            print(f"Available columns are: {list(df.columns)}")
            return

        # 2. Identify duplicate rows based ONLY on the specified column
        # keep=False marks ALL instances of a duplicate title (the first, second, etc.) as True.
        is_duplicate = df.duplicated(subset=[title_column_name], keep=False)
        duplicate_rows = df[is_duplicate]

        # 3. Process the results
        if duplicate_rows.empty:
            print(f"✅ No duplicate values found in the '{title_column_name}' column. No file created.")
        else:
            # Sort the duplicates by Title for easy human review
            sorted_duplicates = duplicate_rows.sort_values(by=title_column_name)
            
            # 4. Export the results to a new CSV file
            sorted_duplicates.to_csv(output_file_path, index=False)
            
            duplicate_count = len(sorted_duplicates)
            unique_duplicate_titles = df[is_duplicate][title_column_name].nunique()
            
            print("-" * 70)
            print(f"🎉 Success!")
            print(f"⚠️ Found {duplicate_count} rows across {unique_duplicate_titles} unique duplicated titles.")
            print(f"💾 The duplicate data has been saved to: **{os.path.abspath(output_file_path)}**")
            print("-" * 70)

    except FileNotFoundError:
        print(f"❌ Error: Input file '{input_file_path}' was not found.")
    except pd.errors.EmptyDataError:
        print("❌ Error: The input file is empty.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# --- Configuration ---
INPUT_FILE = 'scraper_results.csv' 
OUTPUT_FILE = 'title_duplicates.csv'
TITLE_COLUMN = 'Title' 

# --- Execution ---
# IMPORTANT: Make sure your input file exists in the same directory as this script.
export_duplicate_titles_to_csv(INPUT_FILE, OUTPUT_FILE, TITLE_COLUMN)