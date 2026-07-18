"""
Run this ONCE to create all required fields in the Airtable base.
"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN   = os.environ.get("AIRTABLE_TOKEN")
BASE_ID = "appsNkoJJqzZFfAW1"
TABLE_ID = "tblU9q6T3j1pyCWey"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type":  "application/json"
}

# All fields we need with their types
FIELDS = [
    {"name": "Company Name",      "type": "singleLineText"},
    {"name": "Contact Name",      "type": "singleLineText"},
    {"name": "Email",             "type": "email"},
    {"name": "Phone",             "type": "phoneNumber"},
    {"name": "State",             "type": "singleLineText"},
    {"name": "Industry/NAICS",    "type": "singleLineText"},
    {"name": "Loan Amount",       "type": "singleLineText"},
    {"name": "Customer Type",     "type": "singleSelect", "options": {
        "choices": [
            {"name": "Type 1 - US Founders"},
            {"name": "Type 2 - Foreign Companies"},
            {"name": "Type 3 - HNW Multiple Businesses"},
        ]
    }},
    {"name": "Source",            "type": "singleLineText"},
    {"name": "Date Added",        "type": "singleLineText"},
    {"name": "Enrichment Status", "type": "singleSelect", "options": {
        "choices": [
            {"name": "Pending"},
            {"name": "Enriched"},
            {"name": "Failed"},
        ]
    }},
    {"name": "Outreach Status",   "type": "singleSelect", "options": {
        "choices": [
            {"name": "Pending"},
            {"name": "Sent"},
            {"name": "Replied"},
            {"name": "Booked"},
        ]
    }},
    {"name": "Notes",             "type": "multilineText"},
]

def create_fields():
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{TABLE_ID}/fields"

    print(f"Setting up Airtable fields for table {TABLE_ID}...")
    created = 0
    skipped = 0

    for field in FIELDS:
        payload = {"name": field["name"], "type": field["type"]}
        if "options" in field:
            payload["options"] = field["options"]

        resp = requests.post(url, headers=HEADERS, json=payload)

        if resp.status_code == 200:
            print(f"  [OK] Created: {field['name']}")
            created += 1
        elif "DUPLICATE_FIELD_NAME" in resp.text or resp.status_code == 422:
            print(f"  [SKIP] Already exists: {field['name']}")
            skipped += 1
        else:
            print(f"  [WARN] {field['name']}: {resp.status_code} - {resp.text[:100]}")

    print(f"\nDone! Created: {created} | Skipped (already exist): {skipped}")
    print("You can now run python run_all.py")

if __name__ == "__main__":
    create_fields()