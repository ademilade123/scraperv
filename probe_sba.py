"""Check the SBA CSV's date column and date range."""
import requests, csv, io
from datetime import datetime

URL = ("https://data.sba.gov/sites/default/files/uploaded_resources/"
       "FOIA_7a_FY2020_Present_asof_260331.csv")
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

print("Downloading...")
r = requests.get(URL, headers=HEADERS, timeout=180)
r.raise_for_status()
rows = list(csv.DictReader(io.StringIO(r.text)))
print(f"Rows: {len(rows)}")
print(f"Columns: {list(rows[0].keys())}")
print()

# show sample approvaldate values
print("Sample approvaldate values:")
for row in rows[:5]:
    print(f"  '{row.get('approvaldate')}'  gross='{row.get('grossapproval')}'")

# find the newest approval date in the file
def pd(s):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try: return datetime.strptime(s.strip(), fmt)
        except: pass
    return None

dates = [pd(r.get("approvaldate","")) for r in rows]
dates = [d for d in dates if d]
if dates:
    print(f"\nOldest approval date: {min(dates).date()}")
    print(f"Newest approval date: {max(dates).date()}")
    print(f"Today: {datetime.today().date()}")
    days_old = (datetime.today() - max(dates)).days
    print(f"Newest record is {days_old} days old")
