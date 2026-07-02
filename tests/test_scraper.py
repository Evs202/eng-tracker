"""
Scraper unit tests using mock HTTP responses.

Run: pytest tests/test_scraper.py

These tests don't hit the real internet — they use mock responses so
the tests are fast and don't depend on employer websites being up.
"""

import json
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scraper dir to path so we can import selector_scraper.py
sys.path.insert(0, str(Path(__file__).parent.parent / "scraper"))
import selector_scraper as scraper


# ── T6: load_config ────────────────────────────────────────────────────────

def test_load_config_returns_employers_key(tmp_path):
    """T6: load_config returns a dict with an 'employers' key."""
    config = {"employers": [{"id": "test", "name": "Test Co", "url": "http://example.com",
                             "deadline_selector": None, "notes": "", "requires_js": False}]}
    config_file = tmp_path / "scrapers-config.json"
    config_file.write_text(json.dumps(config))

    # Patch the CONFIG_FILE path
    with patch.object(scraper, "CONFIG_FILE", config_file):
        result = scraper.load_config()

    assert "employers" in result
    assert len(result["employers"]) == 1


# ── T7: scrape_employer with valid selector ────────────────────────────────

def test_scrape_employer_valid_selector():
    """T7: scrape_employer with a valid selector returns status=open and scraped date."""
    employer_config = {
        "id": "test-employer",
        "name": "Test Employer",
        "url": "http://example.com/careers",
        "deadline_selector": ".deadline-date",
        "notes": "",
        "requires_js": False,
    }

    mock_html = '<html><body><span class="deadline-date">5 December 2026</span></body></html>'
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html
    mock_response.raise_for_status = MagicMock()

    with patch("selector_scraper.requests.get", return_value=mock_response):
        result = scraper.scrape_employer(employer_config)

    assert result["id"] == "test-employer"
    assert result["status"] == "open"
    assert result["last_scraped"] == scraper.TODAY
    assert "_raw_deadline" in result


# ── T8: scrape_employer with selector not found ────────────────────────────

def test_scrape_employer_selector_not_found():
    """T8: When selector doesn't match anything, status=unknown."""
    employer_config = {
        "id": "test-employer",
        "name": "Test Employer",
        "url": "http://example.com/careers",
        "deadline_selector": ".nonexistent-selector",
        "notes": "",
        "requires_js": False,
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body><p>No deadline here</p></body></html>"
    mock_response.raise_for_status = MagicMock()

    with patch("selector_scraper.requests.get", return_value=mock_response):
        result = scraper.scrape_employer(employer_config)

    assert result["id"] == "test-employer"
    assert result["status"] == "unknown"


# ── T9: scrape_employer with HTTP error ────────────────────────────────────

def test_scrape_employer_http_error():
    """T9: When server returns 403, status=unknown (no crash)."""
    import requests as req

    employer_config = {
        "id": "test-employer",
        "name": "Test Employer",
        "url": "http://example.com/careers",
        "deadline_selector": ".deadline-date",
        "notes": "",
        "requires_js": False,
    }

    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.raise_for_status.side_effect = req.exceptions.HTTPError(response=mock_response)

    with patch("selector_scraper.requests.get", return_value=mock_response):
        result = scraper.scrape_employer(employer_config)

    assert result["id"] == "test-employer"
    assert result["status"] == "unknown"


# ── T10: validate_schema rejects missing field ─────────────────────────────

def test_validate_schema_rejects_missing_field():
    """T10: validate_schema exits if a required field is missing."""
    incomplete_employers = [
        {"id": "x", "employer": "Missing Fields Co"}  # missing most required fields
    ]
    with pytest.raises(SystemExit):
        scraper.validate_schema(incomplete_employers)
