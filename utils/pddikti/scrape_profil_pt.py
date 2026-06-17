#!/usr/bin/env python3
"""
Scraper profil PT dari PDDikti — simpan ke file JSON + logo.

Alur per PT:
  1. Cari URL /detail-pt/ di PDDikti via Selenium
  2. Scrape profil (alamat, kontak, website, akreditasi, dll.)
  3. Download logo PT
  4. Simpan ke utils/outs/{kode_pt}/{kode_pt}_profile.json
           dan utils/outs/{kode_pt}/{kode_pt}_logo.jpg

Output JSON ({kode_pt}_profile.json):
  {
    "kode_pt"       : "071024",
    "nama"          : "Universitas Muhammadiyah Malang",
    "url_pddikti"   : "https://pddikti.../detail-pt/...",
    "profil_pddikti": { "Status": ..., "Akreditasi": ..., ... },
    "logo_url"      : "https://...",
    "logo_file"     : "071024_logo.jpg",   // kosong jika gagal
    "scraped_at"    : "2026-06-07T14:00:00"
  }

Usage:
    # Scrape semua PT dari DB
    python scrape_profil_pt.py

    # Lanjutkan (skip yang sudah ada _profile.json)
    python scrape_profil_pt.py --resume

    # Hanya satu PT
    python scrape_profil_pt.py --kode_pt 071024

    # Batasi jumlah
    python scrape_profil_pt.py --limit 10

    # Preview tanpa download logo
    python scrape_profil_pt.py --no-logo
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pymysql
import requests
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

UTILS_DIR = Path(__file__).resolve().parent
ENV_PATH  = UTILS_DIR.parent.parent / ".env"
load_dotenv(ENV_PATH)

sys.path.insert(0, str(UTILS_DIR))
from firefox_helper import make_driver
from scrape_pddikti import (
    scrape_search_page,
    extract_profile,
)

OUT_DIR  = str(UTILS_DIR.parent / "outs")
BASE_URL = "https://pddikti.kemdiktisaintek.go.id"

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


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def get_pt_list(kode_pt=None):
    conn = pymysql.connect(**DB_CONFIG)
    with conn.cursor() as cur:
        if kode_pt:
            cur.execute(
                "SELECT kode_pt, nama FROM universities_perguruantinggi "
                "WHERE kode_pt = %s",
                (kode_pt,),
            )
        else:
            cur.execute(
                "SELECT kode_pt, nama FROM universities_perguruantinggi "
                "WHERE kode_pt IS NOT NULL AND kode_pt != '' "
                "ORDER BY nama"
            )
        rows = cur.fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Selenium: cari URL /detail-pt/
# ---------------------------------------------------------------------------

def find_detail_pt_url(driver, kode_pt, nama_pt):
    """
    Cari URL /detail-pt/ untuk PT ini di PDDikti.
    Strategi: cari dengan kode_pt dulu, fallback ke nama.
    Return: (url, nama_di_pddikti) atau (None, None).
    """
    for keyword in [kode_pt, nama_pt]:
        search_url = f"{BASE_URL}/search/{keyword.replace(' ', '%20')}"
        print(f"  Mencari: {search_url[:80]}...")
        try:
            all_data = scrape_search_page(driver, search_url)
        except Exception as e:
            print(f"  [ERROR] scrape_search_page: {e}")
            continue

        for section, tabel in all_data.items():
            for row in tabel.get("rows", []):
                detail_url = row.get("_detail_url", "")
                if not detail_url or "/detail-pt/" not in detail_url:
                    continue
                # Ambil nama dari kolom tabel (berbagai kemungkinan nama kolom)
                nama_di_tabel = (
                    row.get("Nama Perguruan TInggi")
                    or row.get("Nama Perguruan Tinggi")
                    or row.get("Nama", "")
                )
                return detail_url, nama_di_tabel.strip()

    return None, None


# ---------------------------------------------------------------------------
# Selenium: ekstrak logo
# ---------------------------------------------------------------------------

# Selector berurutan dari paling spesifik ke fallback.
# Logo PT di PDDikti disimpan sebagai data:image base64 dengan class max-w-[200px].
LOGO_SELECTORS = [
    "img[class*='max-w-[200px]']",   # logo PT — embedded base64
    "img[class*='object-fit']",       # fallback kelas yang sama
    "img[class*='mx-auto']",          # fallback posisi center
]

def extract_logo_src(driver):
    """
    Cari src logo PT dari halaman detail PDDikti.
    Bisa berupa:
      - data URI  : "data:image/jpeg;base64,/9j/..."
      - URL biasa : "https://..."
    Return src string, atau '' jika tidak ditemukan.
    """
    for selector in LOGO_SELECTORS:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in els:
                src = el.get_attribute("src") or ""
                if not src:
                    continue
                # Abaikan ikon kecil (Sort Icon, dll.) — cek dimensi
                w = el.get_attribute("width") or "0"
                h = el.get_attribute("height") or "0"
                try:
                    if int(w) < 40 or int(h) < 40:
                        continue
                except ValueError:
                    pass
                # Abaikan aset situs (logo PDDikti, navbar, kemendikbud)
                skip_keywords = ["logo-pddikti", "pddikti-navbar", "logo-kemendikbud",
                                  "swiperArrow", "dropdown", "gmaps", "PT-Banner"]
                if any(kw in src for kw in skip_keywords):
                    continue
                if src.startswith("/"):
                    src = BASE_URL + src
                print(f"  Logo ditemukan via [{selector}]: {src[:80]}...")
                return src
        except Exception:
            continue
    return ""


# ---------------------------------------------------------------------------
# Simpan logo (URL atau base64)
# ---------------------------------------------------------------------------

def save_logo(logo_src, out_path):
    """
    Simpan logo ke out_path.
    Mendukung data URI (base64) maupun URL biasa.
    Return True jika berhasil.
    """
    if not logo_src:
        return False

    try:
        # Data URI: "data:image/jpeg;base64,/9j/..."
        if logo_src.startswith("data:image"):
            header, b64data = logo_src.split(",", 1)
            img_bytes = base64.b64decode(b64data)
            with open(out_path, "wb") as f:
                f.write(img_bytes)
            size_kb = len(img_bytes) / 1024
            print(f"  Logo (base64) disimpan: {out_path} ({size_kb:.1f} KB)")
            return True

        # URL biasa
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(logo_src, headers=headers, timeout=15)
        if r.status_code == 200 and r.content:
            with open(out_path, "wb") as f:
                f.write(r.content)
            size_kb = len(r.content) / 1024
            print(f"  Logo (URL) disimpan: {out_path} ({size_kb:.1f} KB)")
            return True
        else:
            print(f"  [GAGAL] Download logo HTTP {r.status_code}")

    except Exception as e:
        print(f"  [GAGAL] Simpan logo: {e}")

    return False


# ---------------------------------------------------------------------------
# Scrape satu PT
# ---------------------------------------------------------------------------

def scrape_pt(driver, kode_pt, nama_pt, fetch_logo=True):
    """
    Scrape profil + logo satu PT.
    Return dict hasil, atau None jika URL tidak ditemukan.
    """
    print(f"\n{'─'*60}")
    print(f"Kode : {kode_pt}")
    print(f"Nama : {nama_pt}")

    # 1. Cari URL detail PT
    detail_url, nama_di_pddikti = find_detail_pt_url(driver, kode_pt, nama_pt)
    if not detail_url:
        print(f"  [SKIP] URL /detail-pt/ tidak ditemukan.")
        return None

    print(f"  URL  : {detail_url}")

    # 2. Buka halaman detail PT
    driver.get(detail_url)
    time.sleep(7)

    # 3. Scrape profil
    print("  Mengekstrak profil...")
    try:
        profil = extract_profile(driver)
    except Exception as e:
        print(f"  [ERROR] extract_profile: {e}")
        profil = {}
    print(f"  Field profil : {list(profil.keys())}")

    # 4. Ambil src logo (base64 atau URL)
    logo_src = ""
    if fetch_logo:
        logo_src = extract_logo_src(driver)

    result = {
        "kode_pt":        kode_pt,
        "nama":           nama_pt,
        "nama_pddikti":   nama_di_pddikti,
        "url_pddikti":    detail_url,
        "profil_pddikti": profil,
        "_logo_src":      logo_src,   # penuh, dipakai save_output, tidak ditulis ke JSON
        "logo_file":      "",
        "scraped_at":     datetime.now().isoformat(timespec="seconds"),
    }

    return result


# ---------------------------------------------------------------------------
# Simpan output
# ---------------------------------------------------------------------------

def save_output(result, fetch_logo=True):
    """
    Simpan JSON profil dan download logo ke utils/outs/{kode_pt}/.
    """
    kode_pt  = result["kode_pt"]
    pt_dir   = os.path.join(OUT_DIR, kode_pt)
    os.makedirs(pt_dir, exist_ok=True)

    # Simpan logo menggunakan _logo_src (field internal, tidak masuk JSON)
    logo_src = result.pop("_logo_src", "")
    if fetch_logo and logo_src:
        ext = "png" if ("image/png" in logo_src or logo_src.endswith(".png")) else "jpg"
        logo_filename = f"{kode_pt}_logo.{ext}"
        logo_path = os.path.join(pt_dir, logo_filename)
        ok = save_logo(logo_src, logo_path)
        if ok:
            result["logo_file"] = logo_filename

    # Simpan JSON
    json_path = os.path.join(pt_dir, f"{kode_pt}_profile.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  JSON disimpan : {json_path}")

    return json_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape profil PT dari PDDikti → simpan JSON + logo"
    )
    parser.add_argument("--kode_pt", default=None,
                        help="Hanya scrape satu PT berdasarkan kode")
    parser.add_argument("--resume",  action="store_true",
                        help="Skip PT yang sudah ada _profile.json")
    parser.add_argument("--limit",   type=int, default=None,
                        help="Batasi jumlah PT yang diproses")
    parser.add_argument("--no-logo", action="store_true",
                        help="Jangan download logo")
    args = parser.parse_args()

    fetch_logo = not args.no_logo

    # Ambil daftar PT
    pt_list = get_pt_list(kode_pt=args.kode_pt)
    total   = len(pt_list)
    print(f"Total PT dari DB : {total}")

    # Filter resume
    if args.resume:
        filtered = []
        for pt in pt_list:
            kode = pt["kode_pt"]
            json_path = os.path.join(OUT_DIR, kode, f"{kode}_profile.json")
            if os.path.exists(json_path):
                print(f"  [SKIP] {kode} sudah ada profile.json")
            else:
                filtered.append(pt)
        pt_list = filtered
        print(f"Setelah filter resume : {len(pt_list)} PT akan diproses")

    # Limit
    if args.limit:
        pt_list = pt_list[:args.limit]
        print(f"Mode limit : hanya {args.limit} PT pertama")

    if not pt_list:
        print("Tidak ada PT yang perlu diproses.")
        return

    print(f"\nMulai scraping {len(pt_list)} PT...\n")

    driver = make_driver(headless=True)
    ok = error = skip = 0

    try:
        for i, pt in enumerate(pt_list, 1):
            kode = pt["kode_pt"]
            nama = pt["nama"]
            print(f"\n[{i}/{len(pt_list)}] {kode} — {nama}")

            try:
                result = scrape_pt(driver, kode, nama, fetch_logo=fetch_logo)
                if result is None:
                    skip += 1
                    continue
                save_output(result, fetch_logo=fetch_logo)
                ok += 1
            except Exception as e:
                print(f"  [ERROR] {kode}: {e}")
                error += 1
                # Restart driver jika crash
                try:
                    driver.quit()
                except Exception:
                    pass
                time.sleep(3)
                driver = make_driver(headless=True)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    print(f"\n{'='*60}")
    print(f"SELESAI — Berhasil: {ok} | Skip: {skip} | Error: {error}")
    print(f"Output  : {OUT_DIR}/[kode_pt]/[kode_pt]_profile.json")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
