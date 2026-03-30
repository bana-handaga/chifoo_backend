"""
Firefox WebDriver factory — dipakai bersama oleh semua scraper.

Prioritas binary Firefox:
  1. Env var FIREFOX_BINARY (jika diset)
  2. /snap/firefox/current/usr/lib/firefox/firefox  (Ubuntu snap)
  3. /usr/bin/firefox
  4. /usr/lib/firefox/firefox
  5. Tidak di-set → Selenium cari sendiri via PATH

geckodriver: pakai sistem (via PATH), bukan binary lokal.
"""

import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

_FIREFOX_HEADLESS_CANDIDATES = [
    "/usr/lib/firefox-esr/firefox-esr",   # binary langsung, tidak butuh display
    "/usr/lib/firefox/firefox",
    "/snap/firefox/current/usr/lib/firefox/firefox",
]

_FIREFOX_GUI_CANDIDATES = [
    "/usr/bin/firefox-esr",               # wrapper script, setup env GUI dengan benar
    "/usr/bin/firefox",
]


def _find_firefox_bin(headless=True):
    candidates = _FIREFOX_HEADLESS_CANDIDATES if headless else _FIREFOX_GUI_CANDIDATES
    for p in candidates:
        if p and Path(p).exists():
            return p
    return None  # biarkan Selenium cari via PATH


def make_driver(headless=True, page_load_timeout=None, extra_prefs=None):
    """Buat Firefox WebDriver dengan geckodriver sistem."""
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    # Preferences untuk lingkungan headless/server tanpa desktop session
    options.set_preference("browser.tabs.remote.autostart", False)
    options.set_preference("security.sandbox.content.level", 0)
    options.set_preference("extensions.enabled", False)
    options.set_preference("datareporting.healthreport.uploadEnabled", False)
    options.set_preference("datareporting.policy.dataSubmissionEnabled", False)

    ff_bin = _find_firefox_bin(headless=headless)
    if ff_bin:
        options.binary_location = ff_bin

    if extra_prefs:
        for key, val in extra_prefs.items():
            options.set_preference(key, val)

    # Paksa headless — set di os.environ agar diwarisi geckodriver & Firefox
    os.environ.pop("FIREFOX_BINARY", None)  # hapus override lama jika ada
    os.environ.setdefault("TMPDIR", "/tmp")
    if headless:
        # Mode headless: hapus display agar Firefox tidak mencoba buka GUI
        os.environ.pop("DISPLAY", None)
        os.environ.pop("DBUS_SESSION_BUS_ADDRESS", None)
        os.environ.pop("XDG_RUNTIME_DIR", None)
        os.environ["MOZ_HEADLESS"] = "1"
        os.environ["MOZ_DISABLE_CONTENT_SANDBOX"] = "1"

    # Gunakan geckodriver dari sistem (PATH), bukan binary lokal
    # Cari path eksplisit agar tidak memicu selenium-manager (lambat)
    import shutil
    gecko_path = shutil.which("geckodriver") or "geckodriver"
    service = Service(executable_path=gecko_path)
    driver = webdriver.Firefox(service=service, options=options)
    if page_load_timeout:
        driver.set_page_load_timeout(page_load_timeout)
    return driver
