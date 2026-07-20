"""
Probe SBA datastore API from PythonAnywhere.
Tries the JSON API instead of the CSV file download.
"""
import requests
import json

RESOURCE_ID = "d67d3ccb-2002-4134-a288-481b51cd3479"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# A few endpoint variants to see which the edge serves correctly
urls = [
    ("datastore /en/", f"https://data.sba.gov/en/api/3/action/datastore_search?resource_id={RESOURCE_ID}&limit=2"),
    ("datastore no /en/", f"https://data.sba.gov/api/3/action/datastore_search?resource_id={RESOURCE_ID}&limit=2"),
    ("package_show /en/", "https://data.sba.gov/en/api/3/action/package_show?id=7-a-504-foia"),
    ("package_show no /en/", "https://data.sba.gov/api/3/action/package_show?id=7-a-504-foia"),
]

for label, url in urls:
    print("=" * 60)
    print(label)
    print(url)
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            result = data.get("result", {})
            # datastore_search returns records + the resource_id it actually served
            served_rid = result.get("resource_id")
            if served_rid:
                match = "MATCH" if served_rid == RESOURCE_ID else "WRONG RESOURCE (cache poisoned)"
                print(f"  Served resource_id: {served_rid}  [{match}]")
                recs = result.get("records", [])
                print(f"  Records returned: {len(recs)}")
                if recs:
                    # show the field names so we know it's the loan data
                    print(f"  Fields: {list(recs[0].keys())[:8]}")
            # package_show returns resources list
            resources = result.get("resources")
            if resources:
                print(f"  Resources in package: {len(resources)}")
                for res in resources:
                    if res.get("id") == RESOURCE_ID:
                        print(f"    FY2020 file URL: {res.get('url')}")
    except Exception as e:
        print(f"  FAILED: {e}")
    print()
