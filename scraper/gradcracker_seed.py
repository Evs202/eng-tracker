"""
Gradcracker employer seed scraper — v2.
Scrapes job listing pages to collect unique employer hub URLs,
then visits each hub page to get the real employer name + careers URL.
Outputs: scraper/output/employers_seed.csv

Usage:
    pip install requests beautifulsoup4
    python scraper/gradcracker_seed.py
"""

import csv
import time
import re
import os
import requests
from bs4 import BeautifulSoup

BASE = "https://www.gradcracker.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; eng-tracker-research-bot/1.0)"
}
DELAY = 1.2

DISCIPLINE_MAP = {
    "aerospace-aeronautical":    "Aerospace Engineering",
    "chemical-process":          "Chemical Engineering",
    "civil-structural":          "Civil Engineering",
    "electrical-electronic":     "Electrical & Electronics",
    "mechanical":                "Mechanical Engineering",
    "biomedical-biotechnology":  "Biomedical Engineering",
    "software-it":               "Software Engineering",
    "systems-control":           "Systems Engineering",
    "energy-renewables":         "Renewable Energy",
    "robotics-automation":       "Robotics & Automation",
}

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "employers_seed.csv")
LOG_FILE = os.path.join(OUTPUT_DIR, "progress.log")

def log(msg):
    print(msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def get_soup(url):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    time.sleep(DELAY)
    return BeautifulSoup(resp.text, "html.parser")

def slug_to_name(slug):
    """Convert 'bae-systems' → 'BAE Systems'"""
    return " ".join(w.capitalize() for w in slug.replace("-", " ").split())

def collect_hub_urls(discipline_slug):
    """Return set of hub URLs found across all listing pages for a discipline."""
    hub_urls = {}  # hub_url → set of disciplines
    page = 1
    discipline_label = DISCIPLINE_MAP[discipline_slug]

    while True:
        url = f"{BASE}/search/{discipline_slug}/engineering-graduate-jobs/?page={page}"
        log(f"  [{discipline_slug}] page {page}")
        try:
            soup = get_soup(url)
        except Exception as e:
            log(f"  Error: {e}")
            break

        # All hub links on the page
        links = soup.select("a[href*='/hub/']")
        found = set()
        for a in links:
            href = a.get("href", "")
            m = re.match(r"(/hub/(\d+)/([^/?#]+))", href)
            if m:
                path = m.group(1)
                hub_id = m.group(2)
                # Skip the generic "featured-graduate-employer" placeholder
                if "featured-graduate-employer" in path:
                    continue
                full_url = BASE + path
                found.add(full_url)
                if full_url not in hub_urls:
                    hub_urls[full_url] = set()
                hub_urls[full_url].add(discipline_label)

        if not found:
            log(f"  No hub links on page {page} — stopping discipline.")
            break

        # Next page?
        next_btn = soup.select_one("a[rel='next'], a.next, li.next a, [aria-label='Next']")
        if not next_btn:
            break
        page += 1
        if page > 40:
            break

    return hub_urls

def get_employer_info(hub_url):
    """Visit hub page, return (employer_name, careers_url)."""
    try:
        soup = get_soup(hub_url)

        # Employer name — usually in <h1> or og:title
        name = None
        og = soup.find("meta", property="og:title")
        if og:
            name = og.get("content", "").strip()
            # Strip trailing " | Gradcracker" etc.
            name = re.sub(r"\s*[\|–-].*$", "", name).strip()

        if not name:
            h1 = soup.select_one("h1")
            if h1:
                name = h1.get_text(strip=True)

        if not name:
            # Fall back to slug
            slug = hub_url.rstrip("/").split("/")[-1]
            name = slug_to_name(slug)

        # Careers URL — external link labelled careers/website/apply
        careers_url = ""
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            text = a.get_text(strip=True).lower()
            if href.startswith("http") and "gradcracker.com" not in href:
                if any(k in text for k in ["careers", "website", "visit", "apply", "jobs"]):
                    careers_url = href
                    break

        if not careers_url:
            # Any external link
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if href.startswith("http") and "gradcracker.com" not in href:
                    careers_url = href
                    break

        return name, careers_url

    except Exception as e:
        log(f"    Error fetching {hub_url}: {e}")
        slug = hub_url.rstrip("/").split("/")[-1]
        return slug_to_name(slug), ""

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # Clear log
    open(LOG_FILE, "w").close()

    log("=== Gradcracker employer seed scraper v2 ===\n")

    # Step 1: collect all hub URLs across all disciplines
    all_hubs = {}  # hub_url → set of discipline labels
    for slug in DISCIPLINE_MAP:
        log(f"\nScraping discipline: {slug}")
        hubs = collect_hub_urls(slug)
        log(f"  Found {len(hubs)} unique employers")
        for url, discs in hubs.items():
            if url not in all_hubs:
                all_hubs[url] = set()
            all_hubs[url].update(discs)

    log(f"\nTotal unique employer hubs: {len(all_hubs)}")

    # Step 2: visit each hub page to get real name + careers URL
    log("Fetching employer names and careers URLs...\n")
    rows = []
    hub_list = list(all_hubs.items())
    for i, (hub_url, disciplines) in enumerate(hub_list):
        slug = hub_url.rstrip("/").split("/")[-1]
        log(f"[{i+1}/{len(hub_list)}] {slug}")
        name, careers_url = get_employer_info(hub_url)
        rows.append({
            "employer":          name,
            "disciplines":       "; ".join(sorted(disciplines)),
            "careers_url":       careers_url,
            "gradcracker_hub":   hub_url,
        })

    # Sort by employer name
    rows.sort(key=lambda r: r["employer"].lower())

    # Write CSV
    fieldnames = ["employer", "disciplines", "careers_url", "gradcracker_hub"]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    log(f"\n✓ Done. {len(rows)} employers written to:\n  {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
