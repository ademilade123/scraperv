"""
Sunbiz.org Scraper - Customer Type 2
Downloads daily corporate filings from Florida's official SFTP server.
No scraping needed - official public data with free credentials.
Filters for foreign qualification filings where jurisdiction is non-US.

SFTP Credentials (public):
  Host:     sftp.floridados.gov
  Username: Public
  Password: PubAccess1845!
  Path:     /doc/cor/
  File:     yyyymmddc.txt (daily corporate filings)
"""

import sys, os, io
from datetime import datetime, timedelta
from dotenv import load_dotenv
import paramiko

load_dotenv()
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from shared.logger import log_run_start, log_run_success, log_run_failure, log_info
from shared.airtable_client import push_leads_batch

SCRAPER_NAME = "Sunbiz.org Scraper (Type 2)"

SFTP_HOST    = "sftp.floridados.gov"
SFTP_USER    = "Public"
SFTP_PASS    = "PubAccess1845!"
SFTP_PATH    = "/doc/cor"

# Foreign entity type codes in the Florida data file
FOREIGN_CODES = {"FP", "FN", "FL"}  # Foreign Profit, Foreign Non-Profit, Foreign LLC

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID",
    "IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS",
    "MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK",
    "OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV",
    "WI","WY","DC","US","USA"
}


def is_foreign_jurisdiction(state_code: str) -> bool:
    return state_code.upper().strip() not in US_STATES and len(state_code.strip()) > 0


def get_daily_filename(date: datetime) -> str:
    return f"{date.strftime('%Y%m%d')}c.txt"


def download_daily_file(date: datetime) -> list[str] | None:
    """Download daily corporate filings file via SFTP (paramiko)."""
    filename    = get_daily_filename(date)
    # Files live directly in doc/cor/ — no year subfolder
    remote_path = f"doc/cor/{filename}"
    log_info(f"  Trying: {remote_path}")

    try:
        transport = paramiko.Transport((SFTP_HOST, 22))
        transport.connect(username=SFTP_USER, password=SFTP_PASS)
        sftp = paramiko.SFTPClient.from_transport(transport)

        try:
            sftp.stat(remote_path)
        except FileNotFoundError:
            log_info(f"  Not found: {filename} (holiday/weekend)")
            sftp.close()
            transport.close()
            return None

        log_info(f"  Downloading: {filename}")
        buffer = io.BytesIO()
        sftp.getfo(remote_path, buffer)
        sftp.close()
        transport.close()

        content = buffer.getvalue().decode("latin-1")
        lines   = content.splitlines()
        log_info(f"  Downloaded {len(lines)} lines")
        return lines

    except Exception as e:
        log_info(f"  SFTP error: {e}")
        return None


def parse_corporate_file(lines: list[str], date: datetime) -> list[dict]:
    """
    Parse Florida corporate filing records.
    Confirmed format:
      pos 0:      Record type (L=LLC, P=Profit, N=NonProfit)
      pos 1-12:   Document Number
      pos 13-212: Entity Name (200 chars)
      pos 204-212: Status code
        AFORL = Active Foreign LLC
        AFORP = Active Foreign Profit
        AFORNP = Active Foreign Non-Profit
        AFLAL = Active FL LLC (domestic)
        ADOMP = Active Domestic Profit (skip)
    """
    FOREIGN_CODES = {"AFORL", "AFORP", "AFORNP", "AFOR"}
    leads    = []
    date_str = date.strftime("%Y-%m-%d")

    for line in lines:
        if len(line) < 220:
            continue

        status = line[204:212].strip()

        # Only keep foreign filings
        if not any(status.startswith(code) for code in FOREIGN_CODES):
            continue

        doc_number  = line[1:13].strip()
        entity_name = line[13:213].strip()

        if not entity_name:
            continue

        leads.append({
            "Company Name":      entity_name,
            "State":             "FL",
            "Contact Name":      "",
            "Date Added":        date_str,
            "Customer Type":     "Type 2 - Foreign Companies",
            "Source":            "Sunbiz.org",
            "Enrichment Status": "Pending",
            "Outreach Status":   "Pending",
        })

    return leads


def scrape_sunbiz() -> list[dict]:
    """Try last 7 days and collect ALL foreign filings found."""
    all_leads = []

    for days_back in range(7):
        date  = datetime.today() - timedelta(days=days_back)
        lines = download_daily_file(date)

        if lines:
            leads = parse_corporate_file(lines, date)
            log_info(f"  {date.strftime('%Y-%m-%d')}: {len(lines)} lines -> {len(leads)} foreign filings")
            all_leads.extend(leads)
            # Don't break — collect all days this week

    log_info(f"Total foreign leads this week: {len(all_leads)}")
    return all_leads


def run():
    log_run_start(SCRAPER_NAME)
    try:
        leads          = scrape_sunbiz()
        added, skipped = push_leads_batch(leads)
        log_info(f"Airtable -> Added: {added} | Skipped: {skipped}")
        log_run_success(SCRAPER_NAME, added)
    except Exception as e:
        log_run_failure(SCRAPER_NAME, e)
        raise

if __name__ == "__main__":
    run()