"""Test whether the SBA 7(a) data is reachable via alternate hosts
from PythonAnywhere (catalog.data.gov and its API)."""
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html",
}

tests = [
    ("data.gov package API",
     "https://catalog.data.gov/api/3/action/package_show?id=sba-7a-and-504-loan-data-reports"),
    ("data.gov dataset page",
     "https://catalog.data.gov/dataset/7-a-504-foia"),
    ("data.gov search",
     "https://catalog.data.gov/api/3/action/package_search?q=7a+504+FOIA&rows=3"),
    ("sba.gov main site reachable?",
     "https://www.sba.gov/"),
    ("data.sba.gov root reachable?",
     "https://data.sba.gov/"),
]

for label, url in tests:
    print("=" * 60)
    print(label)
    print(url)
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        print(f"  Status: {r.status_code}")
        print(f"  Size: {len(r.content)} bytes")
        ct = r.headers.get("Content-Type", "?")
        print(f"  Content-Type: {ct}")
        # if JSON and has resources, look for CSV download links
        if "json" in ct and r.status_code == 200:
            try:
                data = r.json()
                res = data.get("result", {})
                resources = res.get("resources") or (res.get("results", [{}])[0].get("resources") if res.get("results") else None)
                if resources:
                    csvs = [x.get("url") for x in resources if str(x.get("format","")).upper()=="CSV" and "7a" in str(x.get("url","")).lower() and "2020" in str(x.get("url","")).lower()]
                    for c in csvs:
                        print(f"    FY2020 CSV: {c}")
            except Exception as pe:
                print(f"  (json parse note: {pe})")
    except Exception as e:
        print(f"  FAILED: {e}")
    print()
