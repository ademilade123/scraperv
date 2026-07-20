"""
Probe the SBA download endpoints WITHOUT a filename, plus the
resource-page scrape. Run this in the GitHub Action (or anywhere
that can reach data.sba.gov) to find a URL that actually returns CSV.
"""
import requests, re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*",
}

DATASET_ID  = "0ff8e8e9-b967-4f4e-987c-6ac78c575087"
RESOURCE_ID = "d67d3ccb-2002-4134-a288-481b51cd3479"

candidates = [
    ("bare /download no filename",
     f"https://data.sba.gov/dataset/{DATASET_ID}/resource/{RESOURCE_ID}/download"),
    ("bare /download /en/",
     f"https://data.sba.gov/en/dataset/{DATASET_ID}/resource/{RESOURCE_ID}/download"),
    ("known older file 250331",
     f"https://data.sba.gov/dataset/{DATASET_ID}/resource/{RESOURCE_ID}/download/foia-7a-fy2020-present-asof-250331.csv"),
    ("resource page (scrape for link)",
     f"https://data.sba.gov/dataset/{DATASET_ID}/resource/{RESOURCE_ID}"),
]

for label, url in candidates:
    print("=" * 60)
    print(label)
    print(url)
    try:
        r = requests.get(url, headers=HEADERS, timeout=90, allow_redirects=True)
        print(f"  Status: {r.status_code}")
        print(f"  Final URL: {r.url}")
        ct = r.headers.get("Content-Type", "?")
        print(f"  Content-Type: {ct}  Size: {len(r.content)}")
        if r.status_code == 200 and ("csv" in ct.lower() or "," in r.text[:200]):
            print(f"  FIRST LINE: {r.text.splitlines()[0][:120]}")
            print("  >>> THIS ONE WORKS <<<")
        elif r.status_code == 200 and "html" in ct.lower():
            # scrape any csv download link off the resource page
            links = re.findall(r'(https?://[^"\s]*foia-7a[^"\s]*\.csv)', r.text, re.I)
            for l in sorted(set(links)):
                print(f"    found link: {l}")
    except Exception as e:
        print(f"  FAILED: {e}")
    print()
