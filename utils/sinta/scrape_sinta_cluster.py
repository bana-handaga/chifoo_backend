"""
Scraper SINTA — Klasterisasi Perguruan Tinggi (Metrics Cluster 2026)

Sumber data:
  Halaman : /affiliations/profile/{sinta_id}/?view=matricscluster2026

Data yang diambil:
  - cluster_name  : nama cluster (Mandiri / Utama / Madya / Pratama / Binaan)
  - total_score   : skor total keseluruhan
  - scores        : skor per 6 kategori (raw, ternormal, tertimbang):
      publication, hki, kelembagaan, research, community_service, sdm
  - items         : detail semua item kode (AI1, AN1, KI1, P1, PM1, DOS1, dst.)

Periode penilaian: 2022 – 2024

Prasyarat:
  Data profil afiliasi sudah ada di utils/sinta/outs/affprofile/
  (hasil dari scrape_sinta_afiliasi.py)

Input  : utils/sinta/outs/affprofile/*_sinta_afiliasi.json
Output : utils/sinta/outs/cluster/{kode}_cluster.json

Usage:
  cd chifoo_backend
  python utils/sinta/scrape_sinta_cluster.py
  python utils/sinta/scrape_sinta_cluster.py --kode 061008
  python utils/sinta/scrape_sinta_cluster.py --limit 5
  python utils/sinta/scrape_sinta_cluster.py --status
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
CLUSTER_DIR = Path(__file__).parent / "outs" / "cluster"

SINTA_BASE   = "https://sinta.kemdiktisaintek.go.id"
CLUSTER_URL  = SINTA_BASE + "/affiliations/profile/{sinta_id}/?view=matricscluster2026"

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

# Mapping section header → field key
SECTION_MAP = {
    "Publication":       "publication",
    "HKI":               "hki",
    "Kelembagaan":       "kelembagaan",
    "Research":          "research",
    "Community Service": "community_service",
    "SDM":               "sdm",
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
# Parse angka format Indonesia ("1.234,56" → 1234.56)
# ---------------------------------------------------------------------------

def parse_id_number(text):
    """Konversi angka format Indonesia ke float. '1.234,56' → 1234.56"""
    if not text:
        return 0.0
    clean = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Ekstrak data cluster
# ---------------------------------------------------------------------------

def scrape_cluster(session, kode, sinta_id, nama):
    """
    Ambil data Klasterisasi PT dari ?view=matricscluster2026.
    Return dict lengkap.
    """
    url = CLUSTER_URL.format(sinta_id=sinta_id)
    soup, raw = fetch(session, url)
    if soup is None:
        return None

    result = {
        "kode_pt":      kode,
        "sinta_id":     sinta_id,
        "nama":         nama,
        "cluster_name": "",
        "total_score":  0.0,
        "scores":       {},
        "items":        {},
        "scraped_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # --- Cluster Name ---
    m = re.search(r'Affiliation Cluster\s+is\s+["\']([^"\']+)["\']', raw, re.IGNORECASE)
    if m:
        result["cluster_name"] = m.group(1).strip()
    else:
        # Fallback: cari di h4
        for h in soup.find_all("h4"):
            t = h.text.strip()
            if "Cluster" in t and "is" in t:
                m2 = re.search(r'["\']([^"\']+)["\']', t)
                if m2:
                    result["cluster_name"] = m2.group(1).strip()
                break

    # --- Parse tabel di #sixtab ---
    sixtab = soup.find(id="sixtab")
    if not sixtab:
        return result

    table = sixtab.find("table")
    if not table:
        return result

    current_section = ""
    current_key     = ""

    for row in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
        cells = [c for c in cells if c]
        if not cells:
            continue

        first = cells[0]

        # --- Deteksi header section "Score in XXX" ---
        if first.startswith("Score in "):
            label = first[len("Score in "):].strip()
            current_section = label
            current_key     = SECTION_MAP.get(label, label.lower().replace(" ", "_"))
            result["scores"][current_key] = {
                "total_raw": 0.0,
                "total_ternormal": 0.0,
                "total_weighted": 0.0,
            }
            continue

        # --- Total Score XXX (raw) ---
        if first.startswith("Total Score") and "Ternormal" not in first and "%" not in first and current_key:
            val = cells[-1] if len(cells) > 1 else "0"
            result["scores"][current_key]["total_raw"] = parse_id_number(val)
            continue

        # --- Total Score XXX Ternormal (XX%) ---
        if "Ternormal (" in first and current_key:
            val = cells[-1] if len(cells) > 1 else "0"
            result["scores"][current_key]["total_weighted"] = parse_id_number(val)
            continue

        # --- Total Score XXX Ternormal (tanpa %) ---
        if first.startswith("Total Score") and "Ternormal" in first and "%" not in first and current_key:
            val = cells[-1] if len(cells) > 1 else "0"
            result["scores"][current_key]["total_ternormal"] = parse_id_number(val)
            continue

        # --- Total Score Penyesuaian Prodi (Kelembagaan) ---
        if "Penyesuaian" in first and current_key:
            continue  # skip subtotal intermediate

        # --- TOTAL ALL SCORE ---
        if "TOTAL ALL" in first:
            val = cells[-1] if len(cells) > 1 else "0"
            result["total_score"] = parse_id_number(val)
            continue

        # --- Revenue Generating (baris di luar section normal) ---
        if first.startswith("REV") and len(cells) >= 5:
            code, name, weight, value, total = cells[0], cells[1], cells[2], cells[3], cells[4]
            result["items"][code] = {
                "section": current_key,
                "name":    name,
                "weight":  parse_id_number(weight),
                "value":   parse_id_number(value),
                "total":   parse_id_number(total),
            }
            continue

        # --- Baris item: [CODE, Name, Weight, Value, Total] ---
        if len(cells) >= 5 and current_key:
            code = cells[0]
            # Kode valid: huruf+angka, minimal 2 karakter, tidak terlalu panjang
            if re.match(r'^[A-Z]{1,4}\d{1,3}$', code):
                name   = cells[1]
                weight = cells[2]
                value  = cells[3]
                total  = cells[4]
                result["items"][code] = {
                    "section": current_key,
                    "name":    name,
                    "weight":  parse_id_number(weight),
                    "value":   parse_id_number(value),
                    "total":   parse_id_number(total),
                }

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

def print_status(cluster_dir):
    files = list(cluster_dir.glob("*_cluster.json"))
    clusters = {}
    no_cluster = 0
    for f in files:
        d = json.load(open(f))
        c = d.get("cluster_name", "")
        if c:
            clusters[c] = clusters.get(c, 0) + 1
        else:
            no_cluster += 1

    print(f"\n{'='*50}")
    print(f"  File tersimpan : {len(files)}")
    for c, n in sorted(clusters.items(), key=lambda x: -x[1]):
        print(f"  {c:<20}: {n} PT")
    if no_cluster:
        print(f"  (tidak ada data): {no_cluster} PT")
    print(f"  Output dir     : {cluster_dir}")
    print(f"{'='*50}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Klasterisasi PT SINTA (?view=matricscluster2026)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--kode",   default="", help="Filter satu PT (e.g. 061008)")
    parser.add_argument("--limit",  type=int, default=0, help="Batasi jumlah PT")
    parser.add_argument("--status", action="store_true", help="Tampilkan ringkasan lalu keluar")
    args = parser.parse_args()

    CLUSTER_DIR.mkdir(parents=True, exist_ok=True)

    if args.status:
        print_status(CLUSTER_DIR)
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

        out_file = CLUSTER_DIR / f"{kode}_cluster.json"
        if out_file.exists() and not args.kode:
            print(f"[{i}/{len(pt_list)}] Skip: {kode} {nama}")
            skipped += 1
            continue

        print(f"\n[{i}/{len(pt_list)}] {kode} — {nama}  (sinta_id={sinta_id})")

        try:
            data = scrape_cluster(session, kode, sinta_id, nama)
            if data is None:
                print(f"  ERROR: fetch gagal")
                errors += 1
                continue

            scores = data.get("scores", {})
            print(f"  Cluster : {data.get('cluster_name', '-')}")
            print(f"  Total   : {data.get('total_score', 0):.2f}")
            print(f"  Pub={scores.get('publication',{}).get('total_weighted',0):.2f}  "
                  f"HKI={scores.get('hki',{}).get('total_weighted',0):.2f}  "
                  f"Lemb={scores.get('kelembagaan',{}).get('total_weighted',0):.2f}  "
                  f"Res={scores.get('research',{}).get('total_weighted',0):.2f}  "
                  f"PM={scores.get('community_service',{}).get('total_weighted',0):.2f}  "
                  f"SDM={scores.get('sdm',{}).get('total_weighted',0):.2f}")
            print(f"  Items   : {len(data.get('items', {}))} kode")

            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            done += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
            errors += 1

        time.sleep(DELAY_PT)

    print(f"\n=== Selesai ===")
    print(f"  Diproses : {done}")
    print(f"  Di-skip  : {skipped}")
    print(f"  No sinta : {no_sinta}")
    print(f"  Error    : {errors}")
    print_status(CLUSTER_DIR)


if __name__ == "__main__":
    main()
