import os
import pandas as pd
import logging
from typing import List, Dict, Any, Optional
import streamlit as st

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_file_upload(uploaded_file, max_size: int = 10*1024*1024) -> bool:
    """Validate uploaded file size and format"""
    if uploaded_file is None:
        return False
    
    if uploaded_file.size > max_size:
        st.error(f"File size exceeds {max_size/1024/1024}MB limit")
        return False
    
    if not uploaded_file.name.lower().endswith('.pdf'):
        st.error("Only PDF files are supported")
        return False
    
    return True

def save_uploaded_file(uploaded_file, directory: str) -> str:
    """Save uploaded file and return the path"""
    try:
        file_path = os.path.join(directory, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        logger.info(f"File saved: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        raise

def clean_numeric_value(value: Any) -> float:
    """Clean and convert value to numeric"""
    if pd.isna(value):
        return 0.0
    
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        # Remove common formatting characters
        cleaned = value.replace('$', '').replace(',', '').replace(' ', '')
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    
    return 0.0

def format_currency(amount: float) -> str:
    """Format amount as currency"""
    return f"${amount:,.2f}"

def create_summary_stats(discrepancies: List[Dict]) -> Dict:
    """Create summary statistics from discrepancies"""
    if not discrepancies:
        return {
            'total_discrepancies': 0,
            'total_amount_difference': 0,
            'avg_discrepancy': 0,
            'max_discrepancy': 0
        }
    
    amounts = [abs(d.get('amount_difference', 0)) for d in discrepancies]
    
    return {
        'total_discrepancies': len(discrepancies),
        'total_amount_difference': sum(amounts),
        'avg_discrepancy': sum(amounts) / len(amounts) if amounts else 0,
        'max_discrepancy': max(amounts) if amounts else 0
    }
