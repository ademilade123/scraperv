import logging
import os
import sys
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'pipeline.log')

# Fix Windows Unicode issue - force UTF-8 on file, safe chars on console
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
console_handler = logging.StreamHandler(sys.stdout)

# Force stdout to UTF-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[file_handler, console_handler]
)

logger = logging.getLogger('omar_pipeline')


def log_run_start(scraper_name: str):
    logger.info(f"========== START: {scraper_name} ==========")

def log_run_success(scraper_name: str, records_added: int):
    logger.info(f"SUCCESS: {scraper_name} | Records added: {records_added}")
    logger.info(f"========== END: {scraper_name} ==========\n")

import traceback

def log_run_failure(scraper_name: str, error: Exception):
    logger.error(f"FAILED: {scraper_name} | Error: {str(error)}")
    logger.error(traceback.format_exc())
    logger.error(f"========== END (with errors): {scraper_name} ==========\n")

def log_duplicate(scraper_name: str, company_name: str):
    logger.info(f"DUPLICATE SKIPPED: {scraper_name} | Company: {company_name}")

def log_info(message: str):
    # Replace unicode symbols with ASCII safe versions for Windows console
    message = message.replace('→', '->').replace('✅', '[OK]').replace('❌', '[FAIL]')
    logger.info(message)