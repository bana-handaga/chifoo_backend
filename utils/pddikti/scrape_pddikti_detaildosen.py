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
    # Default: profil + riwayat pendidikan
    python utils/scrape_pddikti_detaildosen.py --nama "YULIA FITRI" --pt "UNIVERSITAS MUHAMMADIYAH RIAU"
    python utils/scrape_pddikti_detaildosen.py --nama "YULIA FITRI" --pt "UNIVERSITAS MUHAMMADIYAH RIAU" --nidn "1007078501"

    # --full: semua data (mengajar, penelitian, pengabdian, publikasi, HKI)
    python utils/scrape_pddikti_detaildosen.py --nama "YULIA FITRI" --pt "UNIVERSITAS MUHAMMADIYAH RIAU" --nidn "1007078501" --full
    python utils/scrape_pddikti_detaildosen.py --nama "YULIA FITRI" --pt "UNIVERSITAS MUHAMMADIYAH RIAU" --nidn "1007078501" --nuptk "2039763664230363" --pendidikan "S2" --status "Aktif" --full

    # --debug: tampilkan browser (tidak headless)
    python utils/scrape_pddikti_detaildosen.py --nama "YULIA FITRI" --pt "UNIVERSITAS MUHAMMADIYAH RIAU" --debug
"""

import os
import re
import time
import json
import argparse
from pathlib import Path

from selenium import webdriver
from firefox_helper import make_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

OUT_DIR  = Path("/home/ubuntu/_chifoo/chifoo_backend/utils/outs/dosen")
BASE_URL = "https://pddikti.kemdiktisaintek.go.id"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def init_driver(headless=True):
    return make_driver(headless=headless)


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


def _el_text(el):
    """Ambil teks elemen — gunakan textContent agar bekerja untuk elemen non-visible."""
    txt = el.text.strip()
    if not txt:
        try:
            txt = (el.get_attribute("textContent") or "").strip()
        except Exception:
            pass
    return txt


def get_table_as_list(table_el):
    """Konversi elemen tabel ke list of dict."""
    rows = table_el.find_elements(By.TAG_NAME, "tr")
    if not rows:
        return []
    headers = [_el_text(th) for th in rows[0].find_elements(By.TAG_NAME, "th")]
    if not headers or all(h == "" for h in headers):
        headers = [_el_text(td) for td in rows[0].find_elements(By.TAG_NAME, "td")]
    result = []
    for row in rows[1:]:
        cells = row.find_elements(By.TAG_NAME, "td")
        if not cells:
            continue
        row_dict = {}
        for i, cell in enumerate(cells):
            key = headers[i] if i < len(headers) else f"col_{i}"
            row_dict[key] = _el_text(cell)
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

        headers = [_el_text(th) for th in rows[0].find_elements(By.TAG_NAME, "th")]
        if not headers or all(h == "" for h in headers):
            # Coba ambil header dari td baris pertama (beberapa tabel pakai td di thead)
            headers = [_el_text(td) for td in rows[0].find_elements(By.TAG_NAME, "td")]
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
                        full=False):
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
    # Mapping label di website → key canonical yang disimpan di JSON
    # Website saat ini: "Pendidikan Terakhir", "Status Ikatan Kerja", "Status Aktivitas"
    profil_keys_map = {
        "Nama":                  "Nama",
        "Jenis Kelamin":         "Jenis Kelamin",
        "Perguruan Tinggi":      "Perguruan Tinggi",
        "Program Studi":         "Program Studi",
        "Jabatan Fungsional":    "Jabatan Fungsional",
        "Pendidikan Terakhir":   "Pendidikan Tertinggi",   # label baru → key lama
        "Pendidikan Tertinggi":  "Pendidikan Tertinggi",
        "Status Ikatan Kerja":   "Ikatan Kerja",           # label baru → key lama
        "Ikatan Kerja":          "Ikatan Kerja",
        "Status Aktivitas":      "Status Aktif",           # label baru → key lama
        "Status Aktif":          "Status Aktif",
        "Status":                "Status Aktif",
        "NIDN":                  "NIDN",
        "NUPTK":                 "NUPTK",
        "NIP":                   "NIP",
        "Tanggal Lahir":         "Tanggal Lahir",
    }
    page_text = driver.find_element(By.TAG_NAME, "body").text
    for label, canonical_key in profil_keys_map.items():
        if canonical_key in data["profil"]:
            continue  # sudah diisi oleh label lain
        pattern = rf"(?:^|\n){re.escape(label)}\s*[:\n]\s*([^\n]+)"
        m = re.search(pattern, page_text, re.IGNORECASE | re.MULTILINE)
        if m:
            data["profil"][canonical_key] = m.group(1).strip()

    # Isi dari input argumen jika tidak ditemukan di halaman
    if nuptk_input and "NUPTK" not in data["profil"]:
        data["profil"]["NUPTK"] = nuptk_input
    if pendidikan_input and "Pendidikan Tertinggi" not in data["profil"]:
        data["profil"]["Pendidikan Tertinggi"] = pendidikan_input
    if status_input and "Status Aktif" not in data["profil"]:
        data["profil"]["Status Aktif"] = status_input

    print(f"[2a] Profil: {data['profil']}")

    # ------------------------------------------------------------------
    # 2b. Riwayat Pendidikan — halaman awal (selalu discrape)
    # Hanya ambil tabel yang punya kolom "Gelar" atau "Jenjang" (bukan tabel mengajar)
    # ------------------------------------------------------------------
    print("[2b] Scrape riwayat pendidikan...")
    for item in scrape_tables_on_page(driver, "pendidikan"):
        h_lower = " ".join(item["headers"]).lower()
        # Tabel pendidikan: harus punya "gelar" atau "jenjang"
        # Tabel mengajar: punya "nama mata kuliah"/"kode kelas" → di-skip
        if any(k in h_lower for k in ["gelar", "jenjang"]) and \
           not any(k in h_lower for k in ["mata kuliah", "kode kelas", "nama kelas"]):
            data["riwayat_pendidikan"].extend(item["rows"])

    if not full:
        print("[2c-2g] Mode default — hanya profil + riwayat pendidikan")
        return data

    # ------------------------------------------------------------------
    # 2c. Penelitian — tab Penelitian
    # ------------------------------------------------------------------
    print("[2c] Mencari tab Penelitian...")
    clicked = find_and_click_tab(driver, ["penelitian"])
    if clicked:
        for item in scrape_tables_on_page(driver, "penelitian"):
            h_lower = " ".join(item["headers"]).lower()
            if any(k in h_lower for k in ["judul penelitian", "penelitian"]) and \
               not any(k in h_lower for k in ["mata kuliah", "kode kelas", "pengabdian", "karya"]):
                data["penelitian"].extend(item["rows"])
    else:
        print("  Tab Penelitian tidak ditemukan.")

    # ------------------------------------------------------------------
    # 2d. Tab Riwayat Mengajar — semester dirender sekaligus di DOM
    # ------------------------------------------------------------------
    print("[2d] Mencari tab Riwayat Mengajar...")
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

        # Header kolom tabel mengajar
        MENGAJAR_HEADERS = ["mata kuliah", "sks", "kelas", "matkul",
                            "nama mata kuliah", "kode mata kuliah", "nama matakuliah",
                            "kode kelas", "nama kelas"]

        def _tbl_headers_lower(tbl):
            """Baca header tabel (textContent) sebagai lowercase list."""
            rows = tbl.find_elements(By.TAG_NAME, "tr")
            if not rows:
                return []
            ths = [_el_text(th) for th in rows[0].find_elements(By.TAG_NAME, "th")]
            if not ths or all(h == "" for h in ths):
                ths = [_el_text(td) for td in rows[0].find_elements(By.TAG_NAME, "td")]
            return [h.lower() for h in ths if h]

        def _is_mengajar_tbl(tbl):
            ths = _tbl_headers_lower(tbl)
            return any(k in " ".join(ths) for k in MENGAJAR_HEADERS)

        # Strategi: website merender SEMUA semester sekaligus di DOM.
        # Kumpulkan label semester (single-line) dan tabel mengajar secara paralel,
        # lalu pasangkan berdasarkan urutan.
        sem_labels = []
        seen_sem = set()
        for tag in ["li", "button", "div", "span", "a"]:
            for el in driver.find_elements(By.TAG_NAME, tag):
                try:
                    txt = el.text.strip()
                    if "\n" not in txt and SEM_PATTERN.match(txt) and txt not in seen_sem and el.is_displayed():
                        sem_labels.append(txt)
                        seen_sem.add(txt)
                except Exception:
                    continue
            if sem_labels:
                break  # ambil dari tag pertama yang berhasil

        mengajar_tbls = [tbl for tbl in driver.find_elements(By.TAG_NAME, "table")
                         if _is_mengajar_tbl(tbl)]

        print(f"  Semester labels: {sem_labels}")
        print(f"  Tabel mengajar ditemukan: {len(mengajar_tbls)}")

        if sem_labels and mengajar_tbls:
            # Pasangkan berdasarkan urutan (jumlah boleh beda — ambil min)
            for idx, sem_label in enumerate(sem_labels):
                if idx >= len(mengajar_tbls):
                    break
                rows = get_table_as_list(mengajar_tbls[idx])
                if rows:
                    data["riwayat_mengajar"][sem_label] = rows
                    print(f"    {sem_label}: {len(rows)} matkul")
                else:
                    print(f"    {sem_label}: kosong")
        elif mengajar_tbls:
            # Tabel ada tapi tidak ada label semester → simpan sebagai "default"
            all_rows = []
            for tbl in mengajar_tbls:
                all_rows.extend(get_table_as_list(tbl))
            if all_rows:
                data["riwayat_mengajar"]["default"] = all_rows
                print(f"  Mengajar (tanpa label): {len(all_rows)} matkul")

        if not data["riwayat_mengajar"]:
            print("  Tidak ada data mengajar.")
    else:
        print("  Tab Riwayat Mengajar tidak ditemukan.")

    # ------------------------------------------------------------------
    # 2e. Tab Pengabdian Masyarakat
    # ------------------------------------------------------------------
    print("[2e] Mencari tab Pengabdian Masyarakat...")
    clicked = find_and_click_tab(driver, ["pengabdian"])
    if clicked:
        for item in scrape_tables_on_page(driver, "pengabdian"):
            h_lower = " ".join(item["headers"]).lower()
            if "judul pengabdian" in h_lower or "pengabdian masyarakat" in h_lower:
                data["pengabdian"].extend(item["rows"])
    else:
        print("  Tab Pengabdian tidak ditemukan.")

    # ------------------------------------------------------------------
    # 2f. Tab Publikasi Karya
    # ------------------------------------------------------------------
    print("[2f] Mencari tab Publikasi Karya...")
    clicked = find_and_click_tab(driver, ["publikasi"])
    if clicked:
        for item in scrape_tables_on_page(driver, "publikasi"):
            h_lower = " ".join(item["headers"]).lower()
            if "judul karya" in h_lower or "jenis karya" in h_lower:
                data["publikasi"].extend(item["rows"])
    else:
        print("  Tab Publikasi tidak ditemukan.")

    # ------------------------------------------------------------------
    # 2g. Tab HKI / Paten
    # ------------------------------------------------------------------
    print("[2g] Mencari tab HKI/Paten...")
    clicked = find_and_click_tab(driver, ["hki", "paten", "hak kekayaan"])
    if clicked:
        for item in scrape_tables_on_page(driver, "hki"):
            h_lower = " ".join(item["headers"]).lower()
            if any(k in h_lower for k in ["hki", "paten", "hak kekayaan", "judul hki"]):
                data["hki_paten"].extend(item["rows"])
    else:
        print("  Tab HKI/Paten tidak ditemukan.")

    # ------------------------------------------------------------------
    # 2h. Ambil daftar semua tab yang ada (untuk analisis)
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
    parser.add_argument("--full",  action="store_true", help="Scrape semua data (mengajar, penelitian, pengabdian, publikasi, HKI)")
    parser.add_argument("--debug", action="store_true", help="Tampilkan browser (tidak headless)")
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
            full             = args.full,
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
