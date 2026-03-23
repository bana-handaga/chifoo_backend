"""
Scraper SINTA — Publikasi Google Scholar per Author

Sumber data:
  GET /authors/profile/{sinta_id}/?view=googlescholar&page=N
  → daftar publikasi milik author dari Google Scholar

Data yang diambil per publikasi:
  - judul       : judul artikel
  - penulis     : string penulis (dari SINTA)
  - jurnal      : nama jurnal/penerbit + volume/no
  - tahun       : tahun publikasi
  - sitasi      : jumlah sitasi (N cited)
  - url         : link ke Google Scholar search

Output : utils/sinta/outs/gscholar/{sinta_id}_gscholar.json
  {
    "sinta_id": "6681079",
    "scraped_at": "2026-03-22T...",
    "total": 23,
    "publications": [
      {
        "pub_id": "6681079_0",
        "judul": "...",
        "penulis": "...",
        "jurnal": "...",
        "tahun": 2024,
        "sitasi": 5,
        "url": "https://scholar.google.com/..."
      },
      ...
    ]
  }

Usage:
  cd chifoo_backend

  # Scrape satu author (test)
  python utils/sinta/scrape_sinta_author_gscholar.py --sinta-id 6681079

  # Scrape semua author di DB (resumable)
  python utils/sinta/scrape_sinta_author_gscholar.py

  # Paksa re-scrape
  python utils/sinta/scrape_sinta_author_gscholar.py --force

  # Cek status
  python utils/sinta/scrape_sinta_author_gscholar.py --status

  # Limit untuk testing
  python utils/sinta/scrape_sinta_author_gscholar.py --limit 20
"""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL   = "https://sinta.kemdiktisaintek.go.id/authors/profile/{sinta_id}/?view=googlescholar&page={page}"
HEADERS    = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
DELAY_OK   = 1.2   # detik antar request
DELAY_ERR  = 5.0   # detik setelah error
MAX_RETRY  = 3
MAX_PAGES  = 100   # batas aman per author

OUT_BASE   = Path(__file__).parent / "outs" / "gscholar"
OUT_BASE.mkdir(parents=True, exist_ok=True)


def out_file_for(sinta_id: str, kode_pt: str) -> Path:
    """Kembalikan path output: outs/gscholar/{kode_pt}/{sinta_id}_gscholar.json"""
    d = OUT_BASE / kode_pt
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sinta_id}_gscholar.json"


def find_existing(sinta_id: str) -> Path | None:
    """Cari file lama di semua subfolder (untuk backward compat / resume)."""
    # Cek dulu di root (file lama)
    root_f = OUT_BASE / f"{sinta_id}_gscholar.json"
    if root_f.exists():
        return root_f
    # Cari di subfolder PT
    matches = list(OUT_BASE.glob(f"*/{sinta_id}_gscholar.json"))
    return matches[0] if matches else None

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_page(html: str, sinta_id: str, page: int) -> list[dict]:
    """Parse satu halaman Google Scholar SINTA, return list publikasi."""
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("div.ar-list-item")
    publications = []

    for idx, item in enumerate(items):
        # Judul + URL
        title_el = item.select_one("div.ar-title a")
        judul = title_el.get_text(strip=True) if title_el else ""
        url   = title_el.get("href", "") if title_el else ""

        # Penulis & jurnal (dua baris ar-meta)
        metas = item.select("div.ar-meta a")
        penulis = ""
        jurnal  = ""
        for m in metas:
            txt = m.get_text(strip=True)
            if txt.startswith("Authors"):
                penulis = re.sub(r"^Authors\s*:\s*", "", txt)
            elif m.select_one("i.el-book") or m.get("class", [""])[0] == "ar-pub":
                jurnal = txt
            elif "ar-pub" in " ".join(m.get("class", [])):
                jurnal = txt

        # Tahun (ar-year)
        year_el = item.select_one("a.ar-year")
        tahun = None
        if year_el:
            m_yr = re.search(r"\d{4}", year_el.get_text())
            if m_yr:
                tahun = int(m_yr.group())

        # Sitasi (ar-cited)
        cited_el = item.select_one("a.ar-cited")
        sitasi = 0
        if cited_el:
            m_ct = re.search(r"(\d+)\s+cited", cited_el.get_text())
            if m_ct:
                sitasi = int(m_ct.group(1))

        # pub_id: sinta_id + nomor urut global
        offset = (page - 1) * 10 + idx
        pub_id = f"{sinta_id}_{offset}"

        if judul:
            publications.append({
                "pub_id":  pub_id,
                "judul":   judul,
                "penulis": penulis,
                "jurnal":  jurnal,
                "tahun":   tahun,
                "sitasi":  sitasi,
                "url":     url,
            })

    return publications


def scrape_author(sinta_id: str, session: requests.Session) -> dict | None:
    """Scrape semua halaman GScholar untuk satu author, return dict hasil."""
    all_pubs = []

    for page in range(1, MAX_PAGES + 1):
        url = BASE_URL.format(sinta_id=sinta_id, page=page)

        for attempt in range(1, MAX_RETRY + 1):
            try:
                resp = session.get(url, headers=HEADERS, timeout=20)
                if resp.status_code == 200:
                    break
                elif resp.status_code in (429, 503):
                    print(f"    [{sinta_id}] p{page} HTTP {resp.status_code} — tunggu {DELAY_ERR}s")
                    time.sleep(DELAY_ERR * attempt)
                else:
                    print(f"    [{sinta_id}] p{page} HTTP {resp.status_code}")
                    return None
            except Exception as e:
                print(f"    [{sinta_id}] p{page} error: {e}")
                if attempt == MAX_RETRY:
                    return None
                time.sleep(DELAY_ERR)

        pubs = parse_page(resp.text, sinta_id, page)
        if not pubs:
            break   # halaman kosong → selesai

        all_pubs.extend(pubs)
        time.sleep(DELAY_OK)

    return {
        "sinta_id":   sinta_id,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "total":      len(all_pubs),
        "publications": all_pubs,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def get_authors_with_pt() -> list[tuple[str, str]]:
    """
    Ambil (sinta_id, kode_pt) semua author dari DB Django.
    kode_pt diambil dari afiliasi.sinta_kode (kode PT di SINTA).
    """
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


def status():
    authors = get_authors_with_pt()
    total = len(authors)
    done  = sum(1 for sid, kode in authors if find_existing(sid))
    all_files = list(OUT_BASE.glob("*/*_gscholar.json")) + list(OUT_BASE.glob("*_gscholar.json"))
    total_pubs = sum(
        json.loads(f.read_text()).get("total", 0) for f in all_files
    )
    print(f"Total author di DB   : {total}")
    print(f"Sudah discrape       : {done}")
    print(f"Belum discrape       : {total - done}")
    print(f"Total file JSON      : {len(all_files)}")
    print(f"Total publikasi (GS) : {total_pubs:,}")


def run(authors: list[tuple[str, str]], force=False):
    session = requests.Session()
    ok = skip = err = 0
    total = len(authors)

    for i, (sid, kode_pt) in enumerate(authors, 1):
        existing = find_existing(sid)
        if existing and not force:
            skip += 1
            continue

        print(f"  [{i}/{total}] {sid} ({kode_pt}) ...", end=" ", flush=True)
        result = scrape_author(sid, session)

        if result is None:
            print("ERROR")
            err += 1
            time.sleep(DELAY_ERR)
            continue

        dest = out_file_for(sid, kode_pt)
        dest.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"ok ({result['total']} pub) → {dest.parent.name}/")
        ok += 1

        if i % 50 == 0:
            print(f"\n  --- Progress [{i}/{total}]: ok={ok} skip={skip} err={err} ---\n")

    print(f"\nSelesai: {ok} scraped, {skip} dilewati, {err} error.")


def main():
    parser = argparse.ArgumentParser(description="Scrape Google Scholar publications dari SINTA")
    parser.add_argument("--sinta-id",  help="Scrape satu author saja")
    parser.add_argument("--force",     action="store_true", help="Re-scrape meski sudah ada")
    parser.add_argument("--status",    action="store_true", help="Tampilkan status saja")
    parser.add_argument("--limit",     type=int, default=0, help="Batasi jumlah author")
    args = parser.parse_args()

    if args.status:
        status()
        return

    if args.sinta_id:
        # Untuk single author, cari kode_pt dari DB jika bisa
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

    if args.limit:
        authors = authors[:args.limit]

    run(authors, force=args.force)


if __name__ == "__main__":
    main()
