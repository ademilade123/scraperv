"""
SBA.gov Scraper - Customer Type 1
Pulls SBA 7(a) loan approvals filtered by loan size ($500K+),
last 90 days only.

SBA refreshes the FOIA files quarterly and the download filename
carries the "as of" date (e.g. ...asof-260331.csv), so any hardcoded
URL 404s after each refresh. To survive that, we scrape the dataset
landing page and pull the current FY2020-Present download link by its
stable resource ID, then download whatever file it points to.
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

# Dataset landing page (CKAN). Stable.
SBA_DATASET_PAGE = "https://data.sba.gov/en/dataset/7-a-504-foia"

# Stable resource ID for the 7(a) FY2020-Present file. The filename
# changes each quarter but this ID does not.
SBA_RESOURCE_ID = "d67d3ccb-2002-4134-a288-481b51cd3479"

# Last-resort direct URL if page scraping fails. Update the date if
# SBA ever changes the pattern again.
SBA_FALLBACK_URL = (
    "https://data.sba.gov/en/dataset/0ff8e8e9-b967-4f4e-987c-6ac78c575087"
    f"/resource/{SBA_RESOURCE_ID}"
    "/download/foia-7a-fy2020-present-asof-260331.csv"
)

HEADERS_HTTP = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://data.sba.gov/",
}

MIN_LOAN_AMOUNT = 500_000
CUTOFF_DATE     = datetime.today() - timedelta(days=90)  # last 90 days only


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
    Scrape the dataset page for the current FY2020-Present download
    link, matched by the stable resource ID. Falls back to the
    hardcoded URL if scraping fails.
    """
    try:
        log_info("Resolving current SBA file from dataset page...")
        resp = requests.get(SBA_DATASET_PAGE, headers=HEADERS_HTTP, timeout=60)
        resp.raise_for_status()

        # Find the download link that includes our resource ID.
        pattern = rf'href="([^"]*{re.escape(SBA_RESOURCE_ID)}/download/[^"]+\.csv)"'
        matches = re.findall(pattern, resp.text, re.I)

        if matches:
            url = matches[0]
            if url.startswith("/"):
                url = "https://data.sba.gov" + url
            log_info(f"Resolved current file: {url}")
            return url

        log_info("Resource link not found on page; using fallback URL.")
    except Exception as e:
        log_info(f"Page scrape failed ({e}); using fallback URL.")

    return SBA_FALLBACK_URL


def scrape_sba() -> list:
    csv_url = resolve_csv_url()

    log_info("Downloading SBA CSV...")
    resp = requests.get(csv_url, headers=HEADERS_HTTP, timeout=120)
    resp.raise_for_status()

    rows = list(csv.DictReader(io.StringIO(resp.text)))
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
