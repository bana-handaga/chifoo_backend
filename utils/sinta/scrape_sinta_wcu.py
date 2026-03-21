"""
Scraper SINTA — WCU Analysis: Paper per Subject per Year

Sumber data:
  Halaman WCU : /affiliations/wcuanalysis/{sinta_id}

Data yang diambil:
  - paper_per_subject : jumlah paper per bidang keilmuan per tahun
      Bidang: Arts & Humanities, Engineering & Technology,
              Life Sciences & Medicine, Natural Sciences,
              Social Sciences & Management, Overall
  Sumber data: Scival (Elsevier)

Prasyarat:
  Data profil afiliasi sudah ada di utils/sinta/outs/affprofile/
  (hasil dari scrape_sinta_afiliasi.py)

Input  : utils/sinta/outs/affprofile/*_sinta_afiliasi.json  (untuk sinta_id)
Output : utils/sinta/outs/wcu/{kode}_wcu.json

Usage:
  cd chifoo_backend
  python utils/sinta/scrape_sinta_wcu.py
  python utils/sinta/scrape_sinta_wcu.py --kode 061008
  python utils/sinta/scrape_sinta_wcu.py --limit 5
  python utils/sinta/scrape_sinta_wcu.py --status
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

PROFILE_DIR = Path(__file__).parent / "outs" / "affprofile"
WCU_DIR     = Path(__file__).parent / "outs" / "wcu"

SINTA_BASE = "https://sinta.kemdiktisaintek.go.id"
WCU_URL    = SINTA_BASE + "/affiliations/wcuanalysis/{sinta_id}"

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

# Urutan subject area sesuai legend di chart wcu_research_output1
SUBJECTS = [
    "arts_humanities",
    "engineering_technology",
    "life_sciences_medicine",
    "natural_sciences",
    "social_sciences_management",
    "overall",
]

SUBJECT_LABELS = {
    "arts_humanities":              "Arts & Humanities",
    "engineering_technology":       "Engineering & Technology",
    "life_sciences_medicine":       "Life Sciences & Medicine",
    "natural_sciences":             "Natural Sciences",
    "social_sciences_management":   "Social Sciences & Management",
    "overall":                      "Overall",
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
            return r.text
        except Exception as e:
            print(f"  [attempt {attempt}/{retries}] {url}: {e}")
            if attempt < retries:
                time.sleep(RETRY_WAIT)
    return None


# ---------------------------------------------------------------------------
# Ekstrak data WCU
# ---------------------------------------------------------------------------

def scrape_wcu(session, kode, sinta_id, nama):
    """
    Ambil data Paper per Subject per Year dari halaman wcuanalysis.
    Return dict dengan paper_per_subject (subject → {year: count}).
    """
    url = WCU_URL.format(sinta_id=sinta_id)
    raw = fetch(session, url)
    if raw is None:
        return None

    result = {
        "kode_pt":         kode,
        "sinta_id":        sinta_id,
        "nama":            nama,
        "paper_per_subject": {s: {} for s in SUBJECTS},
        "scraped_at":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Cari blok chart wcu_research_output1 — mulai dari option variable, bukan getElementById
    m = re.search(r'option_wcu_research_output1\s*=\s*\{', raw)
    if not m:
        return result

    block = raw[m.start():m.start() + 12000]

    # Ambil years dari xAxis.data
    xaxis_m = re.search(r'xAxis.*?data\s*:\s*\[([^\]]+)\]', block, re.DOTALL)
    if not xaxis_m:
        return result
    years = re.findall(r"'(\d{4})'", xaxis_m.group(1))

    # Ambil series per subject — ikuti urutan legend
    # Pattern: name: 'Subject Name', type: 'bar', data: [n, n, n, ...]
    series_pattern = re.compile(
        r"name\s*:\s*'([^']+)'.*?data\s*:\s*\[([^\]]+)\]",
        re.DOTALL
    )

    # Kumpulkan semua match name → data
    series_map = {}
    for name, data_str in series_pattern.findall(block):
        if name in ("Max", "Min", "Avg"):
            continue
        nums = re.findall(r'\b(\d+)\b', data_str)
        series_map[name] = nums

    # Map nama label → field key
    label_to_key = {v: k for k, v in SUBJECT_LABELS.items()}

    for label, key in label_to_key.items():
        nums = series_map.get(label, [])
        for yr, cnt in zip(years, nums):
            result["paper_per_subject"][key][yr] = int(cnt)

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

def print_status(wcu_dir):
    files = list(wcu_dir.glob("*_wcu.json"))
    with_data = sum(
        1 for f in files
        if any(
            json.load(open(f))["paper_per_subject"].get(s)
            for s in SUBJECTS
        )
    )
    print(f"\n{'='*50}")
    print(f"  File tersimpan  : {len(files)}")
    print(f"  Dengan data     : {with_data}")
    print(f"  Output dir      : {wcu_dir}")
    print(f"{'='*50}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape WCU Paper per Subject per Year dari SINTA",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--kode",   default="", help="Filter satu PT (e.g. 061008)")
    parser.add_argument("--limit",  type=int, default=0, help="Batasi jumlah PT")
    parser.add_argument("--status", action="store_true", help="Tampilkan ringkasan lalu keluar")
    args = parser.parse_args()

    WCU_DIR.mkdir(parents=True, exist_ok=True)

    if args.status:
        print_status(WCU_DIR)
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

        out_file = WCU_DIR / f"{kode}_wcu.json"
        if out_file.exists() and not args.kode:
            print(f"[{i}/{len(pt_list)}] Skip: {kode} {nama}")
            skipped += 1
            continue

        print(f"\n[{i}/{len(pt_list)}] {kode} — {nama}  (sinta_id={sinta_id})")

        try:
            data = scrape_wcu(session, kode, sinta_id, nama)
            if data is None:
                print(f"  ERROR: fetch gagal")
                errors += 1
                continue

            overall = data["paper_per_subject"].get("overall", {})
            eng     = data["paper_per_subject"].get("engineering_technology", {})
            soc     = data["paper_per_subject"].get("social_sciences_management", {})
            print(f"  Overall : {dict(list(sorted(overall.items()))[-5:])}")
            print(f"  Eng&Tech: {dict(list(sorted(eng.items()))[-5:])}")
            print(f"  Soc&Mgmt: {dict(list(sorted(soc.items()))[-5:])}")

            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            done += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            errors += 1

        time.sleep(DELAY_PT)

    print(f"\n=== Selesai ===")
    print(f"  Diproses : {done}")
    print(f"  Di-skip  : {skipped}")
    print(f"  No sinta : {no_sinta}")
    print(f"  Error    : {errors}")
    print_status(WCU_DIR)


if __name__ == "__main__":
    main()
