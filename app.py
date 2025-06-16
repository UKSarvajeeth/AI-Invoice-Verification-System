import streamlit as st
import os
import re
import json
import pandas as pd
import fitz  # PyMuPDF
import openai
from datetime import datetime
import tempfile
import zipfile
from io import BytesIO
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set page config
st.set_page_config(
    page_title="PDF Data Validator",
    page_icon="📋",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
.main-header {
    font-size: 2.5rem;
    color: #1f77b4;
    text-align: center;
    margin-bottom: 2rem;
}
.section-header {
    font-size: 1.3rem;
    color: #2c3e50;
    margin-top: 2rem;
    margin-bottom: 1rem;
}
.metric-container {
    background-color: #f8f9fa;
    padding: 1rem;
    border-radius: 0.5rem;
    margin: 0.5rem 0;
}
.success-box {
    background-color: #d4edda;
    border: 1px solid #c3e6cb;
    border-radius: 0.25rem;
    padding: 0.75rem;
    color: #155724;
}
.error-box {
    background-color: #f8d7da;
    border: 1px solid #f5c6cb;
    border-radius: 0.25rem;
    padding: 0.75rem;
    color: #721c24;
}
</style>
""", unsafe_allow_html=True)

# Initialize OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Helper functions
def extract_text_from_pdf(file_bytes):
    """Extract text from PDF bytes"""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text

def find_patient_id(text):
    """Extract Patient ID from PDF text"""
    m = re.search(r"(?:Patient\s*ID|ID)\s*[:\-]?\s*(\d+)", text, re.IGNORECASE)
    return m.group(1) if m else None

def compare_with_gpt(pdf_text, excel_row):
    """Compare PDF text with Excel data using GPT"""
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

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4",
            temperature=0.0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Error during comparison: {str(e)}"

def check_api_key():
    """Check if OpenAI API key is available and valid"""
    if not openai.api_key:
        return False, "OpenAI API key not found in .env file"
    
    try:
        # Test API key with a simple request
        openai.Model.list()
        return True, "API key is valid"
    except Exception as e:
        return False, f"API key error: {str(e)}"

def process_files(pdf_files, excel_file):
    """Process all PDF files and return results"""
    # Load Excel data
    try:
        df = pd.read_excel(excel_file, dtype={"Patient ID": str})
    except Exception as e:
        st.error(f"Error reading Excel file: {str(e)}")
        return None
    
    reports = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, pdf_file in enumerate(pdf_files):
        try:
            # Update progress
            progress = (i + 1) / len(pdf_files)
            progress_bar.progress(progress)
            status_text.text(f"Processing {pdf_file.name} ({i+1}/{len(pdf_files)})")
            
            # Extract text from PDF
            pdf_bytes = pdf_file.getvalue()
            txt = extract_text_from_pdf(pdf_bytes)
            
            # Find Patient ID
            pid = find_patient_id(txt)
            if not pid:
                reports.append({
                    "Patient ID": "Not Found",
                    "PDF File": pdf_file.name,
                    "Data Errors": "Patient ID not found in PDF",
                    "Status": "Error"
                })
                continue
            
            # Find matching record in Excel
            matching_records = df[df["Patient ID"] == pid]
            if matching_records.empty:
                reports.append({
                    "Patient ID": pid,
                    "PDF File": pdf_file.name,
                    "Data Errors": f"Patient ID {pid} not found in Excel master data",
                    "Status": "Error"
                })
                continue
            
            # Compare with GPT
            excel_row = matching_records.iloc[0].to_dict()
            discrepancies = compare_with_gpt(txt, excel_row)
            
            # Clean up response
            if "no discrepancies" in discrepancies.lower() or "all the data" in discrepancies.lower():
                clean_discrepancies = "No discrepancies"
                status = "Clean"
            elif "Error during comparison" in discrepancies:
                clean_discrepancies = discrepancies
                status = "Error"
            else:
                clean_discrepancies = discrepancies
                status = "Data Error"
            
            reports.append({
                "Patient ID": pid,
                "PDF File": pdf_file.name,
                "Data Errors": clean_discrepancies,
                "Status": status
            })
            
        except Exception as e:
            reports.append({
                "Patient ID": "Error",
                "PDF File": pdf_file.name,
                "Data Errors": f"Processing error: {str(e)}",
                "Status": "Error"
            })
    
    # Clear progress indicators
    progress_bar.empty()
    status_text.empty()
    
    return pd.DataFrame(reports)

# Main App
def main():
    # Title
    st.markdown('<h1 class="main-header">📋 PDF Data Validator</h1>', unsafe_allow_html=True)
    st.markdown("**Validate PDF documents against Excel master data using AI-powered comparison**")
    
    # Check API key status
    api_valid, api_message = check_api_key()
    
    # Sidebar for configuration and status
    with st.sidebar:
        st.header("⚙️ Configuration Status")
        
        # API Key status
        if api_valid:
            st.success(f"✅ {api_message}")
        else:
            st.error(f"❌ {api_message}")
            st.info("💡 Make sure you have a `.env` file in your project directory with:\n```\nOPENAI_API_KEY=your_api_key_here\n```")
        
        st.markdown("---")
        
        # Help section
        with st.expander("ℹ️ How to use"):
            st.markdown("""
            **Setup:**
            1. Create a `.env` file with your OpenAI API key
            2. Restart the application if you just added the .env file
            
            **Usage:**
            1. **Upload your Excel master data file** (.xlsx format)
            2. **Upload PDF files** to validate (can select multiple)
            3. **Click 'Start Validation'** to begin processing
            4. **Review results** and download reports
            
            **What gets compared:**
            - Patient information (Name, ID, etc.)
            - Insurance details
            - Dates (expiration, billing, etc.)
            - All other fields from Excel master data
            
            **What gets ignored:**
            - Date format differences
            - Text formatting differences
            - Missing fields in PDF
            - Case differences
            """)
        
        with st.expander("📊 Report Types"):
            st.markdown("""
            - **Clean Files**: No discrepancies found
            - **Data Errors**: Actual data mismatches detected
            - **Processing Errors**: Files that couldn't be processed
            """)
        
        with st.expander("🔧 .env File Setup"):
            st.markdown("""
            Create a `.env` file in your project directory:
            
            ```
            OPENAI_API_KEY=sk-your-actual-api-key-here
            ```
            
            **Important:**
            - No spaces around the equals sign
            - No quotes around the API key
            - Save the file as `.env` (with the dot)
            - Restart the Streamlit app after creating the file
            """)
    
    # Show warning if API key is not valid
    if not api_valid:
        st.error("🚨 OpenAI API key is required to proceed. Please check the sidebar for setup instructions.")
        st.stop()
    
    # Main content area
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown('<div class="section-header">📁 Upload Files</div>', unsafe_allow_html=True)
        
        # Excel file upload
        excel_file = st.file_uploader(
            "Upload Excel Master Data",
            type=['xlsx', 'xls'],
            help="Upload your Excel file containing the master data"
        )
        
        # PDF files upload
        pdf_files = st.file_uploader(
            "Upload PDF Files",
            type=['pdf'],
            accept_multiple_files=True,
            help="Select multiple PDF files to validate"
        )
        
        # Display file info
        if excel_file:
            st.success(f"✅ Excel file loaded: {excel_file.name}")
            
            # Preview Excel data
            try:
                df_preview = pd.read_excel(excel_file, dtype={"Patient ID": str})
                st.info(f"📊 Excel contains {len(df_preview)} records with {len(df_preview.columns)} fields")
                
                with st.expander("Preview Excel Data"):
                    st.dataframe(df_preview.head())
                    
            except Exception as e:
                st.error(f"Error reading Excel file: {str(e)}")
        
        if pdf_files:
            st.success(f"✅ {len(pdf_files)} PDF files selected")
            with st.expander("PDF Files"):
                for pdf_file in pdf_files:
                    st.write(f"• {pdf_file.name}")
    
    with col2:
        st.markdown('<div class="section-header">🔧 Validation Controls</div>', unsafe_allow_html=True)
        
        # Validation button
        if st.button("🚀 Start Validation", type="primary", use_container_width=True):
            if not excel_file:
                st.error("❌ Please upload an Excel master data file")
            elif not pdf_files:
                st.error("❌ Please upload at least one PDF file")
            else:
                st.markdown('<div class="section-header">⚡ Processing...</div>', unsafe_allow_html=True)
                
                # Process files
                results_df = process_files(pdf_files, excel_file)
                
                if results_df is not None:
                    # Store results in session state
                    st.session_state.results_df = results_df
                    st.session_state.processing_complete = True
                    
                    st.success("✅ Processing completed!")
    
    # Results section
    if hasattr(st.session_state, 'results_df') and st.session_state.processing_complete:
        st.markdown('<div class="section-header">📈 Results Dashboard</div>', unsafe_allow_html=True)
        
        results_df = st.session_state.results_df
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        total_files = len(results_df)
        clean_files = len(results_df[results_df["Status"] == "Clean"])
        error_files = len(results_df[results_df["Status"] == "Data Error"])
        processing_errors = len(results_df[results_df["Status"] == "Error"])
        
        with col1:
            st.metric("📁 Total Files", total_files)
        
        with col2:
            st.metric("✅ Clean Files", clean_files, delta=f"{clean_files/total_files*100:.1f}%")
        
        with col3:
            st.metric("⚠️ Data Errors", error_files, delta=f"{error_files/total_files*100:.1f}%")
        
        with col4:
            st.metric("❌ Processing Errors", processing_errors, delta=f"{processing_errors/total_files*100:.1f}%")
        
        # Filter options
        st.markdown('<div class="section-header">🔍 Filter Results</div>', unsafe_allow_html=True)
        
        filter_option = st.selectbox(
            "Show:",
            ["All Results", "Only Data Errors", "Only Clean Files", "Only Processing Errors"]
        )
        
        # Filter dataframe
        if filter_option == "Only Data Errors":
            filtered_df = results_df[results_df["Status"] == "Data Error"]
        elif filter_option == "Only Clean Files":
            filtered_df = results_df[results_df["Status"] == "Clean"]
        elif filter_option == "Only Processing Errors":
            filtered_df = results_df[results_df["Status"] == "Error"]
        else:
            filtered_df = results_df
        
        # Results table
        st.markdown('<div class="section-header">📋 Detailed Results</div>', unsafe_allow_html=True)
        
        if len(filtered_df) > 0:
            # Color coding for status
            def color_status(val):
                if val == "Clean":
                    return "background-color: #d4edda"
                elif val == "Data Error":
                    return "background-color: #fff3cd"
                elif val == "Error":
                    return "background-color: #f8d7da"
                return ""
            
            styled_df = filtered_df.style.applymap(color_status, subset=['Status'])
            st.dataframe(styled_df, use_container_width=True)
        else:
            st.info(f"No results found for filter: {filter_option}")
        
        # Download section
        st.markdown('<div class="section-header">📥 Download Reports</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Full report download
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            full_report_filename = f"validation_report_{timestamp}.csv"
            
            csv_full = results_df.to_csv(index=False)
            st.download_button(
                label="📊 Download Full Report",
                data=csv_full,
                file_name=full_report_filename,
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # Errors only report
            errors_df = results_df[results_df["Status"].isin(["Data Error", "Error"])]
            if len(errors_df) > 0:
                errors_filename = f"errors_only_{timestamp}.csv"
                csv_errors = errors_df.to_csv(index=False)
                st.download_button(
                    label="⚠️ Download Errors Only",
                    data=csv_errors,
                    file_name=errors_filename,
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.info("🎉 No errors to download - all files are clean!")
        
        # Summary insights
        if error_files > 0:
            st.markdown('<div class="section-header">🔍 Error Analysis</div>', unsafe_allow_html=True)
            
            error_df = results_df[results_df["Status"] == "Data Error"]
            
            with st.expander(f"View {len(error_df)} files with data errors"):
                for _, row in error_df.iterrows():
                    st.markdown(f"**{row['PDF File']}** (Patient ID: {row['Patient ID']})")
                    st.markdown(f"└─ {row['Data Errors']}")
                    st.markdown("---")

if __name__ == "__main__":
    main()
