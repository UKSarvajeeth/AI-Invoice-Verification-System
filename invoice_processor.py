import pandas as pd
import pdfplumber
import openai
from openai import OpenAI
import json
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from config import Config
import streamlit as st

logger = logging.getLogger(__name__)

class InvoiceProcessor:
    def __init__(self):
        if not Config.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not found. Please check your .env file.")
        
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.master_data = None

    def extract_pdf_data(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract data from PDF invoice using pdfplumber"""
        try:
            extracted_data = []
            
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    # Extract tables
                    tables = page.extract_tables()
                    
                    if tables:
                        for table_num, table in enumerate(tables):
                            if len(table) > 1:  # Has header and data
                                df = pd.DataFrame(table[1:], columns=table[0])
                                
                                # Clean column names
                                df.columns = [str(col).strip().lower() if col else f'col_{i}' 
                                            for i, col in enumerate(df.columns)]
                                
                                # Add metadata
                                df['source_page'] = page_num + 1
                                df['source_table'] = table_num + 1
                                df['source_file'] = pdf_path.split('/')[-1]
                                
                                extracted_data.append(df)
                    
                    # If no tables found, try to extract text and parse
                    if not tables:
                        text = page.extract_text()
                        if text:
                            parsed_data = self._parse_text_for_invoice_data(text)
                            if parsed_data:
                                df = pd.DataFrame(parsed_data)
                                df['source_page'] = page_num + 1
                                df['source_file'] = pdf_path.split('/')[-1]
                                extracted_data.append(df)
            
            logger.info(f"Extracted {len(extracted_data)} tables from {pdf_path}")
            return extracted_data
        
        except Exception as e:
            logger.error(f"Error extracting PDF data from {pdf_path}: {e}")
            raise

    def _parse_text_for_invoice_data(self, text: str) -> List[Dict]:
        """Parse text content for invoice data using regex patterns"""
        invoice_data = []
        
        # Common patterns for invoice items
        patterns = [
            r'(\w+.*?)\s+(\d+)\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.?\d*)',  # item qty price total
            r'(\w+.*?)\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.?\d*)',  # item price total
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            for match in matches:
                if len(match) == 4:
                    invoice_data.append({
                        'item': match[0].strip(),
                        'quantity': match[1].strip(),
                        'unit_price': match[2].replace(',', ''),
                        'total_price': match[3].replace(',', '')
                    })
                elif len(match) == 3:
                    invoice_data.append({
                        'item': match[0].strip(),
                        'unit_price': match[1].replace(',', ''),
                        'total_price': match[2].replace(',', '')
                    })
        
        return invoice_data

    def load_master_data(self, excel_path: str) -> pd.DataFrame:
        """Load master data from Excel file"""
        try:
            df = pd.read_excel(excel_path)
            
            # Clean column names
            df.columns = [str(col).strip().lower() if col else f'col_{i}' 
                         for i, col in enumerate(df.columns)]
            
            # Store for later use
            self.master_data = df
            logger.info(f"Loaded master data with {len(df)} records")
            return df
        
        except Exception as e:
            logger.error(f"Error loading master data from {excel_path}: {e}")
            raise

    def compare_data_with_ai(self, invoice_data: pd.DataFrame, master_data: pd.DataFrame) -> List[Dict]:
        """Compare invoice data with master data using OpenAI"""
        try:
            discrepancies = []
            
            # Convert dataframes to string for AI processing
            invoice_str = invoice_data.to_string(index=False)
            master_str = master_data.head(20).to_string(index=False)  # Limit master data for token efficiency
            
            prompt = f"""
            You are a financial data analyst. Compare the following invoice data with the master data and identify any discrepancies in pricing, quantities, or item details.

            INVOICE DATA:
            {invoice_str}

            MASTER DATA (sample):
            {master_str}

            Please identify discrepancies and return them in this JSON format:
            {{
                "discrepancies": [
                    {{
                        "item_name": "item name",
                        "discrepancy_type": "price/quantity/missing_item",
                        "invoice_value": "value from invoice",
                        "master_value": "value from master data",
                        "amount_difference": "numerical difference",
                        "description": "brief description of the discrepancy"
                    }}
                ]
            }}

            Focus on:
            1. Price differences for the same items
            2. Quantity discrepancies
            3. Items in invoice but not in master data
            4. Significant variations that need attention

            Return only the JSON response.
            """

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a precise financial data analyst. Always return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )

            # Parse the AI response
            ai_response = response.choices[0].message.content.strip()
            
            # Try to extract JSON from the response
            try:
                # Look for JSON in the response
                json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    result = json.loads(json_str)
                    discrepancies = result.get('discrepancies', [])
                else:
                    logger.warning("No JSON found in AI response")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing AI response as JSON: {e}")
                logger.error(f"AI Response: {ai_response}")
            
            return discrepancies

        except Exception as e:
            logger.error(f"Error in AI comparison: {e}")
            return []

    def process_invoice_batch(self, pdf_paths: List[str], master_data_path: str) -> Tuple[List[Dict], pd.DataFrame]:
        """Process multiple invoices and return consolidated results"""
        try:
            # Load master data
            master_data = self.load_master_data(master_data_path)
            all_discrepancies = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, pdf_path in enumerate(pdf_paths):
                try:
                    status_text.text(f'Processing {pdf_path.split("/")[-1]}...')
                    
                    # Extract data from current PDF
                    invoice_tables = self.extract_pdf_data(pdf_path)
                    
                    # Process each table in the invoice
                    for table in invoice_tables:
                        discrepancies = self.compare_data_with_ai(table, master_data)
                        
                        # Add source information to each discrepancy
                        for disc in discrepancies:
                            disc['source_file'] = pdf_path.split('/')[-1]
                            
                        all_discrepancies.extend(discrepancies)
                    
                except Exception as e:
                    logger.error(f"Error processing {pdf_path}: {e}")
                    st.error(f"Error processing {pdf_path.split('/')[-1]}: {str(e)}")
                
                # Update progress
                progress_bar.progress((i + 1) / len(pdf_paths))
            
            status_text.text('Processing complete!')
            
            # Convert discrepancies to DataFrame
            if all_discrepancies:
                discrepancies_df = pd.DataFrame(all_discrepancies)
            else:
                discrepancies_df = pd.DataFrame()
            
            return all_discrepancies, discrepancies_df

        except Exception as e:
            logger.error(f"Error in batch processing: {e}")
            raise

    def generate_report(self, discrepancies: List[Dict], output_path: str) -> str:
        """Generate Excel report with discrepancies"""
        try:
            if not discrepancies:
                # Create empty report
                df = pd.DataFrame({
                    'Message': ['No discrepancies found in the processed invoices.']
                })
            else:
                df = pd.DataFrame(discrepancies)
            
            # Write to Excel with formatting
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Discrepancies', index=False)
                
                # Add summary sheet if there are discrepancies
                if discrepancies:
                    summary_data = {
                        'Metric': ['Total Discrepancies', 'Total Amount Difference', 'Average Discrepancy'],
                        'Value': [
                            len(discrepancies),
                            sum(abs(float(d.get('amount_difference', 0))) for d in discrepancies if str(d.get('amount_difference', 0)).replace('.', '').replace('-', '').isdigit()),
                            sum(abs(float(d.get('amount_difference', 0))) for d in discrepancies if str(d.get('amount_difference', 0)).replace('.', '').replace('-', '').isdigit()) / len(discrepancies)
                        ]
                    }
                    summary_df = pd.DataFrame(summary_data)
                    summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            logger.info(f"Report generated: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error generating report: {e}")
            raise
