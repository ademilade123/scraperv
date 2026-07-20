"""
SBA.gov Scraper - Customer Type 1
Pulls SBA 7(a) loan approvals filtered by loan size ($500K+),
last 90 days only.

Key detail learned the hard way:
  - Use the PLAIN path (no /en/). The localized /en/ download path
    404s for direct requests; the plain path works.
  - The download FILENAME changes every quarter (as-of-251231 ->
    asof-250331 -> ...), but the RESOURCE ID is stable. The bare
    /download endpoint (no filename) redirects to the current file,
    so we try that first and fall back to dated filenames only if
    it fails.
"""

import requests
import csv
import io
import sys, os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from shared.logger import log_run_start, log_run_success, log_run_failure, log_info
from shared.airtable_client import push_leads_batch

SCRAPER_NAME = "SBA.gov Scraper"

# Stable identifiers - these do NOT change across quarterly refreshes.
DATASET_ID  = "0ff8e8e9-b967-4f4e-987c-6ac78c575087"
RESOURCE_ID = "d67d3ccb-2002-4134-a288-481b51cd3479"

# Plain host path (NO /en/). Ordered list of URLs to try in turn.
BASE = f"https://data.sba.gov/dataset/{DATASET_ID}/resource/{RESOURCE_ID}/download"
CANDIDATE_URLS = [
    # Filename-free endpoint - CKAN serves the current file whatever
    # it's named. Best option; survives quarterly renames.
    BASE,
    # Dated fallbacks in case the bare endpoint doesn't redirect.
    f"{BASE}/foia-7a-fy2020-present-asof-260331.csv",
    f"{BASE}/foia-7a-fy2020-present-asof-250331.csv",
    f"{BASE}/foia-7a-fy2020-present-as-of-251231.csv",
]

HEADERS_HTTP = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/csv,*/*",
    "Referer": "https://data.sba.gov/",
}

MIN_LOAN_AMOUNT = 500_000
CUTOFF_DATE     = datetime.today() - timedelta(days=90)


def parse_amount(value: str) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def parse_date(date_str: str):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def download_csv_text() -> str:
    """
    Try each candidate URL until one returns CSV content.
    Raises if none work.
    """
    last_status = None
    for url in CANDIDATE_URLS:
        try:
            log_info(f"Trying: {url}")
            resp = requests.get(url, headers=HEADERS_HTTP, timeout=120,
                                allow_redirects=True)
            last_status = resp.status_code
            if resp.status_code == 200 and resp.text and "," in resp.text[:500]:
                log_info(f"  OK ({len(resp.content)} bytes) via {resp.url}")
                return resp.text
            log_info(f"  Skipped (status {resp.status_code})")
        except Exception as e:
            log_info(f"  Error: {e}")

    raise RuntimeError(
        f"Could not download SBA CSV from any known URL "
        f"(last status {last_status}). SBA may have changed the "
        f"file path again - check data.sba.gov for the current link."
    )


def scrape_sba() -> list:
    log_info("Downloading SBA CSV...")
    text = download_csv_text()

    rows = list(csv.DictReader(io.StringIO(text)))
    log_info(f"Total rows in CSV: {len(rows)}")
    if not rows:
        raise RuntimeError("SBA CSV downloaded but contained no rows.")

    leads = []
    for row in rows:
        gross_approval = parse_amount(row.get("grossapproval", "0"))
        if gross_approval < MIN_LOAN_AMOUNT:
            continue

        date_str    = row.get("approvaldate", "")
        parsed_date = parse_date(date_str)
        if not parsed_date or parsed_date < CUTOFF_DATE:
            continue

        company = row.get("borrname", "").strip()
        if not company:
            continue

        leads.append({
            "Company Name":      company,
            "State":             row.get("borrstate", "").strip(),
            "Industry/NAICS":    row.get("naicscode", "").strip(),
            "Loan Amount":       str(gross_approval),
            "Date Added":        date_str,
            "Customer Type":     "Type 1 - US Founders",
            "Source":            "SBA.gov",
            "Enrichment Status": "Pending",
            "Outreach Status":   "Pending",
        })

    log_info(f"Found {len(leads)} records from last 90 days matching $500K+")
    return leads


def run():
    log_run_start(SCRAPER_NAME)
    try:
        leads          = scrape_sba()
        added, skipped = push_leads_batch(leads)
        log_info(f"Airtable -> Added: {added} | Skipped: {skipped}")
        log_run_success(SCRAPER_NAME, added)
    except Exception as e:
        log_run_failure(SCRAPER_NAME, e)
        raise


if __name__ == "__main__":
    run()
