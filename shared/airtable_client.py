import requests
import os
from dotenv import load_dotenv

load_dotenv()

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN", "")
BASE_ID        = "appsNkoJJqzZFfAW1"
TABLE_ID       = "tblU9q6T3j1pyCWey"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type":  "application/json"
}

BASE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"


def get_existing_keys() -> set[str]:
    """
    Fetch all existing Company Name + State combos from Airtable.
    Returns a set of 'COMPANY NAME|STATE' strings for fast dedup lookup.
    """
    existing = set()
    params   = {
        "fields[]": ["Company Name", "State"],
        "pageSize": 100
    }

    while True:
        resp = requests.get(BASE_URL, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()

        for record in data.get("records", []):
            f    = record.get("fields", {})
            name = f.get("Company Name", "").upper().strip()
            state= f.get("State", "").upper().strip()
            if name:
                existing.add(f"{name}|{state}")

        # Pagination
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset

    return existing


def push_leads_batch(leads: list[dict]) -> tuple[int, int]:
    """
    Push leads to Airtable using batch API (10 per request).
    Fetches existing records first for deduplication.
    Returns (added, skipped).
    """
    if not leads:
        return 0, 0

    # Fetch all existing keys once
    print("  Fetching existing Airtable records for dedup check...")
    existing_keys = get_existing_keys()
    print(f"  Existing records in Airtable: {len(existing_keys)}")

    # Filter out duplicates
    new_leads = []
    skipped   = 0
    for lead in leads:
        name  = lead.get("Company Name", "").upper().strip()
        state = lead.get("State", "").upper().strip()
        key   = f"{name}|{state}"
        if key in existing_keys:
            skipped += 1
        else:
            new_leads.append(lead)
            existing_keys.add(key)  # prevent dupes within this batch

    print(f"  New leads to push: {len(new_leads)} | Duplicates skipped: {skipped}")

    # Push in batches of 10 (Airtable limit)
    added     = 0
    BATCH     = 10
    total     = len(new_leads)

    for i in range(0, total, BATCH):
        chunk   = new_leads[i:i + BATCH]
        payload = {"records": [{"fields": lead} for lead in chunk]}
        resp    = requests.post(BASE_URL, headers=HEADERS, json=payload)
        if resp.status_code >= 400:
            print("AIRTABLE ERROR:", resp.text)
        resp.raise_for_status() 
        added  += len(resp.json().get("records", []))

        # Progress log every 100 records
        if True:
            print(f"  Pushed {min(i + BATCH, total)}/{total}...")

    return added, skipped


def get_recent_records(customer_type: str, days: int = 90) -> list[dict]:
    from datetime import datetime, timedelta
    cutoff = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    params = {
        "filterByFormula": f"AND({{Customer Type}}='{customer_type}', IS_AFTER({{Date Added}}, '{cutoff}'))",
        "maxRecords": 1000
    }
    resp = requests.get(BASE_URL, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json().get("records", [])