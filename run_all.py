"""
Master Runner — runs all 3 scrapers in sequence.
This is the only file scheduled on PythonAnywhere.
Scheduled daily; only does real work on Mondays.
"""

import sys, os
from datetime import datetime
from dotenv import load_dotenv

sys.path.append(os.path.dirname(__file__))
load_dotenv()

from shared.logger import log_info, log_run_start, log_run_success, log_run_failure

import sba_gov.scraper        as sba
import sunbiz_florida.scraper as sunbiz
import delaware_sos.scraper   as delaware

SCRAPERS = [
    ("SBA.gov",      sba.run),
    ("Sunbiz FL",    sunbiz.run),
    ("Delaware SOS", delaware.run),
]


def run_all():
    # PythonAnywhere only schedules daily — do the real work on Mondays only
    if datetime.today().weekday() != 0:   # 0 = Monday
        log_info("Not Monday — skipping this run.")
        return

    log_run_start("MASTER PIPELINE")
    results = {}

    for name, run_fn in SCRAPERS:
        try:
            log_info(f"--- Starting: {name} ---")
            run_fn()
            results[name] = "[OK] Success"
        except Exception as e:
            results[name] = f"[FAIL] {e}"
            log_info(f"--- {name} failed, continuing to next scraper ---")

    log_info("=" * 50)
    log_info("PIPELINE SUMMARY")
    log_info("=" * 50)
    for name, status in results.items():
        log_info(f"  {name}: {status}")
    log_info("=" * 50)


if __name__ == "__main__":
    run_all()
