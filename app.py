import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import tempfile
import shutil

from invoice_processor import InvoiceProcessor
from utils import validate_file_upload, save_uploaded_file, create_summary_stats, format_currency
from config import Config

# Page configuration
st.set_page_config(
    page_title="AI Invoice Verification System",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    """Main Streamlit application"""
    
    # Title and description
    st.title("🤖 AI Invoice Verification System")
    st.markdown("""
    **Automated Invoice Data Verification using AI**
    
    Upload your PDF invoices and master data Excel file to automatically detect pricing discrepancies 
    and generate comprehensive reports.
    """)
    
    # Sidebar configuration
    st.sidebar.title("Configuration")
    st.sidebar.markdown("---")
    
    # Check if API key is configured
    if not Config.OPENAI_API_KEY:
        st.error("⚠️ OpenAI API key not found! Please check your .env file.")
        st.stop()
    
    st.sidebar.success("✅ OpenAI API configured")
    
    # File upload section
    st.header("📁 File Upload")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("PDF Invoices")
        uploaded_pdfs = st.file_uploader(
            "Upload PDF invoice files",
            type=['pdf'],
            accept_multiple_files=True,
            help="Upload one or more PDF invoices to process"
        )
    
    with col2:
        st.subheader("Master Data")
        master_excel = st.file_uploader(
            "Upload master data Excel file",
            type=['xlsx', 'xls'],
            help="Upload the Excel file containing master data for comparison"
        )
    
    # Processing section
    if uploaded_pdfs and master_excel:
        st.header("🔄 Processing")
        
        if st.button("🚀 Start Processing", type="primary"):
            try:
                with st.spinner("Initializing processor..."):
                    processor = InvoiceProcessor()
                
                # Create temporary directories
                temp_dir = tempfile.mkdtemp()
                pdf_paths = []
                
                # Save uploaded files
                with st.spinner("Saving uploaded files..."):
                    # Save PDF files
                    for pdf_file in uploaded_pdfs:
                        if validate_file_upload(pdf_file):
                            pdf_path = os.path.join(temp_dir, pdf_file.name)
                            with open(pdf_path, "wb") as f:
                                f.write(pdf_file.getbuffer())
                            pdf_paths.append(pdf_path)
                    
                    # Save master Excel file
                    master_path = os.path.join(temp_dir, master_excel.name)
                    with open(master_path, "wb") as f:
                        f.write(master_excel.getbuffer())
                
                # Process invoices
                st.info("Processing invoices with AI analysis...")
                discrepancies, discrepancies_df = processor.process_invoice_batch(
                    pdf_paths, master_path
                )
                
                # Generate report
                output_filename = f"discrepancy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                output_path = os.path.join(Config.OUTPUT_DIR, output_filename)
                
                processor.generate_report(discrepancies, output_path)
                
                # Display results
                st.success(f"✅ Processing completed! Found {len(discrepancies)} discrepancies.")
                
                # Results section
                st.header("📊 Results")
                
                if discrepancies:
                    # Summary statistics
                    col1, col2, col3, col4 = st.columns(4)
                    
                    summary_stats = create_summary_stats(discrepancies)
                    
                    with col1:
                        st.metric("Total Discrepancies", summary_stats['total_discrepancies'])
                    
                    with col2:
                        st.metric("Total Amount Difference", 
                                format_currency(summary_stats['total_amount_difference']))
                    
                    with col3:
                        st.metric("Average Discrepancy", 
                                format_currency(summary_stats['avg_discrepancy']))
                    
                    with col4:
                        st.metric("Maximum Discrepancy", 
                                format_currency(summary_stats['max_discrepancy']))
                    
                    # Discrepancies table
                    st.subheader("🔍 Detailed Discrepancies")
                    st.dataframe(discrepancies_df, use_container_width=True)
                    
                    # Visualization
                    if len(discrepancies_df) > 0 and 'discrepancy_type' in discrepancies_df.columns:
                        st.subheader("📈 Discrepancy Analysis")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            # Discrepancy types pie chart
                            disc_counts = discrepancies_df['discrepancy_type'].value_counts()
                            fig_pie = px.pie(
                                values=disc_counts.values,
                                names=disc_counts.index,
                                title="Discrepancy Types Distribution"
                            )
                            st.plotly_chart(fig_pie, use_container_width=True)
                        
                        with col2:
                            # Amount differences bar chart (if amount_difference exists)
                            if 'amount_difference' in discrepancies_df.columns:
                                # Convert amount_difference to numeric, handling non-numeric values
                                discrepancies_df['amount_diff_numeric'] = pd.to_numeric(
                                    discrepancies_df['amount_difference'], errors='coerce'
                                ).fillna(0)
                                
                                fig_bar = px.bar(
                                    discrepancies_df.head(10),
                                    x='item_name',
                                    y='amount_diff_numeric',
                                    title="Top 10 Discrepancies by Amount",
                                    labels={'amount_diff_numeric': 'Amount Difference ($)'}
                                )
                                fig_bar.update_xaxis(tickangle=45)
                                st.plotly_chart(fig_bar, use_container_width=True)
                
                else:
                    st.info("🎉 No discrepancies found! All invoice data matches the master data.")
                
                # Download section
                st.header("💾 Download Report")
                
                try:
                    with open(output_path, "rb") as f:
                        st.download_button(
                            label="📥 Download Excel Report",
                            data=f.read(),
                            file_name=output_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            type="primary"
                        )
                except FileNotFoundError:
                    st.error("Report file not found. Please try processing again.")
                
                # Cleanup temporary files
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
                    
            except Exception as e:
                st.error(f"❌ Error during processing: {str(e)}")
                st.exception(e)
    
    # Instructions section
    with st.expander("📋 Instructions", expanded=False):
        st.markdown("""
        ### How to use this system:
        
        1. **Upload PDF Invoices**: Select one or more PDF files containing invoice data
        2. **Upload Master Data**: Select an Excel file containing your master pricing data
        3. **Start Processing**: Click the "Start Processing" button to begin AI analysis
        4. **Review Results**: Examine the discrepancies found by the AI system
        5. **Download Report**: Get a detailed Excel report with all findings
        
        ### Supported File Formats:
        - **PDF**: Invoice files in PDF format with tables or structured text
        - **Excel**: Master data in .xlsx or .xls format
        
        ### What the system detects:
        - Price discrepancies between invoices and master data
        - Missing items in master data
        - Quantity mismatches
        - Other data inconsistencies
        """)
    
    # Technical details
    with st.expander("🔧 Technical Details", expanded=False):
        st.markdown(f"""
        ### System Configuration:
        - **AI Model**: OpenAI GPT-3.5 Turbo
        - **PDF Processing**: pdfplumber library
        - **Data Processing**: pandas
        - **Maximum File Size**: {Config.MAX_FILE_SIZE / 1024 / 1024}MB
        - **Supported Formats**: {', '.join(Config.SUPPORTED_FORMATS)}
        
        ### Processing Steps:
        1. Extract table data from PDF invoices
        2. Load and validate master data from Excel
        3. Use AI to compare data and identify discrepancies
        4. Generate comprehensive Excel report
        5. Provide statistical analysis and visualizations
        """)

if __name__ == "__main__":
    main()
