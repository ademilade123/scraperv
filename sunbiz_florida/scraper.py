"""
Sunbiz.org Scraper - Customer Type 2
Downloads daily corporate filings from Florida's official SFTP server.
Official public data with free credentials - no web scraping needed.
Filters for foreign qualification filings (non-US home jurisdiction).

SFTP (public credentials):
  Host:     sftp.floridados.gov
  Username: Public
  Password: PubAccess1845!
  Path:     doc/cor/
  File:     yyyymmddc.txt (daily corporate filings)

Record layout (verified against live files):
  pos 0        Record type (L=LLC, P=Profit, N=NonProfit, M=misc)
  pos 1-11     Document number
  pos 12-203   Entity name (space padded)
  pos 204-211  Status code
                 AFORL / AFORP / AFORNP = Active Foreign (what we want)
                 AFLAL                  = Active Florida LLC (domestic, skip)
                 ADOMP / ADOMNP         = Active Domestic (skip)
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

SFTP_HOST = "sftp.floridados.gov"
SFTP_PORT = 22
SFTP_USER = "Public"
SFTP_PASS = "PubAccess1845!"
SFTP_DIR  = "doc/cor"

LOOKBACK_DAYS = 7

# Status codes that mark an active FOREIGN filing
FOREIGN_STATUS_CODES = ("AFORL", "AFORP", "AFORNP", "AFOR")

# Status codes that may trail the entity name and need stripping
ALL_STATUS_CODES = (
    "AFORNP", "ADOMNP", "AFORL", "AFORP", "AFLAL",
    "ADOMP", "AFOR", "ADOM",
)

# Name field boundaries
NAME_START   = 12
NAME_END     = 204
STATUS_START = 204
STATUS_END   = 212
MIN_LINE_LEN = 212


def get_daily_filename(date: datetime) -> str:
    return f"{date.strftime('%Y%m%d')}c.txt"


def clean_entity_name(raw: str) -> str:
    """Strip whitespace and any trailing status code fragment."""
    name = raw.strip()
    for code in ALL_STATUS_CODES:
        if name.endswith(code):
            name = name[: -len(code)].strip()
            break
    return name


def download_daily_file(date: datetime) -> tuple:
    """
    Fetch one daily file over SFTP.

    Returns (lines, outcome) where outcome is one of:
      "ok"      - file downloaded
      "missing" - server reachable, file not there (weekend/holiday)
      "error"   - could not reach or read the server
    """
    filename    = get_daily_filename(date)
    remote_path = f"{SFTP_DIR}/{filename}"
    log_info(f"  Trying: {remote_path}")

    transport = None
    try:
        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USER, password=SFTP_PASS)
        sftp = paramiko.SFTPClient.from_transport(transport)

        try:
            sftp.stat(remote_path)
        except FileNotFoundError:
            log_info(f"  Not found: {filename} (weekend/holiday)")
            sftp.close()
            return None, "missing"

        log_info(f"  Downloading: {filename}")
        buffer = io.BytesIO()
        sftp.getfo(remote_path, buffer)
        sftp.close()

        lines = buffer.getvalue().decode("latin-1").splitlines()
        log_info(f"  Downloaded {len(lines)} lines")
        return lines, "ok"

    except Exception as e:
        log_info(f"  SFTP error: {e}")
        return None, "error"

    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass


def parse_corporate_file(lines: list, date: datetime) -> list:
    """Extract active foreign filings from one daily file."""
    leads    = []
    date_str = date.strftime("%Y-%m-%d")

    for line in lines:
        if len(line) < MIN_LINE_LEN:
            continue

        status = line[STATUS_START:STATUS_END].strip()
        if not status.startswith(FOREIGN_STATUS_CODES):
            continue

        entity_name = clean_entity_name(line[NAME_START:NAME_END])
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


def scrape_sunbiz() -> list:
    """
    Walk back LOOKBACK_DAYS and collect every foreign filing found.

    Raises if no file could be downloaded at all - that means a
    connectivity or credential problem, not a quiet week, and must
    not be reported as a successful run.
    """
    all_leads  = []
    downloaded = 0
    errors     = 0

    for days_back in range(LOOKBACK_DAYS):
        date           = datetime.today() - timedelta(days=days_back)
        lines, outcome = download_daily_file(date)

        if outcome == "error":
            errors += 1
        elif outcome == "ok" and lines:
            downloaded += 1
            leads = parse_corporate_file(lines, date)
            log_info(f"  {date.strftime('%Y-%m-%d')}: {len(lines)} lines -> {len(leads)} foreign filings")
            all_leads.extend(leads)

    if downloaded == 0:
        raise RuntimeError(
            f"No Sunbiz files downloaded in the last {LOOKBACK_DAYS} days "
            f"({errors} connection errors). Check SFTP connectivity to "
            f"{SFTP_HOST}:{SFTP_PORT} and that outbound port 22 is permitted."
        )

    if errors:
        log_info(f"  WARNING: {errors} of {LOOKBACK_DAYS} days failed to download")

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
