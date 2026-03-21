"""
Scraper SINTA — Tren Pengabdian Masyarakat (Community Services) Afiliasi PT

Sumber data:
  Halaman profil : /affiliations/profile/{sinta_id}/?view=services

Data yang diambil:
  - service_history : jumlah pengabdian per tahun (dari service-chart-articles)

Prasyarat:
  Data profil afiliasi sudah ada di utils/sinta/outs/affprofile/
  (hasil dari scrape_sinta_afiliasi.py)

Input  : utils/sinta/outs/affprofile/*_sinta_afiliasi.json  (untuk sinta_id)
Output : utils/sinta/outs/services/{kode}_service.json

Usage:
  cd chifoo_backend
  python utils/sinta/scrape_sinta_services.py
  python utils/sinta/scrape_sinta_services.py --kode 061008
  python utils/sinta/scrape_sinta_services.py --limit 5
  python utils/sinta/scrape_sinta_services.py --status
"""

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROFILE_DIR  = Path(__file__).parent / "outs" / "affprofile"
SERVICE_DIR  = Path(__file__).parent / "outs" / "services"

SINTA_BASE   = "https://sinta.kemdiktisaintek.go.id"
SERVICE_URL  = SINTA_BASE + "/affiliations/profile/{sinta_id}/?view=services"

DELAY_PT   = 2.0
TIMEOUT    = 30
RETRY      = 4
RETRY_WAIT = 8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id,en-US;q=0.7,en;q=0.3",
    "Referer":         SINTA_BASE,
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch(session, url, retries=RETRY):
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return BeautifulSoup(r.text, "lxml"), r.text
        except Exception as e:
            print(f"  [attempt {attempt}/{retries}] {url}: {e}")
            if attempt < retries:
                time.sleep(RETRY_WAIT)
    return None, None


# ---------------------------------------------------------------------------
# Ekstrak data pengabdian
# ---------------------------------------------------------------------------

def scrape_services(session, kode, sinta_id, nama):
    """
    Ambil data tren pengabdian dari ?view=services.
    Return dict dengan service_history per tahun.
    """
    url = SERVICE_URL.format(sinta_id=sinta_id)
    _, raw = fetch(session, url)
    if raw is None:
        return None

    result = {
        "kode_pt":        kode,
        "sinta_id":       sinta_id,
        "nama":           nama,
        "service_history": {},
        "scraped_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # --- Service History per Tahun: service-chart-articles ---
    # JS: xAxis.data:['2006','2007',...], series[0].data:[2,1,0,...]
    m = re.search(r"getElementById\(['\"]service-chart-articles['\"]", raw)
    if m:
        block = raw[m.start():m.start() + 5000]
        arrays = re.findall(r"data\s*:\s*\[([^\]]+)\]", block, re.DOTALL)
        if len(arrays) >= 2:
            years  = re.findall(r"['\"](\d{4})['\"]", arrays[0])
            counts = re.findall(r"\b(\d+)\b",          arrays[1])
            for yr, cnt in zip(years, counts):
                result["service_history"][yr] = int(cnt)

    return result


# ---------------------------------------------------------------------------
# Load daftar PT dari affprofile dir
# ---------------------------------------------------------------------------

def load_pt_list():
    pt_list = []
    for f in sorted(PROFILE_DIR.glob("*_sinta_afiliasi.json")):
        with open(f, encoding="utf-8") as fp:
            d = json.load(fp)
        kode     = f.stem.replace("_sinta_afiliasi", "")
        sinta_id = d.get("sinta_id")
        nama     = d.get("nama", d.get("nama_input", ""))
        pt_list.append({"kode": kode, "sinta_id": sinta_id, "nama": nama})
    return pt_list


# ---------------------------------------------------------------------------
# Status report
# ---------------------------------------------------------------------------

def print_status(service_dir):
    files = list(service_dir.glob("*_service.json"))
    total = len(files)
    with_history = sum(
        1 for f in files
        if json.load(open(f)).get("service_history")
    )
    print(f"\n{'='*50}")
    print(f"  File tersimpan      : {total}")
    print(f"  Dengan tren tahunan : {with_history}")
    print(f"  Output dir          : {service_dir}")
    print(f"{'='*50}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape tren pengabdian SINTA Afiliasi (?view=services)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--kode",   default="", help="Filter satu PT berdasarkan kode (e.g. 061008)")
    parser.add_argument("--limit",  type=int, default=0, help="Batasi jumlah PT (untuk testing)")
    parser.add_argument("--status", action="store_true", help="Tampilkan ringkasan output lalu keluar")
    args = parser.parse_args()

    SERVICE_DIR.mkdir(parents=True, exist_ok=True)

    if args.status:
        print_status(SERVICE_DIR)
        return

    pt_list = load_pt_list()
    print(f"Total PT dari affprofile: {len(pt_list)}")

    if args.kode:
        pt_list = [p for p in pt_list if p["kode"] == args.kode]
        if not pt_list:
            print(f"Kode '{args.kode}' tidak ditemukan di {PROFILE_DIR}")
            return

    if args.limit:
        pt_list = pt_list[:args.limit]

    session = make_session()
    done = skipped = no_sinta = errors = 0

    for i, pt in enumerate(pt_list, 1):
        kode     = pt["kode"]
        sinta_id = pt["sinta_id"]
        nama     = pt["nama"]

        if not sinta_id:
            print(f"[{i}/{len(pt_list)}] SKIP {kode}: tidak ada sinta_id")
            no_sinta += 1
            continue

        out_file = SERVICE_DIR / f"{kode}_service.json"
        if out_file.exists() and not args.kode:
            print(f"[{i}/{len(pt_list)}] Skip: {kode} {nama}")
            skipped += 1
            continue

        print(f"\n[{i}/{len(pt_list)}] {kode} — {nama}  (sinta_id={sinta_id})")

        try:
            data = scrape_services(session, kode, sinta_id, nama)
            if data is None:
                print(f"  ERROR: fetch gagal")
                errors += 1
                continue

            history = data.get("service_history", {})
            print(f"  Tren  : {len(history)} tahun — "
                  + ", ".join(f"{y}:{v}" for y, v in sorted(history.items())[-5:])
                  + (" ..." if len(history) > 5 else ""))

            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            done += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            errors += 1

        time.sleep(DELAY_PT)

    print(f"\n=== Selesai ===")
    print(f"  Diproses  : {done}")
    print(f"  Di-skip   : {skipped}")
    print(f"  No sinta  : {no_sinta}")
    print(f"  Error     : {errors}")
    print_status(SERVICE_DIR)


if __name__ == "__main__":
    main()
