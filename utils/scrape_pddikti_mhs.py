"""
Scraper PDDikti — Daftar Program Studi + Mahasiswa 5 Semester Terakhir

Alur:
  1. Buka halaman pencarian → temukan PT yang namanya persis sama
  2. Buka detail PT → ambil semua program studi (dropdown 'semua')
  3. Untuk tiap prodi: buka halaman detail → ambil data mahasiswa 5 semester terakhir
  4. Simpan ke outs/[kode_pt]_mhs.json (satu file gabungan semua prodi)

Usage:
    python scrape_pddikti_mhs.py [--keyword KW] [--nama NAMA] [--kode KODE] [--semester N]
"""

import os
import re
import time
import json
import argparse

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


OUT_DIR = "/home/ubuntu/projects/utils/outs"
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
# Halaman pencarian
# ---------------------------------------------------------------------------

def find_pt_detail_url(driver, keyword, nama_pt_target):
    """
    Buka halaman search, cari baris PT yang namanya persis sama,
    kembalikan URL detail PT-nya.
    """
    url = f"{BASE_URL}/search/{keyword.replace(' ', '%20')}"
    print(f"Membuka pencarian: {url}")
    driver.get(url)
    time.sleep(6)

    tables = driver.find_elements(By.TAG_NAME, "table")
    for table in tables:
        rows = table.find_elements(By.TAG_NAME, "tr")
        if not rows:
            continue
        header_cells = rows[0].find_elements(By.TAG_NAME, "th") or \
                       rows[0].find_elements(By.TAG_NAME, "td")
        headers = [h.text.strip() for h in header_cells]

        for row in rows[1:]:
            cells = row.find_elements(By.TAG_NAME, "td")
            if not cells:
                continue
            row_dict = dict(zip(headers, [c.text.strip() for c in cells]))

            nama = row_dict.get("Nama Perguruan TInggi",
                   row_dict.get("Nama Perguruan Tinggi", "")).strip()

            if nama.upper() != nama_pt_target.strip().upper():
                continue
            if len(nama) != len(nama_pt_target.strip()):
                continue

            # Ambil link detail dari kolom Aksi
            for cell in cells:
                for a in cell.find_elements(By.TAG_NAME, "a"):
                    href = a.get_attribute("href") or ""
                    if "/detail-pt/" in href:
                        print(f"  [COCOK] '{nama}' → {href}")
                        return href

    print(f"  [TIDAK DITEMUKAN] Tidak ada PT dengan nama persis '{nama_pt_target}'")
    return None


# ---------------------------------------------------------------------------
# Daftar Program Studi
# ---------------------------------------------------------------------------

def get_prodi_list(driver, pt_url):
    """
    Buka halaman detail PT, pilih 'semua' di dropdown,
    kembalikan list dict tiap prodi beserta URL detail-nya.
    """
    print(f"\nMembuka detail PT: {pt_url[:70]}...")
    driver.get(pt_url)
    time.sleep(7)

    # Pilih "semua" (atau opsi terbesar jika "semua" tidak ada)
    selects = driver.find_elements(By.TAG_NAME, "select")
    if not selects:
        print("  [PERINGATAN] Tidak ada dropdown ditemukan.")
        return []

    sel_obj = Select(selects[0])
    opt_values = [o.get_attribute("value") for o in sel_obj.options]
    if "semua" in opt_values:
        sel_obj.select_by_value("semua")
        print("  Dropdown 'semua' dipilih...")
    else:
        sel_obj.select_by_value(opt_values[-1])
        print(f"  Dropdown '{opt_values[-1]}' dipilih (tidak ada opsi semua)...")
    time.sleep(5)

    all_tables = driver.find_elements(By.TAG_NAME, "table")
    if not all_tables:
        print("  [PERINGATAN] Tidak ada tabel ditemukan.")
        return []

    table = all_tables[0]
    all_rows = table.find_elements(By.TAG_NAME, "tr")
    print(f"  Total baris di tabel: {len(all_rows)}")

    KOLOM = [
        "Kode", "Nama Program Studi", "Status", "Jenjang", "Akreditasi",
        "Data Pelaporan (Penghitung)", "Dosen Tetap", "Dosen Tidak Tetap",
        "Total Dosen", "Jumlah Mahasiswa", "Rasio Dosen/Mahasiswa",
    ]

    # Pass 1 — kumpulkan kode + nama dari tabel (tanpa klik)
    prodi_list = []
    for row in all_rows[3:]:
        cells = row.find_elements(By.TAG_NAME, "td")
        if not cells or not any(c.text.strip() for c in cells):
            continue
        values = [c.text.strip() for c in cells]
        row_dict = {}
        for j, col in enumerate(KOLOM):
            row_dict[col] = values[j] if j < len(values) else ""
        if row_dict.get("Kode"):
            prodi_list.append(row_dict)

    n_total = len(prodi_list)
    print(f"  Ditemukan {n_total} program studi, mulai mengumpulkan URL...")

    # Inject JS pushState interceptor
    driver.execute_script("""
        window.__capturedURL = null;
        var _orig = window.history.pushState.bind(window.history);
        window.history.pushState = function(state, title, url) {
            window.__capturedURL = url;
            _orig(state, title, url);
        };
    """)

    # Pass 2 — klik tiap cell nama, tangkap URL, kembali
    for idx, prodi in enumerate(prodi_list):
        kode = prodi["Kode"]
        driver.execute_script("window.__capturedURL = null;")

        try:
            cell_nama = driver.find_element(
                By.XPATH,
                f"//td[normalize-space(text())='{kode}']/following-sibling::td[1]"
            )
        except Exception:
            print(f"    [{idx+1}/{n_total}] {kode} — cell tidak ditemukan")
            prodi["url"] = ""
            continue

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cell_nama)
        time.sleep(0.3)
        cell_nama.click()
        time.sleep(2)

        captured = driver.execute_script("return window.__capturedURL;")
        if captured:
            full_url = f"{BASE_URL}{captured}" if captured.startswith("/") else captured
        else:
            full_url = driver.current_url

        prodi["url"] = full_url
        print(f"    [{idx+1}/{n_total}] {kode} | {prodi['Nama Program Studi'][:35]}")

        driver.back()
        time.sleep(4)

        # Re-inject interceptor + re-pilih semua
        driver.execute_script("""
            window.__capturedURL = null;
            var _orig = window.history.pushState.bind(window.history);
            window.history.pushState = function(state, title, url) {
                window.__capturedURL = url;
                _orig(state, title, url);
            };
        """)
        try:
            selects = driver.find_elements(By.TAG_NAME, "select")
            if selects:
                cur_values = [o.get_attribute("value")
                              for o in Select(selects[0]).options]
                target = "semua" if "semua" in cur_values else cur_values[-1]
                Select(selects[0]).select_by_value(target)
                time.sleep(3)
        except Exception:
            pass

    return prodi_list


# ---------------------------------------------------------------------------
# Mahasiswa per semester (N semester terakhir)
# ---------------------------------------------------------------------------

def get_mahasiswa(driver, prodi_url, n_semester=5):
    """
    Buka halaman detail prodi, klik tab Mahasiswa,
    kembalikan N baris pertama (semester terbaru).
    """
    driver.get(prodi_url)
    time.sleep(7)

    try:
        driver.find_element(By.CSS_SELECTOR, "[data-value='mahasiswa']").click()
        time.sleep(3)
    except Exception as e:
        print(f"      Gagal klik tab Mahasiswa: {e}")
        return []

    tables = driver.find_elements(By.TAG_NAME, "table")
    mhs_table = None
    for tbl in tables:
        header_cells = tbl.find_elements(
            By.CSS_SELECTOR, "tr:first-child th, tr:first-child td"
        )
        texts = [c.text.strip() for c in header_cells]
        if "Semester" in texts and "Jumlah Mahasiswa" in texts:
            mhs_table = tbl
            break

    if not mhs_table:
        return []

    rows = mhs_table.find_elements(By.TAG_NAME, "tr")
    mahasiswa = []
    for row in rows[1:]:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) >= 2:
            sem = cells[0].text.strip()
            jml = cells[1].text.strip()
            if sem:
                mahasiswa.append({"semester": sem, "jumlah_mahasiswa": jml})

    # Ambil N semester terakhir (baris pertama = terbaru)
    return mahasiswa[:n_semester]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(keyword, nama_pt_target, kode_pt, n_semester):
    os.makedirs(OUT_DIR, exist_ok=True)

    print("=" * 60)
    print(f"PDDikti Scraper (Mahasiswa)  Keyword : {keyword}")
    print(f"                             Target  : {nama_pt_target}")
    print(f"                             Kode PT : {kode_pt}")
    print(f"                             Semester: {n_semester} terakhir")
    print("=" * 60)

    driver = init_driver(headless=True)
    try:
        # 1. Temukan URL detail PT
        pt_url = find_pt_detail_url(driver, keyword, nama_pt_target)
        if not pt_url:
            return

        # 2. Ambil daftar semua program studi + URL tiap prodi
        prodi_list = get_prodi_list(driver, pt_url)
        if not prodi_list:
            print("Tidak ada program studi ditemukan.")
            return

        n_total = len(prodi_list)
        print(f"\n{'='*60}")
        print(f"Total prodi: {n_total}. Mulai ambil data mahasiswa...")

        # 3. Untuk tiap prodi: ambil mahasiswa N semester terakhir
        hasil = []
        for i, prodi in enumerate(prodi_list, 1):
            kode_ps = prodi["Kode"]
            nama_ps = prodi["Nama Program Studi"]
            url_ps  = prodi.get("url", "")

            entry = {
                "kode_pt":           kode_pt,
                "kode_ps":           kode_ps,
                "nama_ps":           nama_ps,
                "jenjang":           prodi.get("Jenjang", ""),
                "akreditasi":        prodi.get("Akreditasi", ""),
                "status":            prodi.get("Status", ""),
                "jumlah_mahasiswa":  prodi.get("Jumlah Mahasiswa", ""),
                "url":               url_ps,
                "mahasiswa":         [],
            }

            if not url_ps:
                print(f"  [{i}/{n_total}] {kode_ps} — URL kosong, lewati")
                hasil.append(entry)
                continue

            print(f"\n  [{i}/{n_total}] {kode_ps} — {nama_ps}")
            entry["mahasiswa"] = get_mahasiswa(driver, url_ps, n_semester)
            print(f"      → {len(entry['mahasiswa'])} semester")
            hasil.append(entry)

        # 4. Simpan ke satu file gabungan
        out_path = f"{OUT_DIR}/{kode_pt}_mhs.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(hasil, f, ensure_ascii=False, indent=2)
        print(f"\nDisimpan: {out_path}  ({len(hasil)} prodi)")

    finally:
        driver.quit()

    print("\nSelesai.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scraper PDDikti — daftar prodi + mahasiswa N semester terakhir"
    )
    parser.add_argument("--keyword",  default="universitas muhammadiyah malang",
                        help="Kata kunci pencarian")
    parser.add_argument("--nama",     default="UNIVERSITAS MUHAMMADIYAH MALANG",
                        help="Nama PT persis (huruf kapital)")
    parser.add_argument("--kode",     default="071024",
                        help="Kode PT (prefix nama file output)")
    parser.add_argument("--semester", default=5, type=int,
                        help="Jumlah semester terakhir yang diambil (default: 5)")
    args = parser.parse_args()

    main(
        keyword=args.keyword,
        nama_pt_target=args.nama,
        kode_pt=args.kode,
        n_semester=args.semester,
    )
