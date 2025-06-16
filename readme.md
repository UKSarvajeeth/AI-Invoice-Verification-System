# PDF Data Validator

A Streamlit application that validates PDF documents against Excel master data using OpenAI's AI to identify genuine data discrepancies.

## How It Works

### Core Logic Flow

1. **File Upload & Setup**

   - Users upload an Excel file (master data) and multiple PDF files
   - Application loads OpenAI API key from `.env` file
   - Validates that required files and API key are present
2. **Data Processing**

   ```
   For each PDF file:
   → Extract text using PyMuPDF
   → Find Patient ID using regex pattern
   → Match with Excel row by Patient ID
   → Send both datasets to OpenAI for comparison
   → Record results and errors
   ```
3. **AI-Powered Comparison**

   - Sends PDF text and Excel row data to GPT-4
   - AI compares all fields intelligently
   - Ignores formatting differences, focuses on actual data errors
   - Returns only genuine discrepancies

### Key Functions

- **`extract_text_from_pdf()`**: Converts PDF to readable text
- **`find_patient_id()`**: Extracts Patient ID using regex: `(?:Patient\s*ID|ID)\s*[:\-]?\s*(\d+)`
- **`compare_with_gpt()`**: Sends data to OpenAI for smart comparison
- **`process_files()`**: Main processing pipeline with error handling

### Smart Filtering Logic

The AI is instructed to:

- **Ignore**: Date formats, text formatting, case differences, missing fields
- **Report**: Different names, insurance providers, dates, amounts

### Output

- Real-time dashboard with metrics
- Filterable results table
- Downloadable CSV reports (full or errors-only)

## Installation

1. Install dependencies:

```bash
pip install streamlit pandas openpyxl PyMuPDF openai python-dotenv
```

2. Create `.env` file:

```
OPENAI_API_KEY=sk-your-api-key-here
```

3. Run application:

```bash
streamlit run pdf_validator.py
```

## File Requirements

- **Excel**: Must have "Patient ID" column
- **PDFs**: Must contain "Patient ID: [number]" or "ID: [number]"

The application handles the rest automatically, providing a user-friendly interface for bulk PDF validation.
