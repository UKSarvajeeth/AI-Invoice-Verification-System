import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    SUPPORTED_FORMATS = ['.pdf']
    API_RATE_LIMIT = 60
    UPLOAD_DIR = 'uploads'
    OUTPUT_DIR = 'outputs'
    MASTER_DATA_DIR = 'master_data'
    
    # Create directories if they don't exist
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(MASTER_DATA_DIR, exist_ok=True)
