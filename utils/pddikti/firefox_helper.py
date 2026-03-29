"""
Firefox WebDriver factory — dipakai bersama oleh semua scraper.

Prioritas binary Firefox:
  1. Env var FIREFOX_BINARY (jika diset)
  2. /snap/firefox/current/usr/lib/firefox/firefox  (Ubuntu snap)
  3. /usr/bin/firefox
  4. /usr/lib/firefox/firefox
  5. Tidak di-set → Selenium cari sendiri via PATH
"""

import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

GECKODRIVER_PATH = Path(__file__).resolve().parent.parent / "geckodriver"

_FIREFOX_CANDIDATES = [
    os.environ.get("FIREFOX_BINARY", ""),
    "/snap/firefox/current/usr/lib/firefox/firefox",
    "/usr/bin/firefox",
    "/usr/lib/firefox/firefox",
    "/usr/lib/firefox-esr/firefox-esr",
]


def _find_firefox_bin():
    for p in _FIREFOX_CANDIDATES:
        if p and Path(p).exists():
            return p
    return None  # biarkan Selenium cari via PATH


def make_driver(headless=True, page_load_timeout=None, extra_prefs=None):
    """Buat Firefox WebDriver dengan geckodriver lokal."""
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    ff_bin = _find_firefox_bin()
    if ff_bin:
        options.binary_location = ff_bin

    if extra_prefs:
        for key, val in extra_prefs.items():
            options.set_preference(key, val)

    # Snap Firefox membutuhkan TMPDIR=/tmp agar geckodriver bisa launch
    svc_env = os.environ.copy()
    svc_env.setdefault("TMPDIR", "/tmp")

    service = Service(str(GECKODRIVER_PATH), env=svc_env)
    driver = webdriver.Firefox(service=service, options=options)
    if page_load_timeout:
        driver.set_page_load_timeout(page_load_timeout)
    return driver
