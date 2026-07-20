"""
Run on PythonAnywhere. Pull the pages the server CAN reach (200s)
and extract every CSV / download link from them, so we find the
real current SBA 7(a) FY2020-Present URL.
"""
import requests, re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def dump_links(label, url):
    print("=" * 60)
    print(label, "->", url)
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        print(f"  Status: {r.status_code}  Size: {len(r.content)}")
        if r.status_code != 200:
            return
        # any link containing 'foia' and '.csv'
        csvs = re.findall(r'href="([^"]*foia[^"]*\.csv)"', r.text, re.I)
        # any /download/ link
        dls  = re.findall(r'href="([^"]*/download/[^"]+)"', r.text, re.I)
        # any full data.sba.gov resource link
        res  = re.findall(r'(https?://data\.sba\.gov[^"\s]+)', r.text, re.I)
        print(f"  foia csv links: {len(set(csvs))}")
        for x in sorted(set(csvs)): print("    ", x)
        print(f"  /download/ links: {len(set(dls))}")
        for x in sorted(set(dls))[:15]: print("    ", x)
        if not csvs and not dls:
            print(f"  data.sba.gov mentions: {len(set(res))}")
            for x in sorted(set(res))[:15]: print("    ", x)
    except Exception as e:
        print(f"  FAILED: {e}")
    print()

# Pages the server returned 200 for
dump_links("data.sba.gov root", "https://data.sba.gov/")
dump_links("data.sba.gov dataset (no /en/)", "https://data.sba.gov/dataset/7-a-504-foia")
dump_links("catalog.data.gov dataset", "https://catalog.data.gov/dataset/7-a-504-foia")
# search on the catalog for the dataset's real slug
dump_links("catalog search html", "https://catalog.data.gov/dataset?q=7a+504+FOIA")
