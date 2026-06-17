"""
Scraper PDDikti — Data Pelaporan Tahunan per Semester

Alur:
  1. Buka halaman pencarian → temukan PT yang namanya persis sama
  2. Buka detail PT
  3. Identifikasi dua dropdown:
       - 'Tampilkan' : jumlah baris (10 / 25 / 50 / semua)
       - 'Semester'  : pilihan semester Data Pelaporan Tahunan
  4. Untuk N semester terakhir:
       a. Pilih semester di dropdown Semester
       b. Pilih 'semua' di dropdown Tampilkan
       c. Baca seluruh baris program studi dari tabel
  5. Simpan ke outs/[kode_pt]_pelaporan.json

Usage:
    python scrape_pddikti_pelaporan.py [--keyword KW] [--nama NAMA] [--kode KODE] [--semester N]
"""

import os
import time
import json
import argparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from firefox_helper import make_driver
from selenium.webdriver.support.ui import Select

OUT_DIR = "/home/ubuntu/_chifoo/chifoo_backend/utils/outs"
BASE_URL = "https://pddikti.kemdiktisaintek.go.id"

KOLOM_PRODI = [
    "Kode", "Nama Program Studi", "Status", "Jenjang", "Akreditasi",
    "Jumlah Dosen Penghitung Rasio", "Dosen Tetap", "Dosen Tidak Tetap",
    "Total Dosen", "Jumlah Mahasiswa", "Rasio Dosen/Mahasiswa",
]


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def init_driver(headless=True):
    return make_driver(headless=headless)


def _dismiss_overlay(driver):
    """Tutup overlay/modal yang menghalangi halaman jika ada."""
    from selenium.webdriver.common.keys import Keys
    try:
        overlays = driver.find_elements(By.CSS_SELECTOR, "div.absolute.inset-0")
        if not overlays:
            return
        for overlay in overlays:
            if not overlay.is_displayed():
                continue
            # Coba cari tombol close (×, X, Tutup, Close) di dalam/dekat overlay
            for selector in [
                "button[aria-label='close']", "button[aria-label='Close']",
                "button.close", "[data-dismiss='modal']",
                "button svg", "button",
            ]:
                btns = driver.find_elements(By.CSS_SELECTOR, selector)
                for btn in btns:
                    txt = (btn.text or btn.get_attribute("aria-label") or "").strip().lower()
                    if txt in ("", "×", "x", "close", "tutup", "ok"):
                        try:
                            btn.click()
                            time.sleep(1)
                            return
                        except Exception:
                            pass
            # Fallback: tekan Escape
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(1)
    except Exception:
        pass


def _wait_no_overlay(driver, timeout=15):
    """Tutup overlay jika ada, lalu tunggu sampai hilang."""
    _dismiss_overlay(driver)
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, "div.absolute.inset-0")
            )
        )
    except Exception:
        pass
    time.sleep(0.5)


def _js_select(driver, select_el, value):
    """Set nilai select via JavaScript (bypass overlay)."""
    driver.execute_script(
        "arguments[0].value = arguments[1]; "
        "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
        select_el, value
    )


# ---------------------------------------------------------------------------
# Halaman pencarian → URL detail PT
# ---------------------------------------------------------------------------

def find_pt_detail_url(driver, keyword, nama_pt_target):
    from urllib.parse import quote
    url = f"{BASE_URL}/search/{quote(keyword, safe='(),.')}"
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
# Identifikasi dropdown
# ---------------------------------------------------------------------------

def _get_dropdowns(driver):
    """
    Kembalikan (tampilkan_select, semester_select) dari semua <select> di halaman.

    Dropdown 'Tampilkan' : salah satu opsinya bernilai 'semua'
    Dropdown 'Semester'  : tidak punya opsi 'semua', teksnya mengandung tahun (4 digit)
    """
    tampilkan_sel = None
    semester_sel  = None

    for sel_el in driver.find_elements(By.TAG_NAME, "select"):
        opts       = sel_el.find_elements(By.TAG_NAME, "option")
        opt_values = [o.get_attribute("value") or "" for o in opts]
        opt_texts  = [o.text.strip() for o in opts]

        has_semua = "semua" in opt_values
        has_year  = any(
            any(t[j:j+4].isdigit() for j in range(len(t) - 3))
            for t in opt_texts
        )

        if has_semua and tampilkan_sel is None:
            tampilkan_sel = sel_el
        elif not has_semua and has_year and semester_sel is None:
            semester_sel = sel_el

    return tampilkan_sel, semester_sel


# ---------------------------------------------------------------------------
# Baca semua baris tabel prodi (tabel pertama, lewati 3 baris header)
# ---------------------------------------------------------------------------

def _read_prodi_table(driver):
    all_tables = driver.find_elements(By.TAG_NAME, "table")
    if not all_tables:
        return []

    rows      = all_tables[0].find_elements(By.TAG_NAME, "tr")
    prodi_list = []
    for row in rows[3:]:   # 3 baris pertama = header
        cells = row.find_elements(By.TAG_NAME, "td")
        if not cells or not any(c.text.strip() for c in cells):
            continue
        values   = [c.text.strip() for c in cells]
        row_dict = {col: (values[j] if j < len(values) else "")
                    for j, col in enumerate(KOLOM_PRODI)}
        if row_dict.get("Kode"):
            prodi_list.append(row_dict)

    return prodi_list


# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------

def scrape_pelaporan(driver, pt_url, n_semester=5):
    """
    Buka halaman detail PT, iterasi N semester terakhir dari dropdown
    'Data Pelaporan Tahunan'.

    Alur per semester:
      1. Pilih 'semua' di dropdown Tampilkan → tunggu reload
      2. Pilih semester di dropdown Semester → tunggu reload
      3. Baca seluruh baris program studi dari tabel
    """
    print(f"\nMembuka detail PT: {pt_url[:70]}...")
    driver.get(pt_url)
    time.sleep(7)
    _wait_no_overlay(driver)

    tampilkan_sel, semester_sel = _get_dropdowns(driver)

    if semester_sel is None:
        print("  [PERINGATAN] Dropdown semester tidak ditemukan.")
        return []

    # Simpan signature opsi untuk re-identify dropdown setelah DOM reload
    semester_opt_values  = [o.get_attribute("value") for o in Select(semester_sel).options]
    tampilkan_opt_values = (
        [o.get_attribute("value") for o in Select(tampilkan_sel).options]
        if tampilkan_sel else []
    )
    tampilkan_target = (
        "semua" if "semua" in tampilkan_opt_values
        else tampilkan_opt_values[-1] if tampilkan_opt_values
        else None
    )

    # Ekstrak semua opsi semester sebelum interaksi apapun (hindari stale element)
    target_opts = [
        (o.get_attribute("value"), o.text.strip())
        for o in Select(semester_sel).options[:n_semester]
    ]
    print(f"  Ditemukan {len(semester_opt_values)} semester, mengambil {len(target_opts)} terakhir.")

    def _refetch_tampilkan():
        for sel_el in driver.find_elements(By.TAG_NAME, "select"):
            vals = [o.get_attribute("value") for o in sel_el.find_elements(By.TAG_NAME, "option")]
            if vals == tampilkan_opt_values:
                return sel_el
        return None

    def _refetch_semester():
        for sel_el in driver.find_elements(By.TAG_NAME, "select"):
            vals = [o.get_attribute("value") for o in sel_el.find_elements(By.TAG_NAME, "option")]
            if vals == semester_opt_values:
                return sel_el
        return None

    def _pilih_semua():
        """Pilih 'semua' di Tampilkan jika belum terpilih. Return True jika ada reload."""
        if not tampilkan_target:
            return False
        _wait_no_overlay(driver)
        tap = _refetch_tampilkan()
        if tap is None:
            return False
        sel_obj = Select(tap)
        if sel_obj.first_selected_option.get_attribute("value") != tampilkan_target:
            try:
                sel_obj.select_by_value(tampilkan_target)
            except Exception:
                _js_select(driver, tap, tampilkan_target)
            print(f"    Tampilkan '{tampilkan_target}' dipilih, menunggu reload...")
            time.sleep(5)
            _wait_no_overlay(driver)
            return True
        return False

    hasil = []
    for i, (sem_val, sem_txt) in enumerate(target_opts, 1):
        print(f"\n  [{i}/{len(target_opts)}] Semester: {sem_txt}")

        # Langkah 1: pastikan Tampilkan = 'semua' sebelum pilih semester
        _pilih_semua()

        # Langkah 2: pilih semester
        _wait_no_overlay(driver)
        sem = _refetch_semester()
        if sem:
            try:
                Select(sem).select_by_value(sem_val)
            except Exception:
                _js_select(driver, sem, sem_val)
            print(f"    Semester '{sem_txt}' dipilih, menunggu reload...")
            time.sleep(4)
            _wait_no_overlay(driver)
        else:
            print("    [PERINGATAN] Dropdown semester tidak ditemukan, lewati.")
            continue

        # Langkah 3: baca tabel (Tampilkan sudah 'semua' sebelum ganti semester)
        prodi_list = _read_prodi_table(driver)
        print(f"    → {len(prodi_list)} program studi terbaca.")

        hasil.append({
            "semester":      sem_txt,
            "program_studi": prodi_list,
        })

    return hasil


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(keyword, nama_pt_target, kode_pt, n_semester):
    os.makedirs(OUT_DIR, exist_ok=True)

    print("=" * 60)
    print(f"PDDikti Scraper (Pelaporan)  Keyword : {keyword}")
    print(f"                             Target  : {nama_pt_target}")
    print(f"                             Kode PT : {kode_pt}")
    print(f"                             Semester: {n_semester} terakhir")
    print("=" * 60)

    driver = init_driver(headless=True)
    try:
        pt_url = find_pt_detail_url(driver, keyword, nama_pt_target)
        if not pt_url:
            return

        pelaporan = scrape_pelaporan(driver, pt_url, n_semester)
        if not pelaporan:
            print("Tidak ada data pelaporan ditemukan.")
            return

        output = {
            "kode_pt":         kode_pt,
            "nama_pt":         nama_pt_target,
            "jumlah_semester": len(pelaporan),
            "pelaporan":       pelaporan,
        }
        pt_dir   = os.path.join(OUT_DIR, kode_pt)
        os.makedirs(pt_dir, exist_ok=True)
        out_path = os.path.join(pt_dir, f"{kode_pt}_listprodi.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        total_prodi = sum(len(s["program_studi"]) for s in pelaporan)
        print(f"\nDisimpan: {out_path}")
        print(f"  → {len(pelaporan)} semester, total {total_prodi} baris prodi")

    finally:
        driver.quit()

    print("\nSelesai.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scraper PDDikti — Data Pelaporan Tahunan per semester"
    )
    parser.add_argument("--keyword",  default="universitas muhammadiyah yogyakarta",
                        help="Kata kunci pencarian")
    parser.add_argument("--nama",     default="UNIVERSITAS MUHAMMADIYAH YOGYAKARTA",
                        help="Nama PT persis (huruf kapital)")
    parser.add_argument("--kode",     default="051007",
                        help="Kode PT (prefix nama file output)")
    parser.add_argument("--semester", default=12, type=int,
                        help="Jumlah semester terakhir (default: 12)")
    args = parser.parse_args()

    main(
        keyword=args.keyword,
        nama_pt_target=args.nama,
        kode_pt=args.kode,
        n_semester=args.semester,
    )
