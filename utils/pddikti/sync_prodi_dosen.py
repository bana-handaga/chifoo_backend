#!/usr/bin/env python3
"""
Sinkronisasi PDDikti — Prodi + DataDosen + ProfilDosen + DataMahasiswa

Langkah per PT:
  1. Cari & buka halaman profil PT
  2. Baca semester aktif dari dropdown
  3. Baca tabel prodi (kode, nama, status, jenjang, akreditasi, dosen, mahasiswa, rasio)
  4. Update universities_programstudi + universities_datadosen
  5. Buka halaman detail tiap prodi aktif:
       → Update detail profil prodi (kontak, tanggal berdiri, informasi umum, dll.)
  6. Tab 'Tenaga Pendidik': upsert universities_profildosen (NIDN/NUPTK)
  7. Tab 'Mahasiswa': upsert universities_datamahasiswa (3 semester terakhir)
  8. Setelah semua prodi: tandai Non-Aktif dosen PT yang tidak ditemukan di PDDikti run ini

Usage:
    python sync_prodi_dosen.py --kode 064167 --nama "AKADEMI KESEHATAN MUHAMMADIYAH TEMANGGUNG"
    python sync_prodi_dosen.py --kode 061008 --nama "UNIVERSITAS MUHAMMADIYAH SURAKARTA" --dry-run
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from selenium import webdriver
from firefox_helper import make_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException

# ── Config ────────────────────────────────────────────────────
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(ENV_PATH)

DB_CONFIG = {
    "host":        os.environ.get("DB_HOST", "localhost"),
    "port":        int(os.environ.get("DB_PORT", 3306)),
    "user":        os.environ.get("DB_USER", "root"),
    "password":    os.environ.get("DB_PASSWORD", ""),
    "db":          os.environ.get("DB_NAME", "ptma_db"),
    "charset":     "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "connect_timeout": 30,
}

BASE_URL = "https://pddikti.kemdiktisaintek.go.id"

KOLOM_PRODI = [
    "Kode", "Nama Program Studi", "Status", "Jenjang", "Akreditasi",
    "Jumlah Dosen Penghitung Rasio", "Dosen Tetap", "Dosen Tidak Tetap",
    "Total Dosen", "Jumlah Mahasiswa", "Rasio Dosen/Mahasiswa",
]
JENJANG_MAP = {
    "D1": "d1", "D2": "d2", "D3": "d3", "D4": "d4",
    "S1": "s1", "S2": "s2", "S3": "s3",
    "PROFESI": "profesi", "SPESIALIS": "profesi",
    "SP-1": "profesi", "SP-2": "profesi",
}
AKREDITASI_MAP = {
    "UNGGUL": "unggul", "BAIK SEKALI": "baik_sekali",
    "BAIK": "baik", "C": "c",
}
PENDIDIKAN_MAP = {
    "S3": "s3", "S2": "s2", "S1": "s1",
    "PROFESI": "profesi", "D4": "s1",
}
IKATAN_MAP = {
    "TETAP": "tetap", "TIDAK TETAP": "tidak_tetap",
    "DOSEN TETAP": "tetap", "DOSEN TIDAK TETAP": "tidak_tetap",
}


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── Selenium ─────────────────────────────────────────────────

def init_driver():
    return make_driver(headless=True)


def wait(sec, reason=""):
    if reason:
        log(f"  Menunggu {sec}s — {reason}...")
    time.sleep(sec)


# ── Cari halaman profil PT ───────────────────────────────────

def find_pt_detail_url(driver, nama_pt_target):
    keyword = nama_pt_target.lower()
    url = f"{BASE_URL}/search/{keyword.replace(' ', '%20')}"
    log(f"Pencarian PT: {url}")
    driver.get(url)
    wait(8, "halaman pencarian")

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
            for cell in cells:
                for a in cell.find_elements(By.TAG_NAME, "a"):
                    href = a.get_attribute("href") or ""
                    if "/detail-pt/" in href:
                        log(f"  [COCOK] '{nama}' → {href[:80]}")
                        return href

    log(f"  [TIDAK DITEMUKAN] '{nama_pt_target}'")
    return None


# ── Dropdown helpers ─────────────────────────────────────────

def _get_dropdowns(driver):
    tampilkan_sel = None
    semester_sel  = None
    for sel_el in driver.find_elements(By.TAG_NAME, "select"):
        opts       = sel_el.find_elements(By.TAG_NAME, "option")
        opt_values = [o.get_attribute("value") or "" for o in opts]
        opt_texts  = [o.text.strip() for o in opts]
        has_semua  = "semua" in opt_values
        has_year   = any(
            any(t[j:j+4].isdigit() for j in range(len(t) - 3))
            for t in opt_texts
        )
        if has_semua and tampilkan_sel is None:
            tampilkan_sel = sel_el
        elif not has_semua and has_year and semester_sel is None:
            semester_sel = sel_el
    return tampilkan_sel, semester_sel


# ── Baca tabel prodi (teks + link detail) ───────────────────

def read_prodi_table(driver):
    all_tables = driver.find_elements(By.TAG_NAME, "table")
    if not all_tables:
        return []
    rows = all_tables[0].find_elements(By.TAG_NAME, "tr")
    prodi_list = []
    for row in rows[3:]:
        cells = row.find_elements(By.TAG_NAME, "td")
        if not cells or not any(c.text.strip() for c in cells):
            continue
        values   = [c.text.strip() for c in cells]
        row_dict = {col: (values[j] if j < len(values) else "")
                    for j, col in enumerate(KOLOM_PRODI)}
        if not row_dict.get("Kode"):
            continue

        # Ambil link detail prodi dari kolom 'Nama Program Studi'
        detail_url = None
        if len(cells) > 1:
            for a in cells[1].find_elements(By.TAG_NAME, "a"):
                href = a.get_attribute("href") or ""
                if "/detail-pt/" in href or "/detail-prodi/" in href or href.startswith(BASE_URL):
                    detail_url = href
                    break
        row_dict["_detail_url"] = detail_url
        prodi_list.append(row_dict)
    return prodi_list


def _load_pt_page_with_semua(driver, pt_url):
    """Buka PT page, pilih semua+semester aktif, return (sem_val, sem_txt)."""
    driver.get(pt_url)
    wait(8, "halaman profil PT")
    tampilkan_sel, semester_sel = _get_dropdowns(driver)
    if semester_sel is None:
        return None, None
    all_opts = [(o.get_attribute("value"), o.text.strip())
                for o in Select(semester_sel).options]
    sem_val, sem_txt = all_opts[0]
    if tampilkan_sel:
        tv = [o.get_attribute("value") for o in tampilkan_sel.find_elements(By.TAG_NAME, "option")]
        if "semua" in tv:
            Select(tampilkan_sel).select_by_value("semua")
            wait(5, "tampilkan=semua")
    _, semester_sel2 = _get_dropdowns(driver)
    if semester_sel2:
        Select(semester_sel2).select_by_value(sem_val)
        wait(5, f"semester={sem_txt}")
    return sem_val, sem_txt


def scrape_pt_page(driver, pt_url):
    """Buka halaman PT, baca tabel prodi, dan capture URL detail tiap prodi dengan klik."""
    log(f"Membuka halaman profil PT...")
    sem_val, sem_txt = _load_pt_page_with_semua(driver, pt_url)
    if not sem_txt:
        log("  [PERINGATAN] Dropdown semester tidak ditemukan.")
        return None, []

    all_opts_log = []
    _, semester_sel = _get_dropdowns(driver)
    if semester_sel:
        all_opts_log = [o.text.strip() for o in Select(semester_sel).options]
    log(f"  Opsi semester: {all_opts_log}")
    log(f"  Semester aktif: {sem_txt}")

    prodi_list = read_prodi_table(driver)
    log(f"  {len(prodi_list)} baris prodi terbaca.")

    # Capture URL detail tiap prodi dengan klik nama prodi lalu kembali
    aktif_rows = [r for r in prodi_list if r.get("Status", "").strip().upper() == "AKTIF"]
    log(f"  Mengambil URL detail untuk {len(aktif_rows)} prodi aktif (klik tiap nama)...")

    kode_to_detail = {}
    for i, item in enumerate(aktif_rows):
        kode = item.get("Kode", "").strip()
        nama = item.get("Nama Program Studi", "").strip()
        log(f"    [{i+1}/{len(aktif_rows)}] Klik nama prodi: {nama}")
        try:
            tables = driver.find_elements(By.TAG_NAME, "table")
            if not tables:
                log(f"      Tabel hilang, reload halaman PT...")
                _load_pt_page_with_semua(driver, pt_url)
                tables = driver.find_elements(By.TAG_NAME, "table")

            found = False
            for row in tables[0].find_elements(By.TAG_NAME, "tr")[3:]:
                cells = row.find_elements(By.TAG_NAME, "td")
                if not cells:
                    continue
                if cells[0].text.strip() == kode and len(cells) > 1:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cells[1])
                    time.sleep(0.5)
                    cells[1].click()
                    wait(6, f"navigasi detail {kode}")
                    detail_url = driver.current_url
                    log(f"      → {detail_url[:80]}")
                    kode_to_detail[kode] = detail_url
                    found = True
                    break

            if not found:
                log(f"      [SKIP] Baris prodi {kode} tidak ditemukan di tabel.")

            # Kembali ke halaman PT
            driver.get(pt_url)
            wait(6, "kembali ke PT")
            # Re-select semua + semester
            tampilkan_sel, semester_sel = _get_dropdowns(driver)
            if tampilkan_sel:
                tv = [o.get_attribute("value") for o in tampilkan_sel.find_elements(By.TAG_NAME, "option")]
                if "semua" in tv:
                    Select(tampilkan_sel).select_by_value("semua")
                    wait(4, "tampilkan=semua")
            _, semester_sel2 = _get_dropdowns(driver)
            if semester_sel2:
                Select(semester_sel2).select_by_value(sem_val)
                wait(4, f"semester={sem_txt}")

        except Exception as e:
            log(f"      [ERROR klik prodi {kode}] {e}")
            try:
                driver.get(pt_url)
                wait(6, "recovery ke PT")
            except Exception:
                pass

    # Masukkan detail URL ke prodi_list
    for item in prodi_list:
        kode = item.get("Kode", "").strip()
        item["_detail_url"] = kode_to_detail.get(kode)

    return sem_txt, prodi_list


# ── Parse label semester ─────────────────────────────────────

def parse_semester_label(label):
    """'Ganjil 2025' → ('ganjil', '2025/2026') | 'Genap 2025' → ('genap', '2025/2026')"""
    parts = label.strip().split()
    if len(parts) < 2:
        return None, None
    jenis = parts[0].lower()
    try:
        y = int(parts[1])
    except ValueError:
        return None, None
    return jenis, f"{y}/{y+1}"


def parse_mahasiswa_semester(label):
    """'2025/2026 Genap' → ('genap', '2025/2026') | '2025/2026 Ganjil' → ('ganjil', '2025/2026')"""
    label = label.strip()
    m = re.match(r'(\d{4}/\d{4})\s+(Ganjil|Genap)', label, re.IGNORECASE)
    if m:
        tahun = m.group(1)
        jenis = m.group(2).lower()
        return jenis, tahun
    return None, None


# ── Scrape halaman detail prodi ───────────────────────────────

def _get_text_near_label(driver, label_text):
    """Cari teks di elemen yang berdekatan dengan label tertentu."""
    try:
        els = driver.find_elements(By.XPATH,
            f"//*[contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'), "
            f"'{label_text.upper()}')]")
        for el in els:
            parent = el.find_element(By.XPATH, "..")
            sibling_text = parent.text.strip()
            # Ambil teks setelah label
            if label_text.upper() in sibling_text.upper():
                lines = [l.strip() for l in sibling_text.splitlines() if l.strip()]
                for i, line in enumerate(lines):
                    if label_text.upper() in line.upper() and i + 1 < len(lines):
                        return lines[i + 1]
    except Exception:
        pass
    return ""


def _get_heading_block(driver, heading_text):
    """Ambil konten teks di bawah heading tertentu."""
    try:
        for tag in ["h2", "h3", "h4", "h5", "b", "strong", "p"]:
            els = driver.find_elements(By.TAG_NAME, tag)
            for el in els:
                if heading_text.upper() in el.text.upper():
                    # Ambil teks dari sibling/parent berikutnya
                    try:
                        parent = el.find_element(By.XPATH, "..")
                        full_text = parent.text.strip()
                        # Hapus heading dari teks
                        idx = full_text.upper().find(heading_text.upper())
                        if idx >= 0:
                            result = full_text[idx + len(heading_text):].strip().lstrip(":").strip()
                            if result:
                                return result[:2000]
                    except Exception:
                        pass
    except Exception:
        pass
    return ""


def scrape_detail_prodi(driver, detail_url, nama_prodi):
    """
    Buka halaman detail prodi, ekstrak:
    - profil: telepon, email, website, tanggal_berdiri, no_sk_akreditasi,
              tanggal_kedaluarsa_akreditasi, informasi_umum, ilmu_dipelajari, kompetensi
    - daftar dosen dari tab Tenaga Pendidik
    - data mahasiswa dari tab Mahasiswa (3 semester)

    Return dict: {profil: {...}, dosen: [...], mahasiswa: [...]}
    """
    log(f"    Membuka detail prodi: {detail_url[:80]}")
    driver.get(detail_url)
    wait(8, "halaman detail prodi")

    result = {"profil": {}, "dosen": [], "mahasiswa": []}

    # ── Profil prodi ─────────────────────────────────────────
    page_text = driver.find_element(By.TAG_NAME, "body").text

    def extract_after(label, text):
        """Cari baris setelah 'label' di teks halaman."""
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if label.lower() in line.lower():
                # Cari nilai di baris yang sama (setelah ':') atau baris berikutnya
                if ':' in line:
                    val = line.split(':', 1)[1].strip()
                    if val:
                        return val
                if i + 1 < len(lines) and lines[i+1].strip():
                    return lines[i+1].strip()
        return ""

    profil = {}
    profil["tanggal_berdiri"]   = extract_after("Tanggal Berdiri", page_text)[:40] if extract_after("Tanggal Berdiri", page_text) else ""
    profil["no_sk_akreditasi"]  = (extract_after("SK Selenggara", page_text)
                                   or extract_after("SK Selengara", page_text)
                                   or extract_after("SK Penyelenggara", page_text)
                                   or "")[:100]
    # Tanggal SK: baris setelah "Tanggal SK Selenggara"
    profil["tanggal_kedaluarsa_akreditasi"] = (extract_after("Tanggal SK Selenggara", page_text)
                                               or extract_after("Tanggal SK Selengara", page_text)
                                               or "")

    # Ekstrak telepon, email, website dengan pattern matching dari body text
    lines = page_text.splitlines()
    telepon = ""
    email   = ""
    website = ""
    for line in lines:
        line = line.strip()
        if not telepon and re.match(r'^[\+\(]?[\d\s\(\)\-]{7,20}$', line):
            telepon = line[:20]
        if not email and "@" in line and re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', line):
            email = line[:100]
        if not website and "." in line and "@" not in line and re.match(
                r'^[a-zA-Z0-9][\w\-\.]+\.[a-zA-Z]{2,}(/.*)?$', line):
            # Hindari false positive
            if not re.search(r'(Jalan|jendral|Senayan|Jakarta|Kab\.|Prov\.|Indonesia)', line, re.I):
                website = line[:200]

    profil["telepon"] = telepon
    profil["email"]   = email
    profil["website"] = website

    # Blok teks panjang — hindari extract "-" saja
    def clean_block(text):
        t = text.strip().lstrip(":").strip()
        return "" if t in ["-", "–", ""] else t[:2000]

    profil["informasi_umum"]  = clean_block(extract_after("Informasi Umum", page_text))
    profil["ilmu_dipelajari"] = clean_block(extract_after("Ilmu yang Dipelajari", page_text)
                                            or extract_after("Ilmu Dipelajari", page_text))
    profil["kompetensi"]      = clean_block(extract_after("Kompetensi", page_text))

    # Konversi tanggal_kedaluarsa_akreditasi ke format date (cari pola dd-mm-yyyy atau yyyy-mm-dd)
    tgl_raw = profil.get("tanggal_kedaluarsa_akreditasi", "")
    profil["tanggal_kedaluarsa_date"] = None
    if tgl_raw:
        m = re.search(r'(\d{2})[/-](\d{2})[/-](\d{4})', tgl_raw)
        if m:
            try:
                profil["tanggal_kedaluarsa_date"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
            except Exception:
                pass
        else:
            m2 = re.search(r'(\d{4})[/-](\d{2})[/-](\d{2})', tgl_raw)
            if m2:
                profil["tanggal_kedaluarsa_date"] = f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"

    result["profil"] = profil
    log(f"    Profil: telepon={profil['telepon']!r} email={profil['email']!r} "
        f"website={profil['website']!r} berdiri={profil['tanggal_berdiri']!r}")
    log(f"    SK={profil['no_sk_akreditasi']!r} "
        f"info_umum={len(profil['informasi_umum'])}c "
        f"ilmu={len(profil['ilmu_dipelajari'])}c "
        f"kompetensi={len(profil['kompetensi'])}c")

    # ── Tab Tenaga Pendidik → sub-tab Dosen Home Base ────────
    log(f"    Mencari tab Tenaga Pendidik...")
    tab_found = _click_tab(driver, ["Tenaga Pendidik", "Dosen"])
    if tab_found:
        wait(4, "tab Tenaga Pendidik")
        # Klik sub-tab "Dosen Home Base" jika ada (beberapa PT punya sub-tab)
        _click_tab(driver, ["Dosen Home Base", "Home Base"])
        wait(2, "sub-tab Dosen Home Base")
        dosen_list = _read_dosen_paginated(driver)
        log(f"    → {len(dosen_list)} dosen terbaca")
        result["dosen"] = dosen_list
    else:
        log(f"    [PERINGATAN] Tab Tenaga Pendidik tidak ditemukan.")

    # ── Tab Mahasiswa ─────────────────────────────────────────
    log(f"    Mencari tab Mahasiswa...")
    tab_found = _click_tab(driver, ["Mahasiswa"])
    if tab_found:
        wait(4, "tab Mahasiswa")
        mhs_list = _read_mahasiswa_table(driver, max_rows=3)
        log(f"    → {len(mhs_list)} baris mahasiswa terbaca")
        result["mahasiswa"] = mhs_list
    else:
        log(f"    [PERINGATAN] Tab Mahasiswa tidak ditemukan.")

    return result


def _click_tab(driver, labels):
    """Klik tab berdasarkan label (coba beberapa variasi)."""
    for label in labels:
        try:
            # Coba button, li, a, div dengan teks
            for tag in ["button", "a", "li", "div", "span"]:
                els = driver.find_elements(By.TAG_NAME, tag)
                for el in els:
                    try:
                        if label.lower() in el.text.lower():
                            el.click()
                            return True
                    except Exception:
                        continue
        except Exception:
            continue
    return False


def _read_dosen_paginated(driver):
    """Baca tabel dosen, ikuti pagination sampai halaman terakhir."""
    KOLOM_DOSEN = ["No", "Nama", "NIDN", "NUPTK", "Pendidikan", "Status", "Ikatan Kerja"]
    all_dosen = []
    page = 1

    while True:
        log(f"      Halaman dosen #{page}...")
        rows = _read_table_rows(driver, KOLOM_DOSEN, skip_header=1)
        if not rows:
            break
        all_dosen.extend(rows)

        # Cari tombol next
        if not _click_next_page(driver):
            break
        page += 1
        wait(3, "halaman berikutnya")
        if page > 30:  # safety limit
            break

    return all_dosen


def _read_mahasiswa_table(driver, max_rows=3):
    """Baca tabel mahasiswa — cari tabel dengan header 'Semester', max 3 baris."""
    mhs_list = []
    for table in driver.find_elements(By.TAG_NAME, "table"):
        rows = table.find_elements(By.TAG_NAME, "tr")
        if not rows:
            continue
        # Cek header row
        header_cells = rows[0].find_elements(By.TAG_NAME, "th") or rows[0].find_elements(By.TAG_NAME, "td")
        headers = [c.text.strip().lower() for c in header_cells]
        if "semester" not in headers:
            continue
        for row in rows[1:]:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 2:
                continue
            semester_raw = cells[0].text.strip()
            jumlah_raw   = cells[1].text.strip()
            if not semester_raw or not jumlah_raw:
                continue
            jenis, tahun = parse_mahasiswa_semester(semester_raw)
            if not jenis:
                continue
            try:
                jumlah = int(jumlah_raw.replace(",", "").strip())
            except ValueError:
                jumlah = 0
            mhs_list.append({
                "semester_raw": semester_raw,
                "semester": jenis,
                "tahun_akademik": tahun,
                "jumlah_mahasiswa": jumlah,
            })
            if len(mhs_list) >= max_rows:
                return mhs_list
        if mhs_list:
            return mhs_list
    return mhs_list


def _read_table_rows(driver, kolom, skip_header=1):
    """Baca baris dari tabel yang punya header sesuai kolom[2] (NIDN untuk dosen)."""
    key_col = kolom[2] if len(kolom) > 2 else kolom[0]
    for table in driver.find_elements(By.TAG_NAME, "table"):
        rows = table.find_elements(By.TAG_NAME, "tr")
        if len(rows) <= skip_header:
            continue
        # Cek apakah tabel ini punya header yang sesuai
        header_row = rows[0].find_elements(By.TAG_NAME, "th") or rows[0].find_elements(By.TAG_NAME, "td")
        header_texts = [c.text.strip() for c in header_row]
        if key_col not in header_texts:
            continue
        result = []
        for row in rows[skip_header:]:
            cells = row.find_elements(By.TAG_NAME, "td")
            if not cells or not any(c.text.strip() for c in cells):
                continue
            values   = [c.text.strip() for c in cells]
            row_dict = {col: (values[j] if j < len(values) else "")
                        for j, col in enumerate(kolom)}
            if any(row_dict.values()):
                result.append(row_dict)
        if result:
            return result
    return []


def _click_next_page(driver):
    """Klik tombol next pagination. Return True jika berhasil.

    PDDikti menggunakan icon button tanpa teks dan tanpa aria-label.
    Penanda: aria-disabled="false" (aktif) vs aria-disabled="true" (nonaktif).
    Strategi: ambil tabel dosen, cari button SETELAH tabel dengan aria-disabled="false".
    """
    # Prioritas 1: JavaScript — temukan button setelah tabel dosen dengan aria-disabled="false"
    try:
        btn = driver.execute_script("""
            // Cari tabel dosen (ada header NIDN)
            var dosen_tbl = null;
            for (var tbl of document.querySelectorAll('table')) {
                var hdrs = Array.from(tbl.querySelectorAll('tr:first-child th, tr:first-child td'))
                               .map(function(c) { return c.textContent.trim(); });
                if (hdrs.indexOf('NIDN') >= 0) { dosen_tbl = tbl; break; }
            }
            if (!dosen_tbl) return null;

            // Cari button setelah tabel yang aria-disabled="false"
            for (var btn of document.querySelectorAll('button')) {
                if (!(dosen_tbl.compareDocumentPosition(btn) & 4)) continue; // harus setelah tabel
                if (btn.getAttribute('aria-disabled') === 'false') return btn;
            }
            return null;
        """)
        if btn:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", btn)
            return True
    except Exception:
        pass

    # Fallback: cari button teks '>' atau aria-label "next" (untuk halaman lain yang berbeda)
    for btn in driver.find_elements(By.TAG_NAME, "button"):
        try:
            txt      = btn.text.strip()
            aria     = (btn.get_attribute("aria-label") or "").lower()
            disabled = btn.get_attribute("disabled")
            aria_dis = btn.get_attribute("aria-disabled") or ""
            if (txt == ">" or txt in ("›", "»") or "next" in aria):
                if not disabled and aria_dis != "true":
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", btn)
                    return True
        except StaleElementReferenceException:
            continue
        except Exception:
            continue
    return False


# ── DB helpers ────────────────────────────────────────────────

def safe_int(val, default=0):
    try:
        return int(str(val).replace(",", "").strip()) if val else default
    except (ValueError, TypeError):
        return default


def get_pt_id(cur, kode_pt):
    cur.execute("SELECT id FROM universities_perguruantinggi WHERE kode_pt = %s", (kode_pt,))
    row = cur.fetchone()
    return row["id"] if row else None


def get_prodi_id(cur, pt_id, kode_prodi):
    cur.execute(
        "SELECT id FROM universities_programstudi "
        "WHERE perguruan_tinggi_id = %s AND kode_prodi = %s",
        (pt_id, kode_prodi),
    )
    row = cur.fetchone()
    return row["id"] if row else None


# ── DB writes ─────────────────────────────────────────────────

def db_update_programstudi(cur, now, prodi_id, item, profil, dry_run):
    jenjang    = JENJANG_MAP.get(item.get("Jenjang", "").strip().upper(), "s1")
    akreditasi = AKREDITASI_MAP.get(item.get("Akreditasi", "").strip().upper(), "belum")
    is_active  = item.get("Status", "").strip().upper() == "AKTIF"

    fields = {
        "jenjang": jenjang,
        "akreditasi": akreditasi,
        "is_active": is_active,
        "telepon": (profil.get("telepon") or "")[:20],
        "email": (profil.get("email") or "")[:100],
        "website": (profil.get("website") or "")[:200],
        "tanggal_berdiri": (profil.get("tanggal_berdiri") or "")[:40],
        "no_sk_akreditasi": (profil.get("no_sk_akreditasi") or "")[:100],
        "informasi_umum": profil.get("informasi_umum") or "",
        "ilmu_dipelajari": profil.get("ilmu_dipelajari") or "",
        "kompetensi": profil.get("kompetensi") or "",
        "updated_at": now,
    }

    tgl_kadaluarsa = profil.get("tanggal_kedaluarsa_date")

    if dry_run:
        log(f"    [DRY] UPDATE programstudi id={prodi_id}: {jenjang}/{akreditasi} aktif={is_active}")
        return

    if tgl_kadaluarsa:
        cur.execute(
            "UPDATE universities_programstudi SET "
            "jenjang=%s, akreditasi=%s, is_active=%s, "
            "telepon=%s, email=%s, website=%s, tanggal_berdiri=%s, "
            "no_sk_akreditasi=%s, tanggal_kedaluarsa_akreditasi=%s, "
            "informasi_umum=%s, ilmu_dipelajari=%s, kompetensi=%s, updated_at=%s "
            "WHERE id=%s",
            (fields["jenjang"], fields["akreditasi"], fields["is_active"],
             fields["telepon"], fields["email"], fields["website"], fields["tanggal_berdiri"],
             fields["no_sk_akreditasi"], tgl_kadaluarsa,
             fields["informasi_umum"], fields["ilmu_dipelajari"], fields["kompetensi"],
             now, prodi_id),
        )
    else:
        cur.execute(
            "UPDATE universities_programstudi SET "
            "jenjang=%s, akreditasi=%s, is_active=%s, "
            "telepon=%s, email=%s, website=%s, tanggal_berdiri=%s, "
            "no_sk_akreditasi=%s, "
            "informasi_umum=%s, ilmu_dipelajari=%s, kompetensi=%s, updated_at=%s "
            "WHERE id=%s",
            (fields["jenjang"], fields["akreditasi"], fields["is_active"],
             fields["telepon"], fields["email"], fields["website"], fields["tanggal_berdiri"],
             fields["no_sk_akreditasi"],
             fields["informasi_umum"], fields["ilmu_dipelajari"], fields["kompetensi"],
             now, prodi_id),
        )
    log(f"    [UPD] programstudi id={prodi_id}: {jenjang}/{akreditasi} aktif={is_active}")


def db_upsert_datadosen(cur, now, pt_id, prodi_id, tahun_akademik, semester, item, dry_run):
    dosen_tetap       = safe_int(item.get("Dosen Tetap"))
    dosen_tidak_tetap = safe_int(item.get("Dosen Tidak Tetap"))
    dosen_rasio       = safe_int(item.get("Jumlah Dosen Penghitung Rasio"))
    rasio             = str(item.get("Rasio Dosen/Mahasiswa", "")).strip()[:10]

    cur.execute(
        "SELECT id FROM universities_datadosen "
        "WHERE perguruan_tinggi_id=%s AND program_studi_id=%s "
        "AND tahun_akademik=%s AND semester=%s",
        (pt_id, prodi_id, tahun_akademik, semester),
    )
    existing = cur.fetchone()

    if dry_run:
        action = "UPDATE" if existing else "INSERT"
        log(f"    [DRY] {action} datadosen: tetap={dosen_tetap} tidak_tetap={dosen_tidak_tetap} "
            f"rasio_int={dosen_rasio} rasio={rasio!r}")
        return "updated" if existing else "inserted"

    if existing:
        cur.execute(
            "UPDATE universities_datadosen SET "
            "dosen_tetap=%s, dosen_tidak_tetap=%s, dosen_rasio=%s, rasio=%s "
            "WHERE id=%s",
            (dosen_tetap, dosen_tidak_tetap, dosen_rasio, rasio, existing["id"]),
        )
        log(f"    [UPD] datadosen id={existing['id']}: tetap={dosen_tetap} tidak_tetap={dosen_tidak_tetap} "
            f"rasio_int={dosen_rasio} rasio={rasio!r}")
        return "updated"
    else:
        cur.execute(
            "INSERT INTO universities_datadosen "
            "(perguruan_tinggi_id, program_studi_id, tahun_akademik, semester, "
            " dosen_tetap, dosen_tidak_tetap, dosen_s3, dosen_s2, dosen_s1, "
            " dosen_guru_besar, dosen_lektor_kepala, dosen_lektor, "
            " dosen_asisten_ahli, dosen_bersertifikat, dosen_rasio, rasio) "
            "VALUES (%s,%s,%s,%s,%s,%s,0,0,0,0,0,0,0,0,%s,%s)",
            (pt_id, prodi_id, tahun_akademik, semester,
             dosen_tetap, dosen_tidak_tetap, dosen_rasio, rasio),
        )
        log(f"    [INS] datadosen: {tahun_akademik}/{semester} "
            f"tetap={dosen_tetap} tidak_tetap={dosen_tidak_tetap} "
            f"rasio_int={dosen_rasio} rasio={rasio!r}")
        return "inserted"


def db_upsert_profildosen(cur, now, pt_id, prodi_id, prodi_nama, dosen_list, dry_run):
    n_upd = n_ins = 0
    for d in dosen_list:
        nidn  = d.get("NIDN", "").strip() or None
        nuptk = d.get("NUPTK", "").strip()
        nama  = d.get("Nama", "").strip()
        if not nama:
            continue

        pend_raw = d.get("Pendidikan", "").strip().upper()
        ik_raw   = d.get("Ikatan Kerja", "").strip().upper()
        status   = d.get("Status", "").strip()

        pendidikan  = PENDIDIKAN_MAP.get(pend_raw, "lainnya") if pend_raw else ""
        ikatan_kerja = IKATAN_MAP.get(ik_raw, "") if ik_raw else ""

        # Cari existing record
        existing_id = None
        if nidn:
            cur.execute(
                "SELECT id FROM universities_profildosen "
                "WHERE perguruan_tinggi_id=%s AND nidn=%s",
                (pt_id, nidn),
            )
            row = cur.fetchone()
            if row:
                existing_id = row["id"]
        if existing_id is None and nuptk:
            cur.execute(
                "SELECT id FROM universities_profildosen "
                "WHERE perguruan_tinggi_id=%s AND nuptk=%s",
                (pt_id, nuptk),
            )
            row = cur.fetchone()
            if row:
                existing_id = row["id"]

        if dry_run:
            action = "UPDATE" if existing_id else "INSERT"
            log(f"      [DRY] {action} profildosen: {nama} NIDN={nidn} {pendidikan}/{ikatan_kerja}")
            if existing_id:
                n_upd += 1
            else:
                n_ins += 1
            continue

        if existing_id:
            cur.execute(
                "UPDATE universities_profildosen SET "
                "nama=%s, nuptk=%s, pendidikan_tertinggi=%s, ikatan_kerja=%s, "
                "status=%s, program_studi_id=%s, program_studi_nama=%s, "
                "scraped_at=%s, updated_at=%s "
                "WHERE id=%s",
                (nama, nuptk, pendidikan, ikatan_kerja, status,
                 prodi_id, prodi_nama, now, now, existing_id),
            )
            n_upd += 1
        else:
            cur.execute(
                "INSERT INTO universities_profildosen "
                "(nidn, nuptk, nama, jenis_kelamin, perguruan_tinggi_id, "
                " program_studi_id, program_studi_nama, jabatan_fungsional, "
                " pendidikan_tertinggi, ikatan_kerja, status, "
                " url_pencarian, scraped_at, created_at, updated_at) "
                "VALUES (%s,%s,%s,'', %s,%s,%s,'', %s,%s,%s,'', %s,%s,%s)",
                (nidn, nuptk, nama, pt_id, prodi_id, prodi_nama,
                 pendidikan, ikatan_kerja, status, now, now, now),
            )
            n_ins += 1

    log(f"    profildosen: {n_upd} diupdate, {n_ins} baru")
    return n_upd, n_ins


def db_mark_nonak_dosen(cur, now, pt_id, dry_run):
    """
    Tandai Non-Aktif semua dosen PT yang tidak ter-update pada run ini.
    Kriteria: perguruan_tinggi_id = pt_id AND (scraped_at IS NULL OR scraped_at < now).
    """
    if dry_run:
        cur.execute(
            "SELECT COUNT(*) AS n FROM universities_profildosen "
            "WHERE perguruan_tinggi_id=%s "
            "  AND (scraped_at IS NULL OR scraped_at < %s) "
            "  AND status != 'Non-Aktif'",
            (pt_id, now),
        )
        n = cur.fetchone()["n"]
        log(f"    [DRY] {n} dosen akan ditandai Non-Aktif")
        return n

    cur.execute(
        "UPDATE universities_profildosen "
        "SET status='Non-Aktif', updated_at=%s "
        "WHERE perguruan_tinggi_id=%s "
        "  AND (scraped_at IS NULL OR scraped_at < %s) "
        "  AND status != 'Non-Aktif'",
        (now, pt_id, now),
    )
    n = cur.rowcount
    log(f"    profildosen Non-Aktif: {n} dosen tidak ditemukan di PDDikti")
    return n


def db_upsert_datamahasiswa(cur, now, pt_id, prodi_id, mhs_list, dry_run):
    n_upd = n_ins = 0
    for m in mhs_list:
        semester       = m["semester"]
        tahun_akademik = m["tahun_akademik"]
        jumlah         = m["jumlah_mahasiswa"]

        cur.execute(
            "SELECT id FROM universities_datamahasiswa "
            "WHERE perguruan_tinggi_id=%s AND program_studi_id=%s "
            "AND tahun_akademik=%s AND semester=%s",
            (pt_id, prodi_id, tahun_akademik, semester),
        )
        existing = cur.fetchone()

        if dry_run:
            action = "UPDATE" if existing else "INSERT"
            log(f"      [DRY] {action} datamahasiswa: {tahun_akademik}/{semester} jumlah={jumlah}")
            if existing:
                n_upd += 1
            else:
                n_ins += 1
            continue

        if existing:
            cur.execute(
                "UPDATE universities_datamahasiswa SET mahasiswa_aktif=%s "
                "WHERE id=%s",
                (jumlah, existing["id"]),
            )
            n_upd += 1
        else:
            cur.execute(
                "INSERT INTO universities_datamahasiswa "
                "(perguruan_tinggi_id, program_studi_id, tahun_akademik, semester, "
                " mahasiswa_baru, mahasiswa_aktif, mahasiswa_lulus, mahasiswa_dropout, "
                " mahasiswa_pria, mahasiswa_wanita) "
                "VALUES (%s,%s,%s,%s,0,%s,0,0,0,0)",
                (pt_id, prodi_id, tahun_akademik, semester, jumlah),
            )
            n_ins += 1

    log(f"    datamahasiswa: {n_upd} diupdate, {n_ins} baru")
    return n_upd, n_ins


# ── Main ──────────────────────────────────────────────────────

def sync(kode_pt, nama_pt, dry_run):
    log("=" * 65)
    log(f"Sync PDDikti  PT   : {nama_pt}")
    log(f"              Kode : {kode_pt}")
    log(f"              Mode : {'DRY RUN' if dry_run else 'LIVE'}")
    log("=" * 65)

    driver = init_driver()
    pt_url      = None
    sem_txt     = None
    prodi_rows  = []

    try:
        # Langkah 1 — Cari URL halaman PT
        pt_url = find_pt_detail_url(driver, nama_pt)
        if not pt_url:
            log("Proses dihentikan — PT tidak ditemukan di PDDikti.")
            return

        # Langkah 2 & 3 — Baca semester aktif + tabel prodi
        sem_txt, prodi_rows = scrape_pt_page(driver, pt_url)

    except Exception as e:
        log(f"[ERROR scraping PT page] {e}")
        driver.quit()
        return

    if not sem_txt or not prodi_rows:
        driver.quit()
        log("Tidak ada data prodi. Selesai.")
        return

    semester, tahun_akademik = parse_semester_label(sem_txt)
    if not semester:
        driver.quit()
        log(f"[ERROR] Tidak bisa parse semester: {sem_txt!r}")
        return

    log(f"Semester aktif: {sem_txt} → {semester}/{tahun_akademik}")
    log(f"Total prodi terbaca: {len(prodi_rows)}")

    # Filter prodi aktif saja untuk langkah 5-7
    aktif_rows = [r for r in prodi_rows if r.get("Status", "").strip().upper() == "AKTIF"]
    log(f"Prodi aktif: {len(aktif_rows)}")

    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = pymysql.connect(**DB_CONFIG)
    stats = {
        "prodi_updated": 0, "prodi_skipped": 0,
        "dosen_updated": 0, "dosen_inserted": 0,
        "profil_updated": 0, "profil_inserted": 0,
        "profil_non_aktif": 0,
        "mhs_updated": 0, "mhs_inserted": 0,
        "errors": 0,
    }

    try:
        with conn.cursor() as cur:
            pt_id = get_pt_id(cur, kode_pt)
            if pt_id is None:
                log(f"[ERROR] kode_pt={kode_pt!r} tidak ditemukan di DB.")
                driver.quit()
                return
            log(f"PT id di DB: {pt_id}")

            # Langkah 4 — Update datadosen dari tabel utama (semua prodi)
            log("\n--- Langkah 4: Update prodi + datadosen dari tabel PT ---")
            for item in prodi_rows:
                kode_prodi = item.get("Kode", "").strip()
                nama_prodi = item.get("Nama Program Studi", "").strip()
                prodi_id   = get_prodi_id(cur, pt_id, kode_prodi)
                if prodi_id is None:
                    log(f"  [SKIP] {kode_prodi} tidak ada di DB")
                    stats["prodi_skipped"] += 1
                    continue

                action = db_upsert_datadosen(
                    cur, now, pt_id, prodi_id, tahun_akademik, semester, item, dry_run
                )
                if action == "updated":
                    stats["dosen_updated"] += 1
                else:
                    stats["dosen_inserted"] += 1

            # Langkah 5-7 — Detail tiap prodi aktif
            log(f"\n--- Langkah 5-7: Detail prodi aktif ({len(aktif_rows)} prodi) ---")
            for idx, item in enumerate(aktif_rows, 1):
                kode_prodi = item.get("Kode", "").strip()
                nama_prodi = item.get("Nama Program Studi", "").strip()
                detail_url = item.get("_detail_url")

                log(f"\n  [{idx}/{len(aktif_rows)}] {kode_prodi} — {nama_prodi}")

                prodi_id = get_prodi_id(cur, pt_id, kode_prodi)
                if prodi_id is None:
                    log(f"  [SKIP] tidak ada di DB")
                    stats["prodi_skipped"] += 1
                    continue

                if not detail_url:
                    log(f"  [SKIP] link detail prodi tidak tersedia")
                    # Tetap update dari data tabel utama
                    db_update_programstudi(cur, now, prodi_id, item, {}, dry_run)
                    stats["prodi_updated"] += 1
                    continue

                try:
                    detail = scrape_detail_prodi(driver, detail_url, nama_prodi)
                except Exception as e:
                    log(f"  [ERROR scrape detail] {e}")
                    stats["errors"] += 1
                    # Kembali ke halaman PT untuk prodi berikutnya
                    try:
                        driver.get(pt_url)
                        wait(6, "kembali ke halaman PT")
                    except Exception:
                        pass
                    continue

                # Step 5d — Update programstudi
                db_update_programstudi(cur, now, prodi_id, item, detail["profil"], dry_run)
                stats["prodi_updated"] += 1

                # Step 6 — Upsert profil dosen
                if detail["dosen"]:
                    nu, ni = db_upsert_profildosen(
                        cur, now, pt_id, prodi_id, nama_prodi, detail["dosen"], dry_run
                    )
                    stats["profil_updated"] += nu
                    stats["profil_inserted"] += ni

                # Step 7 — Upsert data mahasiswa
                if detail["mahasiswa"]:
                    nu, ni = db_upsert_datamahasiswa(
                        cur, now, pt_id, prodi_id, detail["mahasiswa"], dry_run
                    )
                    stats["mhs_updated"] += nu
                    stats["mhs_inserted"] += ni

                # Kembali ke halaman PT jika masih ada prodi berikutnya
                if idx < len(aktif_rows):
                    try:
                        driver.get(pt_url)
                        wait(6, "kembali ke halaman PT")
                    except Exception:
                        pass

            # Langkah 8 — Tandai Non-Aktif dosen yang tidak ditemukan di PDDikti
            log("\n--- Langkah 8: Tandai Non-Aktif dosen yang tidak ter-update ---")
            stats["profil_non_aktif"] = db_mark_nonak_dosen(cur, now, pt_id, dry_run)

        if not dry_run:
            conn.ping(reconnect=True)
            conn.commit()
            log("\nKomit ke database berhasil.")

    except Exception as e:
        conn.rollback()
        log(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        stats["errors"] += 1
    finally:
        driver.quit()
        conn.close()

    log("\n" + "=" * 65)
    log("RINGKASAN")
    log(f"  Prodi diupdate      : {stats['prodi_updated']}")
    log(f"  Prodi dilewati      : {stats['prodi_skipped']} (tidak ada di DB)")
    log(f"  DataDosen updated   : {stats['dosen_updated']}")
    log(f"  DataDosen inserted  : {stats['dosen_inserted']}")
    log(f"  ProfilDosen updated : {stats['profil_updated']}")
    log(f"  ProfilDosen inserted: {stats['profil_inserted']}")
    log(f"  ProfilDosen Non-Aktif:{stats['profil_non_aktif']}")
    log(f"  DataMahasiswa upd   : {stats['mhs_updated']}")
    log(f"  DataMahasiswa ins   : {stats['mhs_inserted']}")
    log(f"  Error               : {stats['errors']}")
    log("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="Sync PDDikti → DB (prodi + datadosen + profildosen + datamahasiswa)")
    parser.add_argument("--kode", required=True, help="Kode PT, contoh: 064167")
    parser.add_argument("--nama", required=True, help="Nama PT persis HURUF KAPITAL sesuai PDDikti")
    parser.add_argument("--dry-run", action="store_true", help="Preview tanpa menulis ke DB")
    args = parser.parse_args()
    sync(args.kode, args.nama, args.dry_run)


if __name__ == "__main__":
    main()
