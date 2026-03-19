"""
Scraper PDDikti — Detail Dosen

Alur:
  1. Buka halaman pencarian: /search/[nama dosen] [nama pt]
     → URL ini disimpan sebagai referensi re-scrape di masa depan
  2. Klik tab "Dosen" pada hasil pencarian
  3. Temukan link "Lihat Detail" → buka halaman detail dosen
     (URL detail TIDAK disimpan — bersifat session-based, berubah tiap sesi)
  4. Scrape: profil (termasuk NUPTK, pendidikan terakhir, status),
             riwayat pendidikan, riwayat mengajar, penelitian,
             pengabdian masyarakat, publikasi karya, HKI/Paten
  5. Simpan ke outs/dosen/[nidn]_detaildosen.json
     Identifier stabil: NIDN (bukan URL)

Usage:
    python utils/scrape_pddikti_detaildosen.py --nama "YULIA FITRI" --pt "UNIVERSITAS MUHAMMADIYAH RIAU"
    python utils/scrape_pddikti_detaildosen.py --nama "YULIA FITRI" --pt "UNIVERSITAS MUHAMMADIYAH RIAU" --nidn "1007078501"
    python utils/scrape_pddikti_detaildosen.py --nama "YULIA FITRI" --pt "UNIVERSITAS MUHAMMADIYAH RIAU" --nidn "1007078501" --nuptk "2039763664230363" --pendidikan "S2" --status "Aktif"
    python utils/scrape_pddikti_detaildosen.py --debug   # tampilkan browser (tidak headless)
"""

import os
import re
import time
import json
import argparse
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

OUT_DIR  = Path("/home/ubuntu/_chifoo/chifoo_backend/utils/outs/dosen")
BASE_URL = "https://pddikti.kemdiktisaintek.go.id"


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
    return webdriver.Firefox(options=options)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def wait_text_loaded(driver, timeout=10):
    """Tunggu hingga loading spinner hilang atau konten muncul."""
    time.sleep(3)
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass
    time.sleep(2)


def get_table_as_list(table_el):
    """Konversi elemen tabel ke list of dict."""
    rows = table_el.find_elements(By.TAG_NAME, "tr")
    if not rows:
        return []
    headers = [th.text.strip() for th in rows[0].find_elements(By.TAG_NAME, "th")]
    if not headers:
        headers = [td.text.strip() for td in rows[0].find_elements(By.TAG_NAME, "td")]
    result = []
    for row in rows[1:]:
        cells = row.find_elements(By.TAG_NAME, "td")
        if not cells:
            continue
        row_dict = {}
        for i, cell in enumerate(cells):
            key = headers[i] if i < len(headers) else f"col_{i}"
            row_dict[key] = cell.text.strip()
        result.append(row_dict)
    return result


def get_kv_pairs(section_el):
    """Ambil pasangan key-value dari tabel profil (2 kolom: label | nilai)."""
    result = {}
    rows = section_el.find_elements(By.TAG_NAME, "tr")
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) >= 2:
            key = cells[0].text.strip().rstrip(":")
            val = cells[1].text.strip()
            if key:
                result[key] = val
    return result


# ---------------------------------------------------------------------------
# Step 1: Cari URL detail dosen dari halaman search
# ---------------------------------------------------------------------------

def find_dosen_detail_url(driver, nama_dosen, nama_pt, nidn_target=None):
    keyword = f"{nama_dosen} {nama_pt}"
    url_pencarian = f"{BASE_URL}/search/{keyword.replace(' ', '%20')}"
    print(f"\n[1] Membuka pencarian: {url_pencarian}")
    driver.get(url_pencarian)
    wait_text_loaded(driver, timeout=12)

    # Cari dan klik tab "Dosen"
    tab_dosen = None
    for el in driver.find_elements(By.XPATH, "//*[contains(@class,'tab') or contains(@role,'tab')]"):
        if "dosen" in el.text.strip().lower():
            tab_dosen = el
            break

    # Jika tidak ketemu via role, coba cari button/li/div dengan teks "Dosen"
    if not tab_dosen:
        for tag in ["button", "li", "div", "a", "span"]:
            for el in driver.find_elements(By.TAG_NAME, tag):
                txt = el.text.strip()
                if txt.lower() in ("dosen", "dosen (aktif)") or re.match(r"^dosen\s*\(?\d*\)?$", txt, re.I):
                    tab_dosen = el
                    break
            if tab_dosen:
                break

    if tab_dosen:
        print(f"[1] Klik tab Dosen: '{tab_dosen.text.strip()}'")
        try:
            driver.execute_script("arguments[0].click();", tab_dosen)
            time.sleep(4)
        except Exception as e:
            print(f"  [WARN] Gagal klik tab: {e}")
    else:
        print("[1] Tab Dosen tidak ditemukan, lanjut cari link langsung...")

    # Kumpulkan semua link "Lihat Detail" — hanya /detail-dosen/
    detail_links = []
    for a in driver.find_elements(By.TAG_NAME, "a"):
        href = a.get_attribute("href") or ""
        if "/detail-dosen/" in href:
            detail_links.append({"text": a.text.strip(), "href": href})

    print(f"[1] Ditemukan {len(detail_links)} link detail dosen")
    for lnk in detail_links:
        print(f"    {lnk['text']} → {lnk['href'][:80]}")

    if not detail_links:
        print("[DEBUG] Page source snippet:")
        print(driver.page_source[:3000])
        return None, url_pencarian

    # Jika hanya 1, langsung pakai
    if len(detail_links) == 1:
        return detail_links[0]["href"], url_pencarian

    # Jika >1, coba cocokkan dengan NIDN jika diberikan
    if nidn_target:
        for lnk in detail_links:
            if nidn_target in lnk["href"]:
                print(f"[1] Cocok NIDN {nidn_target}: {lnk['href'][:80]}")
                return lnk["href"], url_pencarian

    # Ambil yang pertama
    print(f"[1] Menggunakan link pertama (ada {len(detail_links)} kandidat)")
    return detail_links[0]["href"], url_pencarian


# ---------------------------------------------------------------------------
# Helpers scrape tabel dari halaman aktif
# ---------------------------------------------------------------------------

def scrape_tables_on_page(driver, label_hint="", container=None):
    """
    Ambil semua tabel yang berisi data dari container (default: seluruh halaman).
    Kembalikan list of {headers, rows, label}.
    """
    root = container if container else driver
    results = []
    for i, tbl in enumerate(root.find_elements(By.TAG_NAME, "table")):
        rows = tbl.find_elements(By.TAG_NAME, "tr")
        if not rows:
            continue

        headers = [th.text.strip() for th in rows[0].find_elements(By.TAG_NAME, "th")]
        if not headers or all(h == "" for h in headers):
            continue  # skip tabel tanpa header

        rows_data = get_table_as_list(tbl)
        # Skip jika semua sel kosong
        if not rows_data or all(all(v == "" for v in r.values()) for r in rows_data):
            continue

        results.append({"headers": headers, "rows": rows_data, "hint": label_hint})
        print(f"  [{label_hint or 'default'} tbl{i}] {len(rows_data)} baris | {headers}")

    return results


def get_active_tabpanel(driver):
    """
    Cari elemen tabpanel yang sedang aktif/visible.
    Return elemen panel atau None jika tidak ditemukan.
    """
    selectors = [
        "//*[@role='tabpanel' and not(@aria-hidden='true') and not(contains(@style,'display: none'))]",
        "//*[@role='tabpanel'][contains(@class,'active')]",
        "//*[contains(@class,'tab-pane') and contains(@class,'active') and contains(@class,'show')]",
        "//*[contains(@class,'tab-pane') and contains(@class,'active')]",
        "//*[contains(@class,'tab-content')]//*[contains(@class,'active')]",
    ]
    for sel in selectors:
        try:
            els = driver.find_elements(By.XPATH, sel)
            # Pilih panel yang benar-benar visible dan punya konten
            for el in els:
                if el.is_displayed() and el.text.strip():
                    return el
        except Exception:
            continue
    return None


def find_and_click_tab(driver, keywords):
    """
    Cari tab/button dengan teks yang mengandung salah satu keyword,
    klik, tunggu konten load. Return teks tab yang diklik atau None.
    """
    for tag in ["button", "li", "a", "div", "span"]:
        for el in driver.find_elements(By.TAG_NAME, tag):
            txt = el.text.strip()
            txt_lower = txt.lower()
            if any(kw in txt_lower for kw in keywords):
                # Pastikan elemen visible & clickable
                try:
                    if not el.is_displayed():
                        continue
                    driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(4)
                    print(f"  → Klik tab: '{txt}'")
                    return txt
                except Exception:
                    continue
    return None


# ---------------------------------------------------------------------------
# Step 2: Scrape halaman detail dosen (semua tab)
# ---------------------------------------------------------------------------

def scrape_detail_dosen(driver, detail_url, url_pencarian="",
                        nuptk_input="", pendidikan_input="", status_input="",
                        profile_only=False):
    print(f"\n[2] Membuka detail dosen: {detail_url[:80]}...")
    driver.get(detail_url)
    wait_text_loaded(driver, timeout=15)

    data = {
        # URL pencarian disimpan sebagai referensi re-scrape (stabil, berbasis nama)
        # URL detail TIDAK disimpan — bersifat session-based
        "url_pencarian":      url_pencarian,
        "profil":             {},
        "riwayat_pendidikan": [],
        "riwayat_mengajar":   {},   # dict: {"Ganjil 2024": [{...}], ...}
        "penelitian":         [],
        "pengabdian":         [],
        "publikasi":          [],
        "hki_paten":          [],
        "raw_sections":       {}
    }

    # ------------------------------------------------------------------
    # 2a. Profil — ambil dari body text via regex
    # Termasuk: NUPTK, Pendidikan (terakhir), Status
    # ------------------------------------------------------------------
    profil_keys = [
        "NIDN", "NUPTK", "NIP", "Nama", "Jenis Kelamin", "Tanggal Lahir",
        "Program Studi", "Perguruan Tinggi",
        "Jabatan Fungsional", "Pendidikan Tertinggi",
        "Ikatan Kerja", "Status Aktif", "Status",
    ]
    page_text = driver.find_element(By.TAG_NAME, "body").text
    for key in profil_keys:
        pattern = rf"(?:^|\n){re.escape(key)}\s*[:\n]\s*([^\n]+)"
        m = re.search(pattern, page_text, re.IGNORECASE | re.MULTILINE)
        if m:
            data["profil"][key] = m.group(1).strip()

    # Isi dari input argumen jika tidak ditemukan di halaman
    if nuptk_input and "NUPTK" not in data["profil"]:
        data["profil"]["NUPTK"] = nuptk_input
    if pendidikan_input and "Pendidikan Tertinggi" not in data["profil"]:
        data["profil"]["Pendidikan Tertinggi"] = pendidikan_input
    if status_input and "Status" not in data["profil"]:
        data["profil"]["Status"] = status_input

    print(f"[2a] Profil: {data['profil']}")

    if profile_only:
        print("[2b-2f] profile_only=True — skip semua tab")
        return data

    # ------------------------------------------------------------------
    # 2b. Tab default (halaman awal) — riwayat pendidikan & penelitian
    # ------------------------------------------------------------------
    print("[2b] Scrape tab default (riwayat pendidikan, penelitian)...")
    for item in scrape_tables_on_page(driver, "default"):
        h_lower = " ".join(item["headers"]).lower()
        if any(k in h_lower for k in ["perguruan tinggi", "gelar", "jenjang"]):
            data["riwayat_pendidikan"].extend(item["rows"])
        elif any(k in h_lower for k in ["penelitian", "judul penelitian"]):
            data["penelitian"].extend(item["rows"])
        else:
            data["raw_sections"][f"default_{len(data['raw_sections'])}"] = item["rows"]

    # ------------------------------------------------------------------
    # 2c. Tab Riwayat Mengajar — ada dropdown/pilihan per semester
    # ------------------------------------------------------------------
    print("[2c] Mencari tab Riwayat Mengajar...")
    clicked = find_and_click_tab(driver, ["riwayat mengajar", "mengajar"])
    if clicked:
        time.sleep(3)
        from selenium.webdriver.support.ui import Select as SeleniumSelect

        # Ambil panel aktif — scrape hanya dalam panel ini agar tidak tercampur tabel lain
        panel = get_active_tabpanel(driver)
        if panel:
            print(f"  Tabpanel aktif ditemukan: {panel.text[:60]}...")
        else:
            print("  Tabpanel aktif tidak terdeteksi, fallback ke seluruh halaman")

        SEM_PATTERN = re.compile(r"\d{4}/\d{4}\s+(Ganjil|Genap)", re.IGNORECASE)

        def _collect_semester_items(root):
            """Cari semua elemen clickable yang labelnya semester akademik."""
            found = []
            seen = set()
            for tag in ["li", "button", "div", "span", "a", "option"]:
                for el in root.find_elements(By.TAG_NAME, tag):
                    try:
                        txt = el.text.strip()
                        if SEM_PATTERN.match(txt) and txt not in seen and el.is_displayed():
                            found.append((txt, el))
                            seen.add(txt)
                    except Exception:
                        continue
            return found

        def _scrape_mengajar_native_select(root):
            """Coba native <select> terlebih dulu."""
            selects = root.find_elements(By.TAG_NAME, "select")
            if not selects:
                return False
            sel = SeleniumSelect(selects[0])
            options = [(o.get_attribute("value"), o.text.strip())
                       for o in sel.options if o.get_attribute("value")]
            if not options:
                return False
            print(f"  Native select: {len(options)} semester")
            for val, sem_label in options:
                try:
                    SeleniumSelect((get_active_tabpanel(driver) or driver)
                                   .find_elements(By.TAG_NAME, "select")[0]).select_by_value(val)
                    time.sleep(3)
                    active = get_active_tabpanel(driver) or driver
                    rows = []
                    for it in scrape_tables_on_page(driver, f"mengajar_{sem_label}", container=active):
                        rows.extend(it["rows"])
                    if rows:
                        data["riwayat_mengajar"][sem_label] = rows
                except Exception as e:
                    print(f"  [WARN] native select '{sem_label}': {e}")
            return True

        MENGAJAR_HEADERS = ["mata kuliah", "sks", "kelas", "matkul",
                            "nama mata kuliah", "kode mata kuliah", "nama matakuliah"]
        BUKAN_MENGAJAR  = ["judul penelitian", "judul pengabdian", "judul karya",
                            "perguruan tinggi", "gelar akademik"]

        def _wait_for_mengajar_table(timeout=15):
            """Poll sampai muncul tabel dengan header mengajar, atau timeout."""
            deadline = time.time() + timeout
            while time.time() < deadline:
                for tbl in driver.find_elements(By.TAG_NAME, "table"):
                    rows = tbl.find_elements(By.TAG_NAME, "tr")
                    if not rows:
                        continue
                    ths = [th.text.strip().lower() for th in rows[0].find_elements(By.TAG_NAME, "th")]
                    if any(k in " ".join(ths) for k in MENGAJAR_HEADERS):
                        return True
                time.sleep(1)
            return False

        def _scrape_mengajar_custom_dropdown(root):
            """Klik tiap item semester dari custom dropdown/list."""
            sem_items = _collect_semester_items(root)
            if not sem_items:
                return False
            print(f"  Custom dropdown: {len(sem_items)} semester — {[s[0] for s in sem_items]}")
            for sem_label, el in sem_items:
                try:
                    old_count = len(driver.find_elements(By.TAG_NAME, "table"))
                    driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    driver.execute_script("arguments[0].click();", el)
                    # Poll sampai tabel mengajar muncul, maks 15 detik
                    found = _wait_for_mengajar_table(timeout=15)
                    # Scroll untuk trigger lazy load
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
                    if not found:
                        time.sleep(2)  # satu tunggu lagi setelah scroll
                    # Scan SEMUA tabel di halaman, filter by header mengajar
                    rows = []
                    for it in scrape_tables_on_page(driver, f"mengajar_{sem_label}"):
                        h_lower = " ".join(it["headers"]).lower()
                        if any(k in h_lower for k in BUKAN_MENGAJAR):
                            continue
                        if any(k in h_lower for k in MENGAJAR_HEADERS):
                            rows.extend(it["rows"])
                    if rows:
                        data["riwayat_mengajar"][sem_label] = rows
                        print(f"    {sem_label}: {len(rows)} baris")
                    else:
                        print(f"    {sem_label}: kosong")
                except Exception as e:
                    print(f"  [WARN] custom click '{sem_label}': {e}")
            return True

        root = panel if panel else driver
        if not _scrape_mengajar_native_select(root):
            if not _scrape_mengajar_custom_dropdown(root):
                # Fallback: scrape langsung tabel dalam panel
                items = scrape_tables_on_page(driver, "mengajar", container=root)
                for it in items:
                    h_lower = " ".join(it["headers"]).lower()
                    if any(k in h_lower for k in ["mata kuliah", "sks", "kelas", "matkul",
                                                   "nama mata kuliah", "kode mata kuliah"]):
                        data["riwayat_mengajar"]["default"] = data["riwayat_mengajar"].get("default", [])
                        data["riwayat_mengajar"]["default"].extend(it["rows"])
        if not data["riwayat_mengajar"]:
            print("  Tidak ada data mengajar.")
    else:
        print("  Tab Riwayat Mengajar tidak ditemukan.")

    # ------------------------------------------------------------------
    # 2d. Tab Pengabdian Masyarakat
    # ------------------------------------------------------------------
    print("[2d] Mencari tab Pengabdian Masyarakat...")
    clicked = find_and_click_tab(driver, ["pengabdian"])
    if clicked:
        for item in scrape_tables_on_page(driver, "pengabdian"):
            data["pengabdian"].extend(item["rows"])
    else:
        print("  Tab Pengabdian tidak ditemukan.")

    # ------------------------------------------------------------------
    # 2e. Tab Publikasi Karya
    # ------------------------------------------------------------------
    print("[2e] Mencari tab Publikasi Karya...")
    clicked = find_and_click_tab(driver, ["publikasi"])
    if clicked:
        for item in scrape_tables_on_page(driver, "publikasi"):
            data["publikasi"].extend(item["rows"])
    else:
        print("  Tab Publikasi tidak ditemukan.")

    # ------------------------------------------------------------------
    # 2f. Tab HKI / Paten
    # ------------------------------------------------------------------
    print("[2f] Mencari tab HKI/Paten...")
    clicked = find_and_click_tab(driver, ["hki", "paten", "hak kekayaan"])
    if clicked:
        for item in scrape_tables_on_page(driver, "hki"):
            data["hki_paten"].extend(item["rows"])
    else:
        print("  Tab HKI/Paten tidak ditemukan.")

    # ------------------------------------------------------------------
    # 2g. Ambil daftar semua tab yang ada (untuk analisis)
    # ------------------------------------------------------------------
    all_tabs = []
    for tag in ["button", "li"]:
        for el in driver.find_elements(By.TAG_NAME, tag):
            txt = el.text.strip()
            if txt and len(txt) < 60 and el.is_displayed():
                role = el.get_attribute("role") or ""
                cls  = el.get_attribute("class") or ""
                if "tab" in role.lower() or "tab" in cls.lower() or tag == "button":
                    all_tabs.append(txt)
    data["_tabs_found"] = list(dict.fromkeys(all_tabs))  # deduplicate

    # ------------------------------------------------------------------
    # 2h. (ID detail tidak disimpan — session-based, tidak bisa diandalkan)
    # ------------------------------------------------------------------

    return data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape detail dosen PDDikti")
    parser.add_argument("--nama",       required=True, help="Nama lengkap dosen")
    parser.add_argument("--pt",         required=True, help="Nama PT")
    parser.add_argument("--nidn",       default="",    help="NIDN (untuk disambiguasi & nama file)")
    parser.add_argument("--nuptk",      default="",    help="NUPTK dosen (dari data homebase prodi)")
    parser.add_argument("--pendidikan", default="",    help="Pendidikan terakhir, e.g. S2, S3")
    parser.add_argument("--status",     default="",    help="Status dosen, e.g. Aktif")
    parser.add_argument("--profile-only", action="store_true", help="Hanya ambil profil utama, skip semua tab")
    parser.add_argument("--debug",        action="store_true", help="Tampilkan browser (tidak headless)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Tentukan nama file output: outs/dosen/[kode_pt]/[nidn]_[nama].json
    safe_nama = re.sub(r"[^\w]", "_", args.nama.upper())
    nidn_str  = args.nidn or "no_nidn"
    out_file  = OUT_DIR / f"{nidn_str}_{safe_nama}.json"

    print(f"\n{'='*60}")
    print(f"Dosen : {args.nama}")
    print(f"PT    : {args.pt}")
    print(f"NIDN  : {args.nidn or '(tidak diberikan)'}")
    print(f"Output: {out_file}")
    print(f"{'='*60}")

    driver = init_driver(headless=not args.debug)
    try:
        detail_url, url_pencarian = find_dosen_detail_url(
            driver, args.nama, args.pt, nidn_target=args.nidn or None
        )

        if not detail_url:
            print("\n[ERROR] URL detail dosen tidak ditemukan.")
            return

        data = scrape_detail_dosen(
            driver, detail_url,
            url_pencarian    = url_pencarian or "",
            nuptk_input      = args.nuptk,
            pendidikan_input = args.pendidikan,
            status_input     = args.status,
            profile_only     = args.profile_only,
        )
        data["input"] = {
            "nama": args.nama, "pt": args.pt,
            "nidn": args.nidn, "nuptk": args.nuptk,
            "pendidikan": args.pendidikan, "status": args.status,
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        size_kb = out_file.stat().st_size / 1024
        print(f"\n[OK] Disimpan ke {out_file} ({size_kb:.1f} KB)")
        print(f"     Profil keys       : {list(data['profil'].keys())}")
        print(f"     Riwayat pendidikan: {len(data['riwayat_pendidikan'])} baris")
        print(f"     Riwayat mengajar  : {len(data['riwayat_mengajar'])} semester")
        for sem, rows in data['riwayat_mengajar'].items():
            print(f"       {sem}: {len(rows)} matkul")
        print(f"     Penelitian        : {len(data['penelitian'])} baris")
        print(f"     Pengabdian        : {len(data['pengabdian'])} baris")
        print(f"     Publikasi         : {len(data['publikasi'])} baris")
        print(f"     HKI/Paten         : {len(data['hki_paten'])} baris")
        print(f"     Raw sections      : {list(data['raw_sections'].keys())}")
        print(f"     Tabs ditemukan    : {data.get('_tabs_found', [])}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
