"""
Master Runner — runs all 3 scrapers in sequence.
This is the only file scheduled on PythonAnywhere.
"""

import sys, os
sys.path.append(os.path.dirname(__file__))

from shared.logger import log_info, log_run_start, log_run_success, log_run_failure

import sba_gov.scraper       as sba
import sunbiz_florida.scraper as sunbiz
import delaware_sos.scraper   as delaware
from dotenv import load_dotenv
load_dotenv()

SCRAPERS = [
    ("SBA.gov",       sba.run),
    ("Sunbiz FL",     sunbiz.run),
    ("Delaware SOS",  delaware.run),
]


def run_all():
    log_run_start("MASTER PIPELINE")
    results = {}

    for name, run_fn in SCRAPERS:
        try:
            log_info(f"--- Starting: {name} ---")
            run_fn()
            results[name] = "✅ Success"
        except Exception as e:
            results[name] = f"❌ Failed: {e}"
            log_info(f"--- {name} failed, continuing to next scraper ---")

    # Final summary
    log_info("=" * 50)
    log_info("PIPELINE SUMMARY")
    log_info("=" * 50)
    for name, status in results.items():
        log_info(f"  {name}: {status}")
    log_info("=" * 50)


if __name__ == "__main__":
    run_all()