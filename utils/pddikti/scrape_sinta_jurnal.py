"""
Script untuk mengambil data jurnal Perguruan Tinggi dari SINTA
Sumber: https://sinta.kemdiktisaintek.go.id/

Alur:
  1. Baca outs/namapt_list.json  -> daftar PT dengan field 'kode' (kodept)
  2. Cari PT di SINTA via  https://sinta.kemdiktisaintek.go.id/affiliations?q=[kodept]
     Dari hasil pencarian ambil SINTA ID (angka di URL /affiliations/profile/{sinta_id})
  3. Buka halaman profil PT (/affiliations/profile/{sinta_id}), ambil data profil
  4. Buka halaman daftar jurnal langsung (/journals/index/{sinta_id}?page=N)
  5. Parse semua item .list-item di setiap halaman (loop pagination)
  6. Simpan ke outs/sinta_jurnal.json dengan index kodept

Output: outs/sinta_jurnal.json
  {
    "011003": {
      "sinta_id": "581",
      "profil_pt": {
        "nama_pt": "...",
        "lokasi": "...",
        "jumlah_authors": "626",
        "jumlah_departments": "47",
        "jumlah_journals": "36",
        ...
      },
      "jurnal": [
        {
          "nama_jurnal": "...",
          "sinta_url": "...",
          "url_google_scholar": "...",
          "url_website": "...",
          "url_editor": "...",
          "p_issn": "...",
          "e_issn": "...",
          "subject_area": "...",
          "akreditasi": "S2",
          "garuda_url": "...",
          "impact": "42,14",
          "h5_index": "49",
          "citations_5yr": "6.210",
          "citations": "6.266"
        },
        ...
      ]
    },
    ...
  }
"""

import json
import os
import re
import time

from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

GECKODRIVER_PATH = Path(__file__).resolve().parent.parent / "geckodriver"
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_FILE  = os.path.join(BASE_DIR, "utils/outs/namapt_list.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "utils/outs/sinta_jurnal.json")

SINTA_BASE      = "https://sinta.kemdiktisaintek.go.id"
SEARCH_URL      = SINTA_BASE + "/affiliations?q={kode}"
PROFILE_URL     = SINTA_BASE + "/affiliations/profile/{sinta_id}"
JOURNALS_URL    = SINTA_BASE + "/journals/index/{sinta_id}?page={page}"

PAGE_LOAD_WAIT    = 8    # detik tunggu halaman load
BETWEEN_PAGE_WAIT = 4    # detik antar halaman pagination
BETWEEN_PT_WAIT   = 5    # detik antar PT
PAGE_LOAD_TIMEOUT = 120  # detik timeout page load
RETRY_COUNT       = 5    # jumlah retry jika timeout
RETRY_WAIT        = 10   # detik jeda antar retry


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def init_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/snap/firefox/current/usr/lib/firefox/firefox"
    options.set_preference("network.http.connection-timeout", 90)
    options.set_preference("network.http.response.timeout", 90)
    driver = webdriver.Firefox(service=Service(str(GECKODRIVER_PATH)), options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def open_with_retry(driver, url, wait_css=None, retries=RETRY_COUNT):
    """Buka URL dengan retry jika timeout. Tunggu elemen wait_css jika diberikan."""
    for attempt in range(1, retries + 1):
        try:
            driver.get(url)
            if wait_css:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_css))
                )
            else:
                time.sleep(PAGE_LOAD_WAIT)
            return True
        except TimeoutException:
            print(f"  Timeout attempt {attempt}/{retries}: {url}")
            if attempt < retries:
                time.sleep(RETRY_WAIT)
    return False


def safe_text(el):
    try:
        return el.text.strip()
    except Exception:
        return ""


def safe_attr(el, attr):
    try:
        return el.get_attribute(attr) or ""
    except Exception:
        return ""


def extract_sinta_id(url):
    """Ekstrak SINTA ID dari URL pola /affiliations/profile/{id}"""
    m = re.search(r"/affiliations/profile/(\d+)", url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Cari SINTA ID dari pencarian kodept
# ---------------------------------------------------------------------------

def find_sinta_id(driver, kode):
    """
    Buka halaman pencarian SINTA dengan query kodept.
    Kembalikan SINTA ID (string angka) dari URL hasil pencarian pertama,
    atau None jika tidak ditemukan.
    """
    url = SEARCH_URL.format(kode=kode)
    print(f"  Mencari: {url}")
    open_with_retry(driver, url, wait_css=".affil-name, .list-item, .content")

    # Cari semua link ke /affiliations/profile/{id}
    links = driver.find_elements(By.TAG_NAME, "a")
    for a in links:
        href = safe_attr(a, "href")
        sinta_id = extract_sinta_id(href)
        if sinta_id:
            print(f"  SINTA ID ditemukan: {sinta_id}  ({href})")
            return sinta_id

    print(f"  SINTA ID tidak ditemukan untuk kode: {kode}")
    return None


# ---------------------------------------------------------------------------
# Profil PT
# ---------------------------------------------------------------------------

def scrape_profil_pt(driver, sinta_id):
    """
    Buka dan baca data profil PT dari halaman /affiliations/profile/{sinta_id}.
    Field yang diambil:
      - h3 dalam .univ-name          -> nama_pt
      - .affil-abbrev                -> singkatan (contoh: UMSU)
      - .affil-loc                   -> lokasi
      - .affil-code                  -> id_sinta & kode_pt (parse dari teks)
      - div.stat-num + div.stat-text -> Authors, Departments, Journals
      - div.pr-num  + div.pr-txt     -> SINTA Score Overall, 3Yr, Productivity, dst
    """
    url = PROFILE_URL.format(sinta_id=sinta_id)
    print(f"  Profil PT: {url}")
    open_with_retry(driver, url, wait_css="div.stat-num")

    profil = {"sinta_profile_url": url}

    # Nama PT
    for sel in [".univ-name h3", ".univ-name h2", "h3", "h2"]:
        try:
            text = safe_text(driver.find_element(By.CSS_SELECTOR, sel))
            if text and len(text) > 3:
                profil["nama_pt"] = text
                break
        except Exception:
            pass

    # Singkatan PT  (.affil-abbrev)
    try:
        profil["singkatan"] = safe_text(driver.find_element(By.CSS_SELECTOR, ".affil-abbrev"))
    except Exception:
        pass

    # Lokasi  (.affil-loc)
    try:
        profil["lokasi"] = safe_text(driver.find_element(By.CSS_SELECTOR, ".affil-loc"))
    except Exception:
        pass

    # ID SINTA dan kode PT  (.affil-code)
    # Contoh teks: "ID : 581  CODE : 011003"
    try:
        code_text = safe_text(driver.find_element(By.CSS_SELECTOR, ".affil-code"))
        m_id   = re.search(r"ID\s*:\s*(\d+)", code_text)
        m_code = re.search(r"CODE\s*:\s*(\S+)", code_text)
        if m_id:
            profil["id_sinta"] = m_id.group(1)
        if m_code:
            profil["kode_pt"] = m_code.group(1)
    except Exception:
        pass

    # Stat cards: Authors, Departments, Journals
    # HTML: <div class="stat-num">626</div><div class="stat-text">Authors</div>
    try:
        stat_nums  = driver.find_elements(By.CSS_SELECTOR, "div.stat-num")
        stat_texts = driver.find_elements(By.CSS_SELECTOR, "div.stat-text")
        for num_el, txt_el in zip(stat_nums, stat_texts):
            num = safe_text(num_el)
            lbl = safe_text(txt_el)
            if num and lbl:
                profil[lbl.lower().replace(" ", "_")] = num
    except Exception:
        pass

    # SINTA Score: Overall, 3Yr, Productivity, Productivity 3Yr
    # HTML: <div class="pr-num">648.451</div><div class="pr-txt">SINTA Score Overall</div>
    try:
        pr_nums = driver.find_elements(By.CSS_SELECTOR, "div.pr-num")
        pr_txts = driver.find_elements(By.CSS_SELECTOR, "div.pr-txt")
        for num_el, txt_el in zip(pr_nums, pr_txts):
            num = safe_text(num_el)
            lbl = safe_text(txt_el)
            if num and lbl:
                profil[lbl.lower().replace(" ", "_")] = num
    except Exception:
        pass

    return profil


# ---------------------------------------------------------------------------
# Parse satu item jurnal dari .list-item
# ---------------------------------------------------------------------------

def parse_journal_item(item):
    """
    Parse satu elemen .list-item menjadi dict data jurnal.
    Struktur HTML SINTA:
      .affil-name a           → nama jurnal + URL profil SINTA
      .affil-abbrev a         → link Google Scholar / Website / Editor URL
      .affil-loc a            → afiliasi PT
      .profile-id             → P-ISSN, E-ISSN, Subject Area (teks campuran)
      .stat-prev .num-stat    → akreditasi (S1/S2/S3/...) + Garuda Indexed
      .stat-profile .pr-num/.pr-txt → Impact, H5-index, Citations 5yr, Citations
    """
    j = {}

    # Nama jurnal dan URL profil SINTA jurnal
    try:
        name_el = item.find_element(By.CSS_SELECTOR, ".affil-name a")
        j["nama_jurnal"] = safe_text(name_el)
        j["sinta_url"]   = safe_attr(name_el, "href")
    except Exception:
        pass

    # Link eksternal: Google Scholar, Website, Editor URL
    try:
        abbrev_links = item.find_elements(By.CSS_SELECTOR, ".affil-abbrev a")
        for a in abbrev_links:
            text = safe_text(a).strip()
            href = safe_attr(a, "href")
            if "Google Scholar" in text:
                j["url_google_scholar"] = href
            elif "Editor" in text:
                j["url_editor"] = href
            elif "Website" in text:
                j["url_website"] = href
    except Exception:
        pass

    # P-ISSN, E-ISSN, Subject Area
    # Teks contoh: "P-ISSN : 16937619 | E-ISSN : 25804170  Subject Area : Science"
    try:
        pid_el = item.find_element(By.CSS_SELECTOR, ".profile-id")
        pid_text = safe_text(pid_el)

        m = re.search(r"P-ISSN\s*:\s*([\w]+)", pid_text)
        j["p_issn"] = m.group(1) if m else ""

        m = re.search(r"E-ISSN\s*:\s*([\w]+)", pid_text)
        j["e_issn"] = m.group(1) if m else ""

        m = re.search(r"Subject Area\s*:\s*(.+?)(?:\n|$)", pid_text)
        j["subject_area"] = m.group(1).strip() if m else ""
    except Exception:
        pass

    # Akreditasi (S1, S2, S3, S4, S5, S6) dan Garuda Indexed
    try:
        stat_prev = item.find_element(By.CSS_SELECTOR, ".stat-prev")

        # Akreditasi: teks seperti "S2 Accredited"
        try:
            akred_el = stat_prev.find_element(By.CSS_SELECTOR, ".accredited")
            akred_text = safe_text(akred_el)
            # Ambil level saja (S2, dst)
            m = re.search(r"(S\d+)", akred_text)
            j["akreditasi"] = m.group(1) if m else akred_text
        except Exception:
            j["akreditasi"] = ""

        # Garuda Indexed + URL Garuda
        try:
            garuda_el = stat_prev.find_element(By.CSS_SELECTOR, ".garuda-indexed")
            j["garuda_indexed"] = True
            # URL Garuda ada di <a> yang membungkus .garuda-indexed
            try:
                parent_a = stat_prev.find_element(
                    By.XPATH, ".//a[.//span[contains(@class,'garuda-indexed')]]"
                )
                j["url_garuda"] = safe_attr(parent_a, "href")
            except Exception:
                j["url_garuda"] = ""
        except Exception:
            j["garuda_indexed"] = False
            j["url_garuda"] = ""

    except Exception:
        pass

    # Statistik: Impact, H5-index, Citations 5yr, Citations
    # HTML: <div class="pr-num">42,14</div><div class="pr-txt">Impact</div>
    try:
        stat_prof = item.find_element(By.CSS_SELECTOR, ".stat-profile.journal-list-stat, .stat-profile")
        pr_nums = stat_prof.find_elements(By.CSS_SELECTOR, ".pr-num")
        pr_txts = stat_prof.find_elements(By.CSS_SELECTOR, ".pr-txt")
        for num_el, txt_el in zip(pr_nums, pr_txts):
            num = safe_text(num_el)
            lbl = safe_text(txt_el)
            if num and lbl:
                key = lbl.lower().replace("-", "_").replace(" ", "_")
                j[key] = num
    except Exception:
        pass

    return j


# ---------------------------------------------------------------------------
# Scrape semua halaman jurnal untuk satu PT
# ---------------------------------------------------------------------------

def scrape_journals_for_pt(driver, sinta_id):
    """
    Loop semua halaman /journals/index/{sinta_id}?page=N
    sampai tidak ada item lagi.
    Return list of dict jurnal.
    """
    all_journals = []
    page = 1

    while True:
        url = JOURNALS_URL.format(sinta_id=sinta_id, page=page)
        print(f"    Halaman {page}: {url}")
        ok = open_with_retry(driver, url, wait_css=".list-item, .content")
        if not ok:
            print(f"    Gagal membuka halaman {page}, stop")
            break

        items = driver.find_elements(By.CSS_SELECTOR, ".list-item")
        print(f"    Ditemukan {len(items)} item")

        if not items:
            break

        for item in items:
            j = parse_journal_item(item)
            if j.get("nama_jurnal"):
                all_journals.append(j)

        # Cek apakah ada halaman berikutnya
        # Cari link "Next" yang menuju page+1
        next_page = page + 1
        next_url = JOURNALS_URL.format(sinta_id=sinta_id, page=next_page)
        has_next = False
        try:
            pag_links = driver.find_elements(By.CSS_SELECTOR, ".pagination a")
            for a in pag_links:
                href = safe_attr(a, "href")
                if href and f"page={next_page}" in href:
                    has_next = True
                    break
        except Exception:
            pass

        if not has_next:
            break

        page = next_page
        time.sleep(BETWEEN_PAGE_WAIT)

    return all_journals


# ---------------------------------------------------------------------------
# Scrape satu PT (full)
# ---------------------------------------------------------------------------

def scrape_pt(driver, kode, nama):
    """
    Proses lengkap untuk satu PT:
      1. Cari SINTA ID dari pencarian kodept
      2. Ambil profil PT
      3. Ambil semua jurnal
    Return dict hasil.
    """
    print(f"\n[{kode}] {nama}")

    sinta_id = find_sinta_id(driver, kode)
    if not sinta_id:
        return {"sinta_id": None, "error": "PT tidak ditemukan di SINTA", "jurnal": []}

    profil = scrape_profil_pt(driver, sinta_id)
    jurnal_list = scrape_journals_for_pt(driver, sinta_id)

    print(f"  Total jurnal: {len(jurnal_list)}")

    return {
        "sinta_id":  sinta_id,
        "profil_pt": profil,
        "jurnal":    jurnal_list,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        pt_list = json.load(f)
    print(f"Jumlah PT: {len(pt_list)}")

    # Resume: load output yang sudah ada
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            results = json.load(f)
        print(f"Resume: {len(results)} PT sudah diproses")
    else:
        results = {}

    driver = init_driver(headless=True)

    try:
        for i, pt in enumerate(pt_list, 1):
            kode = pt.get("kode", "")
            nama = pt.get("target", pt.get("keyword", ""))

            if not kode:
                continue

            if kode in results:
                print(f"[{i}/{len(pt_list)}] Skip: {kode} {nama}")
                continue

            try:
                data = scrape_pt(driver, kode, nama)
                results[kode] = data
            except Exception as e:
                print(f"  ERROR: {e}")
                results[kode] = {"sinta_id": None, "error": str(e), "jurnal": []}

            # Auto-save setelah tiap PT
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

            time.sleep(BETWEEN_PT_WAIT)

    finally:
        driver.quit()

    total_jurnal = sum(len(v.get("jurnal", [])) for v in results.values())
    print(f"\n=== Selesai ===")
    print(f"Total PT      : {len(results)}")
    print(f"Total jurnal  : {total_jurnal}")
    print(f"Output        : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
