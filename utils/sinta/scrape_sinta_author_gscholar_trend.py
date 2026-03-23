"""
Scraper SINTA — Tren Publikasi & Sitasi Google Scholar per Author

Sumber data (1 request per author):
  GET /authors/profile/{sinta_id}/?view=googlescholar

Data yang diambil:
  - Publications per tahun  (dari ECharts series 'Publications')
  - Citations per tahun     (dari ECharts series 'Citations')

Output : utils/sinta/outs/gscholar/{kode_pt}/{sinta_id}_trend.json
  {
    "sinta_id": "6005631",
    "scraped_at": "2026-03-22T...",
    "trend": [
      {"tahun": 2017, "pub": 3, "cite": 12},
      {"tahun": 2018, "pub": 5, "cite": 20},
      ...
    ]
  }

Usage:
  cd chifoo_backend

  # Scrape satu author (test)
  python utils/sinta/scrape_sinta_author_gscholar_trend.py --sinta-id 6005631

  # Scrape semua author di DB (resumable)
  python utils/sinta/scrape_sinta_author_gscholar_trend.py

  # Paksa re-scrape
  python utils/sinta/scrape_sinta_author_gscholar_trend.py --force

  # Status
  python utils/sinta/scrape_sinta_author_gscholar_trend.py --status

  # Limit untuk testing
  python utils/sinta/scrape_sinta_author_gscholar_trend.py --limit 20
"""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL  = "https://sinta.kemdiktisaintek.go.id/authors/profile/{sinta_id}/?view=googlescholar"
HEADERS   = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
DELAY_OK  = 1.0   # detik antar request
DELAY_ERR = 5.0
MAX_RETRY = 3

OUT_BASE  = Path(__file__).parent / "outs" / "gscholar"
OUT_BASE.mkdir(parents=True, exist_ok=True)


def out_file_for(sinta_id: str, kode_pt: str) -> Path:
    d = OUT_BASE / kode_pt
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sinta_id}_trend.json"


def find_existing(sinta_id: str) -> Path | None:
    matches = list(OUT_BASE.glob(f"*/{sinta_id}_trend.json"))
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_trend(html: str) -> list[dict]:
    """
    Ekstrak data tren dari ECharts google-chart-articles.
    Return list: [{"tahun": 2017, "pub": 3, "cite": 12}, ...]
    """
    # Cari blok inisialisasi chart (dari 'google-chart-articles') sampai setOption
    idx = html.rfind("google-chart-articles'")
    if idx < 0:
        idx = html.rfind('google-chart-articles"')
    if idx < 0:
        return []

    # Ambil 12000 karakter setelah titik chart ditemukan
    block = html[idx:idx + 12000]

    # Ambil xAxis data (tahun)
    years_match = re.search(
        r"xAxis\s*:\s*\[.*?data\s*:\s*\[([^\]]+)\]", block, re.DOTALL
    )
    if not years_match:
        return []

    years = []
    for y in years_match.group(1).split(","):
        y = y.strip().strip("'\"")
        if y.isdigit():
            years.append(int(y))

    # Cari posisi "series:" lalu ambil dua data array berurutan
    series_idx = block.find("series:")
    if series_idx < 0:
        return []

    series_section = block[series_idx:]

    def extract_data_arrays(text: str) -> list[list[int]]:
        """Ambil semua data: [ angka, angka, ... ] dalam urutan kemunculan."""
        results = []
        for m in re.finditer(r"data\s*:\s*\[([\d\s,]+)\]", text, re.DOTALL):
            vals = [int(v.strip()) for v in m.group(1).split(",") if v.strip().isdigit()]
            if vals:
                results.append(vals)
        return results

    data_arrays = extract_data_arrays(series_section)

    # Urutan series di chart: [0] = Publications, [1] = Citations
    pub_data  = data_arrays[0] if len(data_arrays) > 0 else []
    cite_data = data_arrays[1] if len(data_arrays) > 1 else []

    if not years:
        return []

    trend = []
    for i, year in enumerate(years):
        pub  = pub_data[i]  if i < len(pub_data)  else 0
        cite = cite_data[i] if i < len(cite_data) else 0
        if pub > 0 or cite > 0:
            trend.append({"tahun": year, "pub": pub, "cite": cite})

    return trend


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

def scrape_author(sinta_id: str, session: requests.Session) -> dict | None:
    url = BASE_URL.format(sinta_id=sinta_id)

    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                break
            elif resp.status_code in (429, 503):
                time.sleep(DELAY_ERR * attempt)
            else:
                return None
        except Exception as e:
            if attempt == MAX_RETRY:
                return None
            time.sleep(DELAY_ERR)

    trend = parse_trend(resp.text)

    return {
        "sinta_id":   sinta_id,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "trend":      trend,
    }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_authors_with_pt() -> list[tuple[str, str]]:
    import os, sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")
    import django; django.setup()
    from apps.universities.models import SintaAuthor
    rows = (
        SintaAuthor.objects
        .select_related("afiliasi")
        .values_list("sinta_id", "afiliasi__sinta_kode")
        .order_by("afiliasi__sinta_kode", "sinta_id")
    )
    return [(sid, kode or "unknown") for sid, kode in rows]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def status():
    authors = get_authors_with_pt()
    total   = len(authors)
    done    = sum(1 for sid, _ in authors if find_existing(sid))
    all_files = list(OUT_BASE.glob("*/*_trend.json"))
    total_rows = sum(len(json.loads(f.read_text()).get("trend", [])) for f in all_files)
    print(f"Total author di DB   : {total}")
    print(f"Sudah discrape       : {done}")
    print(f"Belum discrape       : {total - done}")
    print(f"Total file JSON      : {len(all_files)}")
    print(f"Total baris trend    : {total_rows:,}")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(authors: list[tuple[str, str]], force=False):
    session = requests.Session()
    ok = skip = err = 0
    total = len(authors)

    for i, (sid, kode_pt) in enumerate(authors, 1):
        if find_existing(sid) and not force:
            skip += 1
            continue

        result = scrape_author(sid, session)

        if result is None:
            print(f"  [{i}/{total}] {sid} ERROR")
            err += 1
            time.sleep(DELAY_ERR)
            continue

        dest = out_file_for(sid, kode_pt)
        dest.write_text(json.dumps(result, ensure_ascii=False))
        n = len(result["trend"])
        print(f"  [{i}/{total}] {sid} ok ({n} tahun)")
        ok += 1
        time.sleep(DELAY_OK)

        if i % 100 == 0:
            print(f"\n  --- [{i}/{total}] ok={ok} skip={skip} err={err} ---\n")

    print(f"\nSelesai: {ok} scraped, {skip} dilewati, {err} error.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape Google Scholar trend dari SINTA")
    parser.add_argument("--sinta-id", help="Scrape satu author saja")
    parser.add_argument("--force",    action="store_true", help="Re-scrape meski sudah ada")
    parser.add_argument("--status",   action="store_true", help="Tampilkan status")
    parser.add_argument("--limit",    type=int, default=0, help="Batasi jumlah author")
    parser.add_argument("--offset",   type=int, default=0, help="Mulai dari index ke-N")
    args = parser.parse_args()

    if args.status:
        status()
        return

    if args.sinta_id:
        try:
            import os, sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")
            import django; django.setup()
            from apps.universities.models import SintaAuthor
            a = SintaAuthor.objects.select_related("afiliasi").get(sinta_id=args.sinta_id)
            kode_pt = a.afiliasi.sinta_kode if a.afiliasi else "unknown"
        except Exception:
            kode_pt = "unknown"
        authors = [(args.sinta_id, kode_pt)]
    else:
        print("Mengambil daftar author dari DB...")
        authors = get_authors_with_pt()
        print(f"  → {len(authors)} author ditemukan")

    if args.offset:
        authors = authors[args.offset:]
    if args.limit:
        authors = authors[:args.limit]

    run(authors, force=args.force)


if __name__ == "__main__":
    main()
