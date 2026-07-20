"""
SBA.gov Scraper - Customer Type 1
Pulls SBA 7(a) loan approvals filtered by loan size ($500K+),
last 90 days only.

IMPORTANT - path history:
  SBA rebuilt their open-data portal (now Drupal-based). The old
  CKAN-style URL:
    /dataset/<id>/resource/<id>/download/foia-7a-...csv
  is DEAD. Files now live at:
    /sites/default/files/uploaded_resources/FOIA_7a_FY2020_Present_asof_<YYMMDD>.csv
  The "asof" date advances each quarter, so we resolve the current
  link from the dataset page and only fall back to a hardcoded URL if
  that scrape fails.
"""

import requests
import csv
import io
import re
import sys, os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from shared.logger import log_run_start, log_run_success, log_run_failure, log_info
from shared.airtable_client import push_leads_batch

SCRAPER_NAME = "SBA.gov Scraper"

# Dataset landing page - lists the current file links.
SBA_DATASET_PAGE = "https://data.sba.gov/dataset/7-a-504-foia"

# Known-good fallback (as of March 31 2026 refresh). Update if the
# page scrape ever fails AND SBA has published a newer quarter.
SBA_FALLBACK_URL = (
    "https://data.sba.gov/sites/default/files/uploaded_resources/"
    "FOIA_7a_FY2020_Present_asof_260331.csv"
)

HEADERS_HTTP = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,text/csv,*/*",
    "Accept-Language": "en-US,en;q=0.9",
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


def resolve_csv_url() -> str:
    """
    Scrape the dataset page for the current 7(a) FY2020-Present CSV
    link. Matches the FY2020 + Present file specifically (not 504,
    not the FY2010-2019 or older files). Falls back to the hardcoded
    URL if scraping fails or no match is found.
    """
    try:
        log_info("Resolving current SBA 7(a) file from dataset page...")
        resp = requests.get(SBA_DATASET_PAGE, headers=HEADERS_HTTP, timeout=60)
        resp.raise_for_status()

        # Find CSV links that are the 7(a) FY2020-Present file.
        # Pattern is tolerant of hyphen/underscore and casing changes.
        links = re.findall(r'href="([^"]+\.csv)"', resp.text, re.I)
        for link in links:
            low = link.lower()
            if "7a" in low and "2020" in low and "present" in low and "504" not in low:
                url = link if link.startswith("http") else "https://data.sba.gov" + link
                log_info(f"Resolved current file: {url}")
                return url

        log_info("7(a) FY2020-Present link not found on page; using fallback.")
    except Exception as e:
        log_info(f"Page scrape failed ({e}); using fallback URL.")

    return SBA_FALLBACK_URL


def scrape_sba() -> list:
    csv_url = resolve_csv_url()

    log_info("Downloading SBA CSV...")
    resp = requests.get(csv_url, headers=HEADERS_HTTP, timeout=180)
    resp.raise_for_status()

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    log_info(f"Total rows in CSV: {len(rows)}")
    if not rows:
        raise RuntimeError("SBA CSV downloaded but contained no rows.")

    # Column names are lowercase and space-free in the SBA file.
    # Guard against a format change: if expected columns are missing,
    # fail loudly rather than silently pushing zero leads.
    sample = rows[0]
    if "grossapproval" not in sample or "borrname" not in sample:
        raise RuntimeError(
            f"SBA CSV columns not as expected. Got: {list(sample.keys())[:10]}"
        )

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
