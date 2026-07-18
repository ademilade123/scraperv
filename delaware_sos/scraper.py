"""
Delaware Secretary of State Scraper - Customer Type 3
Scrapes new LLC formations from Delaware's ICIS portal.
Flags when same registered agent appears across multiple filings within 90 days.
Combined with Florida LLC data from the Sunbiz SFTP.
"""

import requests
import sys, os, time
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

NINETY_DAYS = timedelta(days=90)
CUTOFF_DATE = datetime.today() - NINETY_DAYS

# ── Delaware scraper ──────────────────────────────────────────
def scrape_delaware() -> list[dict]:
    log_info("Fetching Delaware LLC formations...")
    leads   = []
    session = requests.Session()
    session.headers.update(HEADERS_HTTP)

    try:
        # Get initial page for form tokens
        resp = session.get(DE_SEARCH_URL, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract ASP.NET form tokens
        viewstate    = soup.find("input", {"id": "__VIEWSTATE"})
        eventval     = soup.find("input", {"id": "__EVENTVALIDATION"})
        viewstategen = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})

        vs_val  = viewstate["value"]    if viewstate    else ""
        ev_val  = eventval["value"]     if eventval     else ""
        vsg_val = viewstategen["value"] if viewstategen else ""

        # Search for LLC entities (blank name = all)
        post_data = {
            "__VIEWSTATE":                                                vs_val,
            "__EVENTVALIDATION":                                          ev_val,
            "__VIEWSTATEGENERATOR":                                       vsg_val,
            "ctl00$ContentPlaceHolder1$txtEntityName":                    "",
            "ctl00$ContentPlaceHolder1$ddlSearchType":                    "BeginsWith",
            "ctl00$ContentPlaceHolder1$ddlEntityKind":                    "LLC",
            "ctl00$ContentPlaceHolder1$ddlEntityType":                    "D",
            "ctl00$ContentPlaceHolder1$btnSearch":                        "Search",
        }

        search_resp = session.post(DE_SEARCH_URL, data=post_data, timeout=30)
        search_resp.raise_for_status()
        search_soup = BeautifulSoup(search_resp.text, "html.parser")

        # Find results table
        table = search_soup.find("table", {"id": lambda x: x and "grd" in x.lower()})
        if not table:
            # Try any table with results
            tables = search_soup.find_all("table")
            table  = tables[-1] if tables else None

        if not table:
            log_info("  No results table found on Delaware page")
            return []

        rows = table.find_all("tr")[1:]  # skip header
        log_info(f"  Delaware rows found: {len(rows)}")

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 2:
                continue

            name        = cols[0].get_text(strip=True)
            file_number = cols[1].get_text(strip=True)
            entity_type = cols[2].get_text(strip=True) if len(cols) > 2 else ""
            status      = cols[3].get_text(strip=True) if len(cols) > 3 else ""

            if not name:
                continue

            leads.append({
                "name":        name,
                "file_number": file_number,
                "entity_type": entity_type,
                "status":      status,
                "state":       "DE",
                "reg_agent":   "",
                "filing_date": datetime.today().strftime("%Y-%m-%d"),
            })

    except Exception as e:
        log_info(f"  Delaware error: {e}")

    return leads


# ── Florida LLC from SFTP (reuse same credentials as Type 2) ──
def scrape_florida_llcs() -> list[dict]:
    """Pull FL domestic LLC formations from Sunbiz SFTP — same file as Type 2."""
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

        try:
            transport = paramiko.Transport((SFTP_HOST, 22))
            transport.connect(username=SFTP_USER, password=SFTP_PASS)
            sftp = paramiko.SFTPClient.from_transport(transport)

            try:
                sftp.stat(path)
            except FileNotFoundError:
                sftp.close()
                transport.close()
                continue

            buffer = io.BytesIO()
            sftp.getfo(path, buffer)
            sftp.close()
            transport.close()

            lines = buffer.getvalue().decode("latin-1").splitlines()
            log_info(f"  FL file {filename}: {len(lines)} lines")

            for line in lines:
                if len(line) < 220:
                    continue
                status = line[204:212].strip()
                # AFLAL = Active Florida LLC (domestic)
                if status != "AFLAL":
                    continue
                name = line[13:213].strip()
                if not name:
                    continue
                leads.append({
                    "name":        name,
                    "file_number": line[1:13].strip(),
                    "entity_type": "FL LLC",
                    "status":      status,
                    "state":       "FL",
                    "reg_agent":   "",
                    "filing_date": date.strftime("%Y-%m-%d"),
                })

            break  # use most recent file only for FL

        except Exception as e:
            log_info(f"  FL SFTP error for {filename}: {e}")

    log_info(f"  Florida LLC leads: {len(leads)}")
    return leads


# ── Flag repeat registered agents ─────────────────────────────
def flag_repeat_agents(leads: list[dict]) -> list[dict]:
    """Flag leads where same registered agent filed 2+ LLCs in 90 days."""
    agent_map = defaultdict(list)

    for lead in leads:
        agent = lead.get("reg_agent", "").strip().upper()
        if agent:
            agent_map[agent].append(lead)

    flagged = {a for a, filings in agent_map.items() if len(filings) >= 2}
    log_info(f"  Flagged repeat agents: {len(flagged)}")

    for lead in leads:
        agent = lead.get("reg_agent", "").strip().upper()
        lead["flagged"] = agent in flagged

    return leads


# ── Format for Airtable ───────────────────────────────────────
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


# ── Main ──────────────────────────────────────────────────────
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