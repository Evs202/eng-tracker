"""
One-time script to discover Workday job site names for each company.
Visits each Workday careers page using Playwright, intercepts the CXS API
request to extract the job site name, stores it in companies.csv.

Usage (on VPS):
    PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/snap/bin/chromium \
        venv/bin/python scraper/discover_workday_sites.py
"""

import csv
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
COMPANIES_CSV = ROOT / "scraper" / "output" / "companies.csv"


def discover_site_name(page, url, timeout=20000):
    """
    Visit a Workday careers page and intercept the CXS API call to
    find the job site name embedded in the URL path.
    Returns (tenant, site_name) or (None, None) on failure.
    """
    captured = {}

    def on_request(request):
        m = re.search(r"/wday/cxs/([^/]+)/([^/]+)/jobs", request.url)
        if m:
            captured["tenant"] = m.group(1)
            captured["site"] = m.group(2)

    page.on("request", on_request)

    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        # Wait for JS to fire the API call
        page.wait_for_timeout(5000)
    except Exception as e:
        print(f"  Error loading {url}: {e}")

    page.remove_listener("request", on_request)
    return captured.get("tenant"), captured.get("site")


def main():
    from playwright.sync_api import sync_playwright

    rows = list(csv.DictReader(open(COMPANIES_CSV, encoding="utf-8-sig")))
    workday_rows = [r for r in rows if r["ats_type"] == "Workday"]
    print(f"Found {len(workday_rows)} Workday companies")

    chromium_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    launch_kwargs = {"headless": True}
    if chromium_path:
        launch_kwargs["executable_path"] = chromium_path

    results = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        for i, row in enumerate(workday_rows):
            cid = row["id"]
            name = row["employer"]
            url = row["careers_url"]
            print(f"[{i+1}/{len(workday_rows)}] {name} — {url}")

            tenant, site = discover_site_name(page, url)
            if tenant and site:
                print(f"  Found: tenant={tenant}, site={site}")
                results[cid] = {"tenant": tenant, "site": site}
            else:
                print(f"  Not found")

            time.sleep(2)

        context.close()
        browser.close()

    # Update companies.csv with the discovered API URLs
    updated = 0
    for row in rows:
        cid = row["id"]
        if cid in results:
            r = results[cid]
            host = f"{r['tenant']}.wd3.myworkdayjobs.com"
            row["workday_api_url"] = f"https://{host}/wday/cxs/{r['tenant']}/{r['site']}/jobs"
            updated += 1

    # Write back — add workday_api_url column if not present
    fieldnames = list(rows[0].keys())
    if "workday_api_url" not in fieldnames:
        fieldnames.append("workday_api_url")
    for row in rows:
        if "workday_api_url" not in row:
            row["workday_api_url"] = ""

    with open(COMPANIES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nUpdated {updated}/{len(workday_rows)} Workday companies with API URLs")
    print(f"Results saved to {COMPANIES_CSV}")

    # Print any that failed
    failed = [r for r in workday_rows if r["id"] not in results]
    if failed:
        print(f"\nFailed ({len(failed)}):")
        for r in failed:
            print(f"  {r['employer']} — {r['careers_url']}")


if __name__ == "__main__":
    main()
