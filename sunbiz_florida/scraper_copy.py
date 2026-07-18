"""
Sunbiz.org Scraper - Customer Type 2
Pulls Florida foreign qualification filings where
home jurisdiction is non-US (foreign companies expanding into the US).
"""

import requests
import sys, os, time
from datetime import datetime
from bs4 import BeautifulSoup

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from shared.logger import log_run_start, log_run_success, log_run_failure, log_info
from shared.airtable_client import push_leads_batch

SCRAPER_NAME = "Sunbiz.org Scraper (Type 2)"

SUNBIZ_BASE    = "https://search.sunbiz.org"
SEARCH_URL     = f"{SUNBIZ_BASE}/Inquiry/CorporationSearch/SearchResults"
DETAIL_URL     = f"{SUNBIZ_BASE}/Inquiry/CorporationSearch/SearchResultDetail"

# Full browser headers to avoid 403
HEADERS_HTTP = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Referer":         "https://search.sunbiz.org/",
}

FOREIGN_ENTITY_TYPES = ["FOREIGN PROFIT", "FOREIGN NON PROFIT", "FOREIGN LLC"]

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID",
    "IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS",
    "MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK",
    "OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV",
    "WI","WY","DC"
}


def is_foreign_jurisdiction(jurisdiction: str) -> bool:
    j = jurisdiction.upper().strip()
    if not j:
        return False
    if j in US_STATES or "FLORIDA" in j or "UNITED STATES" in j:
        return False
    return True


def make_session() -> requests.Session:
    """Create a session that mimics a real browser visit."""
    session = requests.Session()
    session.headers.update(HEADERS_HTTP)
    # Visit homepage first to get cookies
    try:
        session.get(SUNBIZ_BASE, timeout=15)
        time.sleep(1)
    except Exception:
        pass
    return session


def fetch_search_results(session: requests.Session, entity_type: str) -> list[dict]:
    params = {
        "SearchTerm":       "",
        "SearchType":       "EntityName",
        "SearchStatus":     "Active",
        "SearchEntityType": entity_type,
        "ListPage":         1,
        "SearchActionType": "GetList",
    }
    resp = session.get(SEARCH_URL, params=params, timeout=30)
    resp.raise_for_status()

    soup    = BeautifulSoup(resp.text, "html.parser")
    results = []

    for row in soup.select("table.search-results tr")[1:]:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        link = cols[0].find("a")
        results.append({
            "name":        cols[0].get_text(strip=True),
            "doc_number":  cols[1].get_text(strip=True),
            "status":      cols[2].get_text(strip=True),
            "filing_date": cols[3].get_text(strip=True) if len(cols) > 3 else "",
            "detail_url":  SUNBIZ_BASE + link["href"] if link and link.get("href") else "",
        })
    return results


def fetch_company_detail(session: requests.Session, detail_url: str) -> dict:
    if not detail_url:
        return {}
    resp = session.get(detail_url, timeout=30)
    resp.raise_for_status()
    soup   = BeautifulSoup(resp.text, "html.parser")
    detail = {}
    for span in soup.select("span.label"):
        label = span.get_text(strip=True).replace(":", "").strip()
        val   = span.find_next_sibling("span")
        detail[label] = val.get_text(strip=True) if val else ""
    return detail


def scrape_sunbiz() -> list[dict]:
    session = make_session()
    leads   = []

    for entity_type in FOREIGN_ENTITY_TYPES:
        log_info(f"Fetching: {entity_type}")
        try:
            results = fetch_search_results(session, entity_type)
            log_info(f"  Found {len(results)} results")

            for company in results:
                time.sleep(0.8)
                try:
                    detail       = fetch_company_detail(session, company.get("detail_url", ""))
                    jurisdiction = detail.get("State of Formation", detail.get("Jurisdiction", ""))

                    if not is_foreign_jurisdiction(jurisdiction):
                        continue

                    leads.append({
                        "Company Name":      company["name"],
                        "State":             "FL",
                        "Contact Name":      detail.get("Registered Agent Name", ""),
                        "Date Added":        company.get("filing_date", datetime.today().strftime("%Y-%m-%d")),
                        "Customer Type":     "Type 2 - Foreign Companies",
                        "Source":            "Sunbiz.org",
                        "Enrichment Status": "Pending",
                        "Outreach Status":   "Pending",
                    })
                except Exception as e:
                    log_info(f"  Skipping {company['name']}: {e}")

        except Exception as e:
            log_info(f"  Failed {entity_type}: {e}")

    log_info(f"Total foreign leads: {len(leads)}")
    return leads


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