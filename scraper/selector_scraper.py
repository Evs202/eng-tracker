"""
UK Engineering Grad Scheme Deadline Scraper — per-company CSS-selector approach.

Run manually:  python scraper/selector_scraper.py

Not currently part of the live pipeline (see SPEC.md) — detector.py's
hash-diff + keyword-flag approach superseded this. Renamed 2026-07-02 from
scraper.py, which collided with the scraper/ package name and broke imports
in any script run directly from that directory (e.g. `from scraper.detector
import X` failed because scraper/scraper.py shadowed the scraper package).
Kept rather than deleted because it has real unit test coverage
(tests/test_scraper.py) and scrapers-config.json still only has placeholder
entries (deadline_selector: null) for 3 example companies — this approach
was apparently parked mid-build, not finished and abandoned.

This script visits each employer's career page, finds the deadline date
using a CSS selector, and updates data/deadlines.json.
"""

import json
import time
import random
import sys
from datetime import date
from pathlib import Path

# requests: simple HTTP fetching
# beautifulsoup4: parses HTML to find elements
# Install: pip install requests beautifulsoup4
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Missing dependencies. Run: pip install requests beautifulsoup4")
    sys.exit(1)

# Paths (works from project root or scraper/ directory)
ROOT = Path(__file__).parent.parent
CONFIG_FILE = ROOT / "scraper" / "scrapers-config.json"
DATA_FILE   = ROOT / "data" / "deadlines.json"

TODAY = date.today().isoformat()

REQUIRED_FIELDS = {"id", "employer", "scheme_name", "disciplines", "deadline",
                   "status", "rolling_basis", "url", "last_verified"}


def load_config():
    if not CONFIG_FILE.exists():
        print(f"ERROR: Config file not found: {CONFIG_FILE}")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)


def load_deadlines():
    if not DATA_FILE.exists():
        print(f"ERROR: deadlines.json not found: {DATA_FILE}")
        sys.exit(1)
    with open(DATA_FILE) as f:
        return json.load(f)


def scrape_employer(employer_config):
    """
    Visit employer's career page and find the deadline.
    Returns a dict with the fields to update, or None if scraping fails.
    """
    employer_id = employer_config["id"]
    url = employer_config["url"]
    selector = employer_config.get("deadline_selector")

    print(f"  Scraping {employer_config['name']}...")

    # If no selector defined yet, we can't scrape — return unknown status
    if not selector:
        print(f"    No selector configured yet — skipping (status=unknown)")
        return {"id": employer_id, "status": "unknown", "last_scraped": TODAY}

    # For rolling basis employers, skip scraping — their status is always rolling
    if "rolling" in employer_config.get("notes", "").lower():
        print(f"    Rolling basis employer — no deadline to scrape")
        return {"id": employer_id, "status": "rolling", "rolling_basis": True,
                "deadline": None, "last_scraped": TODAY, "last_verified": TODAY}

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; UK-Eng-Grad-Tracker/1.0; "
                          "educational aggregator; contact: your-email@example.com)"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"    Timeout fetching {url}")
        return {"id": employer_id, "status": "unknown", "last_scraped": TODAY}
    except requests.exceptions.HTTPError as e:
        print(f"    HTTP error {e.response.status_code} for {url}")
        return {"id": employer_id, "status": "unknown", "last_scraped": TODAY}
    except requests.exceptions.RequestException as e:
        print(f"    Request failed: {e}")
        return {"id": employer_id, "status": "unknown", "last_scraped": TODAY}

    soup = BeautifulSoup(response.text, "html.parser")
    element = soup.select_one(selector)

    if not element:
        print(f"    Selector '{selector}' not found on page — status=unknown")
        return {"id": employer_id, "status": "unknown", "last_scraped": TODAY}

    deadline_text = element.get_text(strip=True)
    print(f"    Found: {deadline_text!r}")

    # TODO: parse deadline_text into ISO date format (YYYY-MM-DD)
    # This will be different for each employer depending on how they format dates.
    # Example: "5 December 2026" → "2026-12-05"
    # For now, store the raw text and flag for manual review.
    return {
        "id": employer_id,
        "status": "open",
        "deadline": None,             # TODO: parse deadline_text to ISO date
        "last_scraped": TODAY,
        "_raw_deadline": deadline_text  # for manual review in PR diff
    }


def validate_schema(employers):
    """Check all required fields are present. Exits if not."""
    for i, entry in enumerate(employers):
        missing = REQUIRED_FIELDS - set(entry.keys())
        if missing:
            print(f"ERROR: Entry {i} (id={entry.get('id', '?')}) missing fields: {missing}")
            sys.exit(1)


def apply_scrape_results(deadlines, results):
    """Merge scraper results back into the deadlines list."""
    results_by_id = {r["id"]: r for r in results}
    for entry in deadlines["employers"]:
        update = results_by_id.get(entry["id"])
        if update:
            for key, value in update.items():
                if key != "id":
                    entry[key] = value
    return deadlines


def main():
    print("Loading config...")
    config = load_config()

    print("Loading current deadlines...")
    deadlines = load_deadlines()

    print(f"\nScraping {len(config['employers'])} employers...")
    results = []
    for i, employer in enumerate(config["employers"]):
        result = scrape_employer(employer)
        if result:
            results.append(result)

        # Rate limiting: pause 2-5 seconds between requests (avoids IP blocks)
        if i < len(config["employers"]) - 1:
            wait = random.uniform(2, 5)
            print(f"    Waiting {wait:.1f}s before next request...")
            time.sleep(wait)

    print(f"\nApplying results to deadlines.json...")
    updated = apply_scrape_results(deadlines, results)

    print("Validating schema...")
    validate_schema(updated["employers"])

    # Count how many are unknown (potential broken selectors)
    unknown_count = sum(1 for e in updated["employers"] if e.get("status") == "unknown")
    if unknown_count > 0:
        print(f"\n⚠️  WARNING: {unknown_count} employer(s) have status=unknown.")
        print("   This means the scraper couldn't find their deadline.")
        print("   Possible causes: broken selector, page layout changed, or selector not yet configured.")
        print("   Review these manually before merging the PR.")

    with open(DATA_FILE, "w") as f:
        json.dump(updated, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\n✓ Updated {DATA_FILE}")
    print(f"  {len(results)} employers processed")
    print(f"  {unknown_count} unknown (need review)")


if __name__ == "__main__":
    main()
