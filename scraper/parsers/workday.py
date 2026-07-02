"""
Workday Parser — Phase 3
Queries the Workday public search API for each company to find
graduate schemes, placements and internships.

Workday's real public search endpoint (the CXS API) is:
  POST https://{host}/wday/cxs/{tenant}/{site}/jobs
  with a JSON body filtering by job family / title keywords.
{site} is a per-company slug that does NOT always match {tenant} and can
only be reliably discovered by intercepting real browser network traffic
(see discover_workday_sites.py) — without a discovered value, this falls
back to guessing site == tenant, which is common but not guaranteed.

Usage:
    from scraper.parsers.workday import parse_workday
    listings = parse_workday(company_row)

Or run standalone to test:
    python scraper/parsers/workday.py --company rolls-royce
"""

import argparse
import json
import re
import time
import requests
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HEADERS = {
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":       "application/json",
    "Content-Type": "application/json",
}

# Keywords that indicate a grad/early-careers listing
GRAD_TITLE_KEYWORDS = [
    "graduate", "grad ", "intern", "placement", "apprentice",
    "early career", "early talent", "trainee", "new grad",
    "summer", "spring week", "industrial placement", "year in industry",
    "entry level", "school leaver",
]

SCHEME_CATEGORY_MAP = {
    "graduate":            "Graduate Scheme",
    "grad ":               "Graduate Scheme",
    "early career":        "Graduate Scheme",
    "early talent":        "Graduate Scheme",
    "trainee":             "Graduate Scheme",
    "placement":           "Industrial Placement",
    "industrial":          "Industrial Placement",
    "year in industry":    "Industrial Placement",
    "intern":              "Summer Internship",
    "summer":              "Summer Internship",
    "spring week":         "Spring Week",
    "school leaver":       "Graduate Scheme",
    "apprentice":          "Graduate Scheme",
}


def extract_tenant_from_url(url):
    """
    Extract Workday tenant info from URL.
    e.g. https://baesystems.wd3.myworkday.com/baesystems/jobs
      → host=baesystems.wd3.myworkday.com, tenant=baesystems
    e.g. https://careers.rolls-royce.com/jobs
      → custom portal, not standard Workday subdomain
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if "myworkday.com" in host or "myworkdayjobs.com" in host:
        # Standard Workday subdomain
        # host = baesystems.wd3.myworkday.com
        parts = parsed.path.strip("/").split("/")
        tenant = parts[0] if parts else host.split(".")[0]
        return host, tenant, True
    else:
        # Custom portal — may still be Workday under the hood
        return host, None, False


def build_api_url(host, tenant, site=None):
    """
    Build the Workday CXS search API endpoint.
    `site` should come from a discovered value (discover_workday_sites.py);
    falling back to site == tenant is an unverified guess, not correct for
    every company.
    """
    site = site or tenant
    return f"https://{host}/wday/cxs/{tenant}/{site}/jobs"


def workday_search(api_url, keyword, offset=0, limit=20):
    """
    Call Workday's paginated search API.
    Returns raw JSON response or None on failure.
    """
    payload = {
        "appliedFacets": {},
        "limit":          limit,
        "offset":         offset,
        "searchText":     keyword,
    }
    try:
        resp = requests.post(api_url, json=payload, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        print(f"  [workday] {api_url} returned HTTP {resp.status_code} for keyword {keyword!r}")
        return None
    except Exception as e:
        print(f"  [workday] request failed for {api_url} (keyword {keyword!r}): {e}")
        return None


def parse_date(date_str):
    """Parse Workday date strings to YYYY-MM-DD."""
    if not date_str:
        return None
    # Workday uses ISO 8601: 2026-09-01T00:00:00
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    # Try simple date
    m = re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
    return m.group(1) if m else None


def classify_scheme(title):
    """Guess scheme category from job title."""
    title_lower = title.lower()
    for keyword, category in SCHEME_CATEGORY_MAP.items():
        if keyword in title_lower:
            return category
    return "Graduate Scheme"


def is_grad_listing(title):
    """Return True if title looks like a grad/early-careers role."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in GRAD_TITLE_KEYWORDS)


def extract_listings_from_response(data, company_row):
    """
    Parse Workday API response into our listing schema.
    Returns list of listing dicts.
    """
    listings = []
    if not data or "jobPostings" not in data:
        return listings

    for job in data.get("jobPostings", []):
        title = job.get("title", "")
        if not is_grad_listing(title):
            continue

        # Location
        locations = []
        for loc in job.get("locationsText", "").split(","):
            loc = loc.strip()
            if loc and "United Kingdom" not in loc and loc != "UK":
                locations.append(loc)
            elif "United Kingdom" in loc or loc == "UK":
                locations.append("UK")
        if not locations:
            locations_raw = job.get("locationsText", "")
            locations = [locations_raw] if locations_raw else ["UK"]

        # Dates
        posted_on   = parse_date(job.get("postedOn"))
        start_date  = parse_date(job.get("startDate"))
        end_date    = parse_date(job.get("endDate"))
        close_date  = parse_date(job.get("closingDate") or job.get("externalCloseDate"))

        # Job URL
        ext_url = job.get("externalPath", "")
        job_url = company_row.get("careers_url", "").rstrip("/jobs").rstrip("/") + ext_url if ext_url else company_row.get("careers_url", "")

        listing = {
            "employer":       company_row["employer"],
            "scheme_name":    title,
            "category":       classify_scheme(title),
            "disciplines":    company_row.get("disciplines", ""),
            "opening_date":   start_date or posted_on,
            "deadline":       close_date or end_date,
            "rolling_basis":  False,
            "locations":      locations,
            "url":            job_url,
            "notes":          "",
            "status":         "open",
            "last_verified":  datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source":         "workday_api",
            "raw_title":      title,
        }
        listings.append(listing)

    return listings


def parse_workday(company_row):
    """
    Main entry point. Given a company row from companies.csv,
    queries Workday API and returns list of grad scheme listings.
    """
    url  = company_row.get("careers_url", "")
    name = company_row.get("employer", "")

    host, tenant, is_standard = extract_tenant_from_url(url)

    if not is_standard or not tenant:
        print(f"  [{name}] Not a standard Workday subdomain — skipping")
        return []

    discovered_api_url = company_row.get("workday_api_url", "").strip()
    if discovered_api_url:
        api_url = discovered_api_url
    else:
        api_url = build_api_url(host, tenant)
        print(f"  [{name}] No discovered site slug in companies.csv — guessing "
              f"site=='{tenant}' (run discover_workday_sites.py for a verified value)")

    print(f"  [{name}] Querying Workday API: {api_url}")

    all_listings = []
    seen_titles  = set()

    # Search for each keyword to maximise coverage
    for keyword in ["graduate", "intern", "placement", "early careers", "trainee"]:
        offset = 0
        while True:
            data = workday_search(api_url, keyword, offset=offset)
            if not data:
                break

            total    = data.get("total", 0)
            postings = data.get("jobPostings", [])
            if not postings:
                break

            listings = extract_listings_from_response(data, company_row)
            for l in listings:
                key = l["raw_title"].lower().strip()
                if key not in seen_titles:
                    seen_titles.add(key)
                    all_listings.append(l)

            offset += len(postings)
            if offset >= total:
                break

            time.sleep(0.5)

    print(f"  [{name}] Found {len(all_listings)} grad listings")
    return all_listings


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import csv

    parser = argparse.ArgumentParser()
    parser.add_argument("--company", help="Company id to test (e.g. rolls-royce)")
    parser.add_argument("--all-workday", action="store_true", help="Run all Workday companies")
    args = parser.parse_args()

    CSV_PATH = Path(__file__).parent.parent / "output" / "companies.csv"
    companies = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")))

    if args.company:
        targets = [c for c in companies if c["id"] == args.company]
        if not targets:
            print(f"Company '{args.company}' not found in companies.csv")
        else:
            results = parse_workday(targets[0])
            print(json.dumps(results, indent=2))

    elif args.all_workday:
        workday_cos = [c for c in companies if c["ats_type"] == "Workday"]
        print(f"Running {len(workday_cos)} Workday companies...\n")
        all_results = []
        for company in workday_cos:
            listings = parse_workday(company)
            all_results.extend(listings)
            time.sleep(1)

        out = Path(__file__).parent.parent / "output" / "workday_listings.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\nTotal listings found: {len(all_results)}")
        print(f"Saved to: {out}")
    else:
        print("Usage:")
        print("  python scraper/parsers/workday.py --company rolls-royce")
        print("  python scraper/parsers/workday.py --all-workday")
