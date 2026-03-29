"""
Scraper PDDikti — Kumpulkan URL detail setiap Program Studi untuk satu PT.

Alur:
  1. Buka halaman pencarian → temukan PT yang namanya persis sama
  2. Buka halaman detail PT
  3. Pilih 'semua' di dropdown Tampilkan
  4. Untuk setiap baris prodi: klik nama prodi, tangkap URL via JS interceptor,
     kembali ke halaman PT
  5. Simpan ke outs/[kode_pt]_link_prodi.json

Usage:
    python scrape_pddikti_linkprodi.py [--keyword KW] [--nama NAMA] [--kode KODE]
"""

import os
import time
import json
import argparse

from selenium.webdriver.common.by import By
from firefox_helper import make_driver
from selenium.webdriver.support.ui import Select

OUT_DIR  = "/home/ubuntu/_chifoo/chifoo_backend/utils/outs"
BASE_URL = "https://pddikti.kemdiktisaintek.go.id"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def init_driver(headless=True):
    return make_driver(headless=headless)


# ---------------------------------------------------------------------------
# Halaman pencarian → URL detail PT
# ---------------------------------------------------------------------------

def find_pt_detail_url(driver, keyword, nama_pt_target):
    url = f"{BASE_URL}/search/{keyword.replace(' ', '%20')}"
    print(f"Membuka pencarian: {url}")
    driver.get(url)
    time.sleep(6)

    for table in driver.find_elements(By.TAG_NAME, "table"):
        rows = table.find_elements(By.TAG_NAME, "tr")
        if not rows:
            continue
        header_cells = (rows[0].find_elements(By.TAG_NAME, "th") or
                        rows[0].find_elements(By.TAG_NAME, "td"))
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

            for cell in cells:
                for a in cell.find_elements(By.TAG_NAME, "a"):
                    href = a.get_attribute("href") or ""
                    if "/detail-pt/" in href:
                        print(f"  [COCOK] '{nama}' → {href[:70]}...")
                        return href

    print(f"  [TIDAK DITEMUKAN] PT '{nama_pt_target}' tidak ditemukan.")
    return None


# ---------------------------------------------------------------------------
# Kumpulkan URL setiap prodi
# ---------------------------------------------------------------------------

def collect_prodi_urls(driver, pt_detail_url):
    """
    Buka halaman detail PT, pilih 'semua' di dropdown Tampilkan,
    lalu kumpulkan URL halaman detail tiap prodi dengan mengklik nama prodi
    dan menangkap URL via JS interceptor (tanpa berpindah halaman permanen).

    Returns: list of dict {"kode", "nama", "url"}
    """
    print(f"\n  Mengumpulkan URL prodi dari: {pt_detail_url[:60]}...")
    driver.get(pt_detail_url)
    time.sleep(7)

    selects = driver.find_elements(By.TAG_NAME, "select")
    if not selects:
        print("  [PERINGATAN] Dropdown Tampilkan tidak ditemukan.")
        return []

    Select(selects[0]).select_by_value("semua")
    time.sleep(5)

    tables = driver.find_elements(By.TAG_NAME, "table")
    if not tables:
        print("  [PERINGATAN] Tabel prodi tidak ditemukan.")
        return []

    rows = tables[0].find_elements(By.TAG_NAME, "tr")

    # Pass 1: kumpulkan semua (kode, nama) tanpa klik
    prodi_list = []
    for row in rows[3:]:
        cells = row.find_elements(By.TAG_NAME, "td")
        if not cells or len(cells) < 2:
            continue
        kode = cells[0].text.strip()
        nama = cells[1].text.strip()
        if kode:
            prodi_list.append({"kode": kode, "nama": nama})

    n_total = len(prodi_list)
    print(f"  Ditemukan {n_total} prodi, mulai mengumpulkan URL...")

    # Inject JS interceptor: tangkap URL dari pushState tanpa berpindah halaman
    driver.execute_script("""
        window.__capturedURL = null;
        var _orig = window.history.pushState.bind(window.history);
        window.history.pushState = function(state, title, url) {
            window.__capturedURL = url;
            _orig(state, title, url);
        };
    """)

    # Pass 2: klik tiap cell nama, tangkap URL, kembali ke halaman PT
    prodi_urls = []
    for idx, prodi in enumerate(prodi_list):
        kode = prodi["kode"]
        nama = prodi["nama"]

        # Reset interceptor
        driver.execute_script("window.__capturedURL = null;")

        # Cari cell nama prodi berdasarkan kode di kolom sebelumnya
        try:
            cell_nama = driver.find_element(
                By.XPATH,
                f"//td[normalize-space(text())='{kode}']/following-sibling::td[1]"
            )
        except Exception:
            try:
                table = driver.find_elements(By.TAG_NAME, "table")[0]
                all_rows = table.find_elements(By.TAG_NAME, "tr")
                match = next(
                    (r for r in all_rows
                     if r.find_elements(By.TAG_NAME, "td") and
                        r.find_elements(By.TAG_NAME, "td")[0].text.strip() == kode),
                    None,
                )
                cell_nama = match.find_elements(By.TAG_NAME, "td")[1] if match else None
            except Exception:
                cell_nama = None

        if not cell_nama:
            print(f"    [{idx+1}/{n_total}] {kode} — cell tidak ditemukan")
            prodi_urls.append({"kode": kode, "nama": nama, "url": ""})
            continue

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cell_nama)
        time.sleep(0.3)
        cell_nama.click()
        time.sleep(2)

        # Ambil URL yang ditangkap interceptor
        captured = driver.execute_script("return window.__capturedURL;")
        if captured:
            full_url = (f"{BASE_URL}{captured}" if captured.startswith("/") else captured)
        else:
            full_url = driver.current_url

        prodi_urls.append({"kode": kode, "nama": nama, "url": full_url})
        print(f"    [{idx+1}/{n_total}] {kode} | {nama[:35]:<35} | ...{full_url[-40:]}")

        # Kembali ke halaman PT
        driver.back()
        time.sleep(4)

        # Re-inject interceptor dan re-pilih 'semua' setelah back
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
                Select(selects[0]).select_by_value("semua")
                time.sleep(3)
        except Exception:
            pass

    print(f"  Total URL prodi terkumpul: {len(prodi_urls)}")
    return prodi_urls


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(keyword, nama_pt_target, kode_pt):
    os.makedirs(OUT_DIR, exist_ok=True)

    print("=" * 60)
    print(f"PDDikti Scraper (Link Prodi)  Keyword : {keyword}")
    print(f"                              Target  : {nama_pt_target}")
    print(f"                              Kode PT : {kode_pt}")
    print("=" * 60)

    driver = init_driver(headless=True)
    try:
        pt_url = find_pt_detail_url(driver, keyword, nama_pt_target)
        if not pt_url:
            return

        prodi_urls = collect_prodi_urls(driver, pt_url)
        if not prodi_urls:
            print("Tidak ada URL prodi yang berhasil dikumpulkan.")
            return

        output = {
            "kode_pt":      kode_pt,
            "nama_pt":      nama_pt_target,
            "jumlah_prodi": len(prodi_urls),
            "prodi":        prodi_urls,
        }
        out_path = f"{OUT_DIR}/{kode_pt}_link_prodi.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        kosong = sum(1 for p in prodi_urls if not p["url"])
        print(f"\nDisimpan: {out_path}")
        print(f"  → {len(prodi_urls)} prodi  |  URL kosong: {kosong}")

    finally:
        driver.quit()

    print("\nSelesai.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scraper PDDikti — Kumpulkan URL detail setiap Program Studi"
    )
    parser.add_argument("--keyword", default="universitas muhammadiyah yogyakarta",
                        help="Kata kunci pencarian")
    parser.add_argument("--nama",    default="UNIVERSITAS MUHAMMADIYAH YOGYAKARTA",
                        help="Nama PT persis (huruf kapital)")
    parser.add_argument("--kode",    default="051007",
                        help="Kode PT (prefix nama file output)")
    args = parser.parse_args()

    main(keyword=args.keyword, nama_pt_target=args.nama, kode_pt=args.kode)
