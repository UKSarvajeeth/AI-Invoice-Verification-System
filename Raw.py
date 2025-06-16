import os, re, json
import pandas as pd
import fitz                        # PyMuPDF
from dotenv import load_dotenv
import openai

# — Load API Key —
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# — Config —
EXCEL_FILE   = "Master data.xlsx"
PDF_FOLDER   = "pdfs"
OUTPUT_FILE  = "discrepancy_report.csv"

# — Helpers —

def extract_text_from_pdf(path):
    doc = fitz.open(path)
    return "\n".join(p.get_text() for p in doc)

def find_patient_id(text):
    m = re.search(r"(?:Patient\s*ID|ID)\s*[:\-]?\s*(\d+)", text, re.IGNORECASE)
    return m.group(1) if m else None

def compare_with_gpt(pdf_text, excel_row):
    system = """
You are a data verification assistant. Your ONLY job is to find ACTUAL DATA ERRORS.

STRICT RULES:

1. IGNORE these situations (DO NOT REPORT):
   - Fields not found in PDF
   - Date format differences (2024-12-01 00:00:00 = 1-Dec-2024 = 12/01/2024)
   - Text format differences (BCBS = EXCEL BCBS = Finance Class BCBS)
   - Case differences (JOHN = John = john)
   - Extra spaces or punctuation
   - Different field labels

2. ONLY REPORT these situations:
   - Completely different names (John Smith ≠ Jane Doe)
   - Different insurance companies (BCBS ≠ Aetna) 
   - Different calendar dates (Jan 1 ≠ Dec 31)
   - Different amounts ($100 ≠ $200)

EXAMPLES OF WHAT NOT TO REPORT:
❌ "SWO Expiration Date: Excel has '2024-12-01 00:00:00', PDF has '1-Dec-2024'" = SAME DATE
❌ "Field 'Last usage Date' not found in PDF" = IRRELEVANT
❌ "Insurance: Excel has 'BCBS', PDF has 'Finance Class BCBS'" = SAME COMPANY

EXAMPLES OF WHAT TO REPORT:
✅ "Patient Name: Excel has 'JOHN SMITH', PDF has 'JANE DOE'" = DIFFERENT PERSON
✅ "Insurance: Excel has 'BCBS', PDF has 'AETNA'" = DIFFERENT COMPANY

RESPONSE FORMAT:
- If no actual data errors exist: "No discrepancies"
- If actual data errors found: "Field Name: Excel has 'X', PDF has 'Y'"

Be very strict - only report genuine data errors, not formatting or missing field issues.
"""

    user = (
        "PDF Text:\n```\n"
        + pdf_text[:3800]
        + "\n```\n\nExcel Data:\n```json\n"
        + json.dumps(excel_row, indent=2, default=str)
        + "\n```"
    )

    resp = openai.ChatCompletion.create(
        model="gpt-4",
        temperature=0.0,
        messages=[
            {"role": "system",  "content": system},
            {"role": "user",    "content": user}
        ]
    )
    return resp.choices[0].message.content.strip()

# — Main —

df = pd.read_excel(EXCEL_FILE, dtype={"Patient ID": str})
reports = []

print(f"📋 Loaded {len(df)} records from Excel")

for fname in os.listdir(PDF_FOLDER):
    if not fname.lower().endswith(".pdf"):
        continue

    path = os.path.join(PDF_FOLDER, fname)
    txt  = extract_text_from_pdf(path)

    pid = find_patient_id(txt)
    if not pid:
        print(f"[❌] {fname}: No Patient ID found")
        continue

    matching_records = df[df["Patient ID"] == pid]
    if matching_records.empty:
        print(f"[⚠️] {fname}: Patient ID {pid} not in Excel")
        continue
    
    excel_row = matching_records.iloc[0].to_dict()
    
    print(f"[🔍] {fname} - Patient ID {pid}: Checking for data errors...")
    
    discrepancies = compare_with_gpt(txt, excel_row)

    # Clean up the response
    if "no discrepancies" in discrepancies.lower() or "all the data" in discrepancies.lower():
        clean_discrepancies = "No discrepancies"
    else:
        clean_discrepancies = discrepancies

    reports.append({
        "Patient ID": pid,
        "PDF File": fname,
        "Data Errors": clean_discrepancies
    })

# Save results
result_df = pd.DataFrame(reports)
result_df.to_csv(OUTPUT_FILE, index=False)

# Summary
actual_errors = len(result_df[~result_df["Data Errors"].str.contains("No discrepancies", na=False)])
no_errors = len(reports) - actual_errors

print(f"\n✅ Report saved to {OUTPUT_FILE}")
print(f"📊 Summary:")
print(f"   - Files with NO data errors: {no_errors}")
print(f"   - Files with ACTUAL data errors: {actual_errors}")

if actual_errors > 0:
    print(f"\n🚨 Files with data errors:")
    error_files = result_df[~result_df["Data Errors"].str.contains("No discrepancies", na=False)]
    for _, row in error_files.iterrows():
        print(f"   - {row['PDF File']} (ID: {row['Patient ID']}): {row['Data Errors']}")
