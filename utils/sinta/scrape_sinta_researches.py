"""
Scraper SINTA — Tren Penelitian (Researches) Afiliasi Perguruan Tinggi

Sumber data:
  Halaman profil : /affiliations/profile/{sinta_id}/?view=researches

Data yang diambil:
  - research_radar   : breakdown Article / Conference / Others (dari radar chart)
  - research_history : jumlah penelitian per tahun (dari research-chart-articles)

Prasyarat:
  Data profil afiliasi sudah ada di utils/sinta/outs/affprofile/
  (hasil dari scrape_sinta_afiliasi.py)

Input  : utils/sinta/outs/affprofile/*_sinta_afiliasi.json  (untuk sinta_id)
Output : utils/sinta/outs/researches/{kode}_research.json

Usage:
  cd chifoo_backend
  python utils/sinta/scrape_sinta_researches.py
  python utils/sinta/scrape_sinta_researches.py --kode 061008
  python utils/sinta/scrape_sinta_researches.py --limit 5
  python utils/sinta/scrape_sinta_researches.py --status
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
RESEARCH_DIR = Path(__file__).parent / "outs" / "researches"

SINTA_BASE    = "https://sinta.kemdiktisaintek.go.id"
RESEARCH_URL  = SINTA_BASE + "/affiliations/profile/{sinta_id}/?view=researches"

DELAY_PT   = 2.0   # jeda antar PT (detik)
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
    """GET url, kembalikan (BeautifulSoup, raw_text) atau (None, None)."""
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
# Ekstrak data penelitian
# ---------------------------------------------------------------------------

def scrape_researches(session, kode, sinta_id, nama):
    """
    Ambil data tren penelitian dari ?view=researches.
    Return dict dengan research_radar dan research_history.
    """
    url = RESEARCH_URL.format(sinta_id=sinta_id)
    soup, raw = fetch(session, url)
    if soup is None:
        return None

    result = {
        "kode_pt":  kode,
        "sinta_id": sinta_id,
        "nama":     nama,
        "research_radar":   {},
        "research_history": {},
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    if not raw:
        return result

    # --- Research Radar: Article / Conference / Others ---
    # JS: research-radar chart → indicator[{name:'Article',...}] + data:[{value:[2676,1512,162]}]
    # Ambil nama indikator (Article/Conference/Others) dari indicator array
    # lalu ambil values dari data array
    m = re.search(r"getElementById\(['\"]research-radar['\"]", raw)
    if m:
        block = raw[m.start():m.start() + 3000]

        # Ambil nama indikator dari: {name: 'Article', max: ...}
        indicators = re.findall(r"name\s*:\s*['\"]([^'\"]+)['\"]", block)
        indicators = [n for n in indicators if n.lower() in ("article", "conference", "others", "output")]

        # Ambil values dari: value: [2676, 1512, 162]
        m_val = re.search(r"value\s*:\s*\[\s*([\d\s,]+)\s*\]", block)
        if m_val and indicators:
            values = [int(v.strip()) for v in m_val.group(1).split(",") if v.strip().isdigit()]
            for name_key, val in zip(indicators, values):
                result["research_radar"][name_key.lower()] = val

    # --- Research History per Tahun: research-chart-articles ---
    # JS: xAxis.data:['2006','2007',...], series[0].data:[5,2,2,...]
    m = re.search(r"getElementById\(['\"]research-chart-articles['\"]", raw)
    if m:
        block = raw[m.start():m.start() + 5000]
        arrays = re.findall(r"data\s*:\s*\[([^\]]+)\]", block, re.DOTALL)
        if len(arrays) >= 2:
            years  = re.findall(r"['\"](\d{4})['\"]", arrays[0])
            counts = re.findall(r"\b(\d+)\b",          arrays[1])
            for yr, cnt in zip(years, counts):
                result["research_history"][yr] = int(cnt)

    return result


# ---------------------------------------------------------------------------
# Load daftar PT dari affprofile dir
# ---------------------------------------------------------------------------

def load_pt_list():
    """Baca semua file affprofile/*.json dan kembalikan list {kode, sinta_id, nama}."""
    pt_list = []
    for f in sorted(PROFILE_DIR.glob("*_sinta_afiliasi.json")):
        with open(f, encoding="utf-8") as fp:
            d = json.load(fp)
        kode = f.stem.replace("_sinta_afiliasi", "")
        sinta_id = d.get("sinta_id")
        nama = d.get("nama", d.get("nama_input", ""))
        pt_list.append({"kode": kode, "sinta_id": sinta_id, "nama": nama})
    return pt_list


# ---------------------------------------------------------------------------
# Status report
# ---------------------------------------------------------------------------

def print_status(research_dir):
    files = list(research_dir.glob("*_research.json"))
    total = len(files)
    with_history = 0
    for f in files:
        with open(f, encoding="utf-8") as fp:
            d = json.load(fp)
        if d.get("research_history"):
            with_history += 1
    print(f"\n{'='*50}")
    print(f"  File tersimpan      : {total}")
    print(f"  Dengan tren tahunan : {with_history}")
    print(f"  Output dir          : {research_dir}")
    print(f"{'='*50}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape tren penelitian SINTA Afiliasi (?view=researches)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--kode",   default="", help="Filter satu PT berdasarkan kode (e.g. 061008)")
    parser.add_argument("--limit",  type=int, default=0, help="Batasi jumlah PT (untuk testing)")
    parser.add_argument("--status", action="store_true", help="Tampilkan ringkasan output lalu keluar")
    args = parser.parse_args()

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    if args.status:
        print_status(RESEARCH_DIR)
        return

    # Load daftar PT dari affprofile
    pt_list = load_pt_list()
    print(f"Total PT dari affprofile: {len(pt_list)}")

    # Filter
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

        # Skip jika tidak ada sinta_id
        if not sinta_id:
            print(f"[{i}/{len(pt_list)}] SKIP {kode}: tidak ada sinta_id")
            no_sinta += 1
            continue

        # Skip jika sudah ada file (resume)
        out_file = RESEARCH_DIR / f"{kode}_research.json"
        if out_file.exists() and not args.kode:
            print(f"[{i}/{len(pt_list)}] Skip: {kode} {nama}")
            skipped += 1
            continue

        print(f"\n[{i}/{len(pt_list)}] {kode} — {nama}  (sinta_id={sinta_id})")

        try:
            data = scrape_researches(session, kode, sinta_id, nama)
            if data is None:
                print(f"  ERROR: fetch gagal")
                errors += 1
                continue

            # Ringkasan
            radar   = data.get("research_radar", {})
            history = data.get("research_history", {})
            print(f"  Radar : article={radar.get('article',0):,}  "
                  f"conference={radar.get('conference',0):,}  "
                  f"others={radar.get('others',0):,}")
            print(f"  Tren  : {len(history)} tahun — "
                  + ", ".join(f"{y}:{v}" for y, v in sorted(history.items())[-5:])
                  + (" ..." if len(history) > 5 else ""))

            # Simpan file
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
    print_status(RESEARCH_DIR)


if __name__ == "__main__":
    main()
