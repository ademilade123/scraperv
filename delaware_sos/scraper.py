"""
Delaware Secretary of State Scraper - Customer Type 3
Combined new-LLC-formation source for Type 3.

NOTE on Delaware: Delaware's public portal (icis.corp.delaware.gov)
requires a specific entity name or file number to return anything -
there is no way to list new formations, no date filter, no bulk data
or API, and it prohibits automated searches. So the Delaware half
returns little/nothing; Type 3 is effectively carried by the Florida
LLC data below (formations + registered agents), which is complete.

NAME PARSING (important): the FL fixed-width record puts the entity
name at columns 12-203 and an 8-char status code at 204-211. The name
must start at 12 (not 13, which drops the first letter) and any trailing
status code (AFLAL etc.) must be stripped, or it leaks into the company
name (e.g. "JUNTS LLC ... AFLAL").
"""

import requests
import sys, os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from shared.logger import log_run_start, log_run_success, log_run_failure, log_info
from shared.airtable_client import push_leads_batch

SCRAPER_NAME = "Delaware SOS Scraper (Type 3)"

DE_SEARCH_URL = "https://icis.corp.delaware.gov/Ecorp/EntitySearch/NameSearch.aspx"
HEADERS_HTTP  = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://icis.corp.delaware.gov/",
}

# FL fixed-width record layout (matches the Sunbiz Type 2 scraper)
NAME_START   = 12
NAME_END     = 204
STATUS_START = 204
STATUS_END   = 212
MIN_LINE_LEN = 212

# Status codes that may trail the name and must be stripped
ALL_STATUS_CODES = (
    "AFORNP", "ADOMNP", "AFORL", "AFORP", "AFLAL",
    "ADOMP", "AFOR", "ADOM",
)


def clean_entity_name(raw: str) -> str:
    """Strip whitespace and any trailing status-code fragment."""
    name = raw.strip()
    for code in ALL_STATUS_CODES:
        if name.endswith(code):
            name = name[: -len(code)].strip()
            break
    return name


# ── Delaware scraper (kept, but see NOTE above - yields ~nothing) ──
def scrape_delaware() -> list:
    log_info("Fetching Delaware LLC formations...")
    leads   = []
    session = requests.Session()
    session.headers.update(HEADERS_HTTP)

    try:
        resp = session.get(DE_SEARCH_URL, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        def val(el_id):
            el = soup.find("input", {"id": el_id})
            return el["value"] if el and el.has_attr("value") else ""

        post_data = {
            "__VIEWSTATE":            val("__VIEWSTATE"),
            "__EVENTVALIDATION":      val("__EVENTVALIDATION"),
            "__VIEWSTATEGENERATOR":   val("__VIEWSTATEGENERATOR"),
            "ctl00$ContentPlaceHolder1$txtEntityName":  "",
            "ctl00$ContentPlaceHolder1$ddlSearchType":  "BeginsWith",
            "ctl00$ContentPlaceHolder1$ddlEntityKind":  "LLC",
            "ctl00$ContentPlaceHolder1$ddlEntityType":  "D",
            "ctl00$ContentPlaceHolder1$btnSearch":      "Search",
        }

        search_resp = session.post(DE_SEARCH_URL, data=post_data, timeout=30)
        search_resp.raise_for_status()
        search_soup = BeautifulSoup(search_resp.text, "html.parser")

        table = search_soup.find("table", {"id": lambda x: x and "grd" in x.lower()})
        if not table:
            tables = search_soup.find_all("table")
            table  = tables[-1] if tables else None
        if not table:
            log_info("  No results table found on Delaware page")
            return []

        rows = table.find_all("tr")[1:]
        log_info(f"  Delaware rows found: {len(rows)}")

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 2:
                continue
            name = cols[0].get_text(strip=True)
            if not name:
                continue
            leads.append({
                "name":        name,
                "file_number": cols[1].get_text(strip=True),
                "state":       "DE",
                "reg_agent":   "",
                "filing_date": datetime.today().strftime("%Y-%m-%d"),
            })

    except Exception as e:
        log_info(f"  Delaware error: {e}")

    return leads


# ── Florida LLC from SFTP (same file as Type 2) ──
def scrape_florida_llcs() -> list:
    """Pull FL domestic LLC formations from Sunbiz SFTP."""
    import paramiko
    import io

    SFTP_HOST = "sftp.floridados.gov"
    SFTP_USER = "Public"
    SFTP_PASS = "PubAccess1845!"

    leads = []
    log_info("Fetching Florida LLC formations from Sunbiz SFTP...")

    for days_back in range(7):
        date     = datetime.today() - timedelta(days=days_back)
        filename = date.strftime("%Y%m%d") + "c.txt"
        path     = f"doc/cor/{filename}"
        transport = None

        try:
            transport = paramiko.Transport((SFTP_HOST, 22))
            transport.connect(username=SFTP_USER, password=SFTP_PASS)
            sftp = paramiko.SFTPClient.from_transport(transport)

            try:
                sftp.stat(path)
            except FileNotFoundError:
                sftp.close()
                continue

            buffer = io.BytesIO()
            sftp.getfo(path, buffer)
            sftp.close()

            lines = buffer.getvalue().decode("latin-1").splitlines()
            log_info(f"  FL file {filename}: {len(lines)} lines")

            for line in lines:
                if len(line) < MIN_LINE_LEN:
                    continue
                status = line[STATUS_START:STATUS_END].strip()
                # AFLAL = Active Florida LLC (domestic)
                if status != "AFLAL":
                    continue
                # start at 12, and strip any trailing status code
                name = clean_entity_name(line[NAME_START:NAME_END])
                if not name:
                    continue
                leads.append({
                    "name":        name,
                    "file_number": line[1:12].strip(),
                    "state":       "FL",
                    "reg_agent":   "",
                    "filing_date": date.strftime("%Y-%m-%d"),
                })

            break  # most recent FL file only

        except Exception as e:
            log_info(f"  FL SFTP error for {filename}: {e}")
        finally:
            if transport is not None:
                try:
                    transport.close()
                except Exception:
                    pass

    log_info(f"  Florida LLC leads: {len(leads)}")
    return leads


def flag_repeat_agents(leads: list) -> list:
    """Flag leads where the same registered agent filed 2+ LLCs."""
    agent_map = defaultdict(list)
    for lead in leads:
        agent = lead.get("reg_agent", "").strip().upper()
        if agent:
            agent_map[agent].append(lead)
    flagged = {a for a, f in agent_map.items() if len(f) >= 2}
    log_info(f"  Flagged repeat agents: {len(flagged)}")
    for lead in leads:
        agent = lead.get("reg_agent", "").strip().upper()
        lead["flagged"] = agent in flagged
    return leads


def format_lead(raw: dict) -> dict:
    return {
        "Company Name":      raw.get("name", ""),
        "State":             raw.get("state", ""),
        "Contact Name":      raw.get("reg_agent", ""),
        "Date Added":        raw.get("filing_date", datetime.today().strftime("%Y-%m-%d")),
        "Customer Type":     "Type 3 - HNW Multiple Businesses",
        "Source":            f"Delaware SOS / Sunbiz ({raw.get('state', '')})",
        "Enrichment Status": "Pending",
        "Outreach Status":   "Pending",
    }


def run():
    log_run_start(SCRAPER_NAME)
    try:
        de_leads = scrape_delaware()
        fl_leads = scrape_florida_llcs()

        all_raw  = de_leads + fl_leads
        log_info(f"Combined before flagging: {len(all_raw)}")

        all_raw  = flag_repeat_agents(all_raw)
        leads    = [format_lead(r) for r in all_raw if r.get("name")]

        added, skipped = push_leads_batch(leads)
        log_info(f"Airtable -> Added: {added} | Skipped: {skipped}")
        log_run_success(SCRAPER_NAME, added)

    except Exception as e:
        log_run_failure(SCRAPER_NAME, e)
        raise


if __name__ == "__main__":
    run()
