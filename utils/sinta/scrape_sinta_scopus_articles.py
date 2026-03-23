"""
Scraper SINTA — Artikel Scopus per Author

Sumber data:
  GET /authors/profile/{sinta_id}/?view=scopus&page=N

Data yang diambil per artikel:
  - EID Scopus       (dari URL artikel)
  - Judul
  - Kuartil          (Q1/Q2/Q3/Q4/'')
  - Nama jurnal
  - URL jurnal Scopus
  - Urutan penulis   ("Author Order : 1 of 7" → urutan=1, total=7)
  - Nama singkat     ("Creator : Solechan S.")
  - Tahun
  - Jumlah sitasi

Output: utils/sinta/outs/scopus/{kode_pt}/{sinta_id}_scopus.json
  {
    "sinta_id": "10220",
    "scraped_at": "2026-03-22T...",
    "total_scraped": 5,
    "articles": [
      {
        "eid": "2-s2.0-85147928674",
        "judul": "...",
        "kuartil": "Q1",
        "jurnal_nama": "Polymers",
        "jurnal_url": "https://www.scopus.com/sourceid/54222",
        "scopus_url": "https://www.scopus.com/record/display.uri?eid=...",
        "urutan_penulis": 1,
        "total_penulis": 7,
        "nama_singkat": "Solechan S.",
        "tahun": 2023,
        "sitasi": 4
      },
      ...
    ]
  }

Usage:
  cd chifoo_backend

  # Test satu author
  python utils/sinta/scrape_sinta_scopus_articles.py --sinta-id 10220

  # Scrape semua author di DB (resumable)
  python utils/sinta/scrape_sinta_scopus_articles.py

  # Paksa re-scrape
  python utils/sinta/scrape_sinta_scopus_articles.py --force

  # Status
  python utils/sinta/scrape_sinta_scopus_articles.py --status

  # Limit untuk testing
  python utils/sinta/scrape_sinta_scopus_articles.py --limit 20
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

BASE_URL  = "https://sinta.kemdiktisaintek.go.id/authors/profile/{sinta_id}/?view=scopus&page={page}"
LOGIN_URL = "https://sinta.kemdiktisaintek.go.id/logins/do_login"
HEADERS   = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
DELAY_OK  = 1.5   # detik antar request
DELAY_ERR = 5.0
MAX_RETRY = 3
ARTICLES_PER_PAGE = 10

OUT_BASE = Path(__file__).parent / "outs" / "scopus"
OUT_BASE.mkdir(parents=True, exist_ok=True)

# Credentials — isi sebelum scrape (atau lewat argumen CLI)
SINTA_USERNAME = "bana.handaga@ums.ac.id"
SINTA_PASSWORD = "Jawad@Mahdi1214"


def out_file_for(sinta_id: str, kode_pt: str) -> Path:
    d = OUT_BASE / kode_pt
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{sinta_id}_scopus.json"


def find_existing(sinta_id: str) -> Path | None:
    matches = list(OUT_BASE.glob(f"*/{sinta_id}_scopus.json"))
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_articles(html: str) -> list[dict]:
    """Parse semua artikel dari satu halaman HTML."""
    articles = []

    # Split by article block separator
    blocks = html.split('<div class="ar-list-item mb-5">')

    for blk in blocks[1:]:
        try:
            art = parse_one_article(blk)
            if art:
                articles.append(art)
        except Exception:
            pass

    return articles


def parse_one_article(blk: str) -> dict | None:
    # URL + EID
    url_m = re.search(
        r'href="(https://www\.scopus\.com/record/[^"]+eid=(2-s2\.0-\d+)[^"]*)"',
        blk
    )
    if not url_m:
        return None

    scopus_url = url_m.group(1)
    eid        = url_m.group(2)

    # Judul
    title_m = re.search(
        r'class="ar-title">.*?href="[^"]*"[^>]*>\s*(.+?)\s*</a>',
        blk, re.DOTALL
    )
    judul = title_m.group(1).strip() if title_m else ''
    # Bersihkan whitespace berlebih
    judul = re.sub(r'\s+', ' ', judul)

    # Kuartil
    q_m = re.search(r'ar-quartile[^>]*>.*?>\s*(Q\d)', blk, re.DOTALL)
    kuartil = q_m.group(1) if q_m else ''

    # Jurnal nama + URL
    journal_m = re.search(
        r'href="(https://www\.scopus\.com/sourceid/[^"]+)"[^>]*class="ar-pub"[^>]*>'
        r'[^<]*</i>\s*(.+?)\s*</a>',
        blk, re.DOTALL
    )
    if not journal_m:
        # Alternatif: class berbeda
        journal_m = re.search(
            r'class="ar-pub"[^>]*href="(https://www\.scopus\.com/sourceid/[^"]+)"[^>]*>'
            r'[^<]*</i>\s*(.+?)\s*</a>',
            blk, re.DOTALL
        )
    jurnal_url  = journal_m.group(1).strip() if journal_m else ''
    jurnal_nama = re.sub(r'\s+', ' ', journal_m.group(2).strip()) if journal_m else ''

    # Fallback nama jurnal jika URL tidak cocok
    if not jurnal_nama:
        jn_m = re.search(r'class="ar-pub"[^>]*>.*?</i>\s*(.+?)\s*</a>', blk, re.DOTALL)
        if jn_m:
            jurnal_nama = re.sub(r'\s+', ' ', jn_m.group(1).strip())

    # Urutan penulis
    order_m = re.search(r'Author Order\s*:\s*(\d+)\s*of\s*(\d+)', blk)
    urutan_penulis = int(order_m.group(1)) if order_m else 0
    total_penulis  = int(order_m.group(2)) if order_m else 0

    # Nama singkat
    creator_m = re.search(r'Creator\s*:\s*([^<&\n]+)', blk)
    nama_singkat = creator_m.group(1).strip() if creator_m else ''

    # Tahun
    year_m = re.search(r'class="ar-year"[^>]*>.*?>\s*(\d{4})', blk, re.DOTALL)
    tahun = int(year_m.group(1)) if year_m else None

    # Sitasi
    cited_m = re.search(r'(\d+)\s+cited', blk)
    sitasi = int(cited_m.group(1)) if cited_m else 0

    return {
        "eid":             eid,
        "judul":           judul,
        "kuartil":         kuartil,
        "jurnal_nama":     jurnal_nama,
        "jurnal_url":      jurnal_url,
        "scopus_url":      scopus_url,
        "urutan_penulis":  urutan_penulis,
        "total_penulis":   total_penulis,
        "nama_singkat":    nama_singkat,
        "tahun":           tahun,
        "sitasi":          sitasi,
    }


def is_not_found(html: str) -> bool:
    return 'Publication Not Found' in html


def get_last_page(html: str) -> int:
    """Ambil nomor halaman terakhir dari pagination."""
    pages = re.findall(r'[?&]page=(\d+)', html)
    if pages:
        return max(int(p) for p in pages)
    return 1


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

def do_login(session: requests.Session, username: str, password: str) -> bool:
    """Login ke SINTA, simpan ci_session cookie di session. Return True jika berhasil."""
    try:
        # Ambil halaman login dulu untuk mendapat cookie awal
        session.get("https://sinta.kemdiktisaintek.go.id/logins", headers=HEADERS, timeout=15)
        resp = session.post(
            LOGIN_URL,
            data={"username": username, "password": password},
            headers={**HEADERS, "Referer": "https://sinta.kemdiktisaintek.go.id/logins"},
            timeout=15,
            allow_redirects=True,
        )
        # Cek apakah login berhasil: redirect ke dashboard atau ada profil
        logged_in = (
            resp.status_code == 200
            and "logins" not in resp.url
            and "Invalid" not in resp.text
            and "salah" not in resp.text.lower()
        )
        return logged_in
    except Exception:
        return False


def is_session_expired(html: str) -> bool:
    """Cek apakah halaman adalah redirect ke login (session expired)."""
    return "logins" in html.lower() and 'name="username"' in html


def fetch_page(sinta_id: str, page: int, session: requests.Session,
               username: str = "", password: str = "") -> str | None:
    url = BASE_URL.format(sinta_id=sinta_id, page=page)
    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                html = resp.text
                # Re-login jika session expired
                if is_session_expired(html) and username:
                    print("    [re-login]", end=" ", flush=True)
                    if do_login(session, username, password):
                        continue  # retry setelah login
                    return None
                return html
            elif resp.status_code in (429, 503):
                time.sleep(DELAY_ERR * attempt)
            else:
                return None
        except Exception:
            if attempt == MAX_RETRY:
                return None
            time.sleep(DELAY_ERR)
    return None


def scrape_author(sinta_id: str, session: requests.Session,
                  username: str = "", password: str = "",
                  expected: int = 0) -> dict | None:
    # Halaman pertama
    html = fetch_page(sinta_id, 1, session, username, password)
    if html is None:
        return None

    if is_not_found(html):
        return {
            "sinta_id":      sinta_id,
            "scraped_at":    datetime.now(timezone.utc).isoformat(),
            "total_scraped": 0,
            "articles":      [],
        }

    articles = parse_articles(html)

    # Iterasi halaman berikutnya sampai kosong / not_found
    if username:
        # Dengan login: iterasi bebas sampai halaman kosong
        page = 2
        while True:
            time.sleep(DELAY_OK)
            html = fetch_page(sinta_id, page, session, username, password)
            if html is None or is_not_found(html):
                break
            page_arts = parse_articles(html)
            if not page_arts:
                break
            articles.extend(page_arts)
            page += 1
    else:
        # Tanpa login: hanya 1 halaman yang bisa diakses
        pass

    # Deduplikasi by EID (jaga-jaga)
    seen = set()
    unique = []
    for a in articles:
        if a["eid"] not in seen:
            seen.add(a["eid"])
            unique.append(a)

    return {
        "sinta_id":      sinta_id,
        "scraped_at":    datetime.now(timezone.utc).isoformat(),
        "total_scraped": len(unique),
        "articles":      unique,
    }


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_authors_with_pt() -> list[tuple[str, str, int]]:
    """Return list of (sinta_id, kode_pt, scopus_artikel) — hanya yang punya Scopus."""
    import os, sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")
    import django; django.setup()
    from apps.universities.models import SintaAuthor
    rows = (
        SintaAuthor.objects
        .filter(scopus_artikel__gt=0)
        .select_related("afiliasi")
        .values_list("sinta_id", "afiliasi__sinta_kode", "scopus_artikel")
        .order_by("afiliasi__sinta_kode", "sinta_id")
    )
    return [(sid, kode or "unknown", n) for sid, kode, n in rows]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def status():
    authors = get_authors_with_pt()
    total   = len(authors)
    done    = sum(1 for sid, _, _ in authors if find_existing(sid))
    all_files = list(OUT_BASE.glob("*/*_scopus.json"))
    total_arts = 0
    not_found_count = 0
    for f in all_files:
        try:
            d = json.loads(f.read_text())
            n = d.get("total_scraped", 0)
            total_arts += n
            if n == 0:
                not_found_count += 1
        except Exception:
            pass
    print(f"Author Scopus di DB  : {total:,}")
    print(f"Sudah discrape       : {done:,}")
    print(f"Belum discrape       : {total - done:,}")
    print(f"Total file JSON      : {len(all_files):,}")
    print(f"  Not Found (0 art)  : {not_found_count:,}")
    print(f"Total artikel scrape : {total_arts:,}")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(authors: list[tuple[str, str, int]], force: bool = False,
        username: str = "", password: str = ""):
    session = requests.Session()
    ok = skip = err = not_found = 0
    total = len(authors)

    # Login jika credentials tersedia
    if username:
        print(f"Login sebagai {username!r}...", end=" ", flush=True)
        if do_login(session, username, password):
            print("OK")
        else:
            print("GAGAL — lanjut tanpa login (hanya ≤10 artikel/author)")
            username = ""

    for i, (sid, kode_pt, expected) in enumerate(authors, 1):
        if find_existing(sid) and not force:
            skip += 1
            continue

        result = scrape_author(sid, session, username, password, expected)

        if result is None:
            print(f"  [{i}/{total}] {sid} ERROR")
            err += 1
            time.sleep(DELAY_ERR)
            continue

        dest = out_file_for(sid, kode_pt)
        dest.write_text(json.dumps(result, ensure_ascii=False))

        n = result["total_scraped"]
        if n == 0:
            print(f"  [{i}/{total}] {sid} not_found (expected={expected})")
            not_found += 1
        else:
            print(f"  [{i}/{total}] {sid} ok ({n} artikel, expected={expected})")
            ok += 1

        time.sleep(DELAY_OK)

        if i % 100 == 0:
            print(f"\n  --- [{i}/{total}] ok={ok} not_found={not_found} skip={skip} err={err} ---\n")

    print(f"\nSelesai: {ok} scraped, {not_found} not_found, {skip} dilewati, {err} error.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape artikel Scopus dari SINTA")
    parser.add_argument("--sinta-id", help="Scrape satu author saja")
    parser.add_argument("--force",    action="store_true", help="Re-scrape meski sudah ada")
    parser.add_argument("--status",   action="store_true", help="Tampilkan status")
    parser.add_argument("--limit",    type=int, default=0, help="Batasi jumlah author")
    parser.add_argument("--username", default=SINTA_USERNAME, help="Username SINTA")
    parser.add_argument("--password", default=SINTA_PASSWORD, help="Password SINTA")
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
            kode_pt  = a.afiliasi.sinta_kode if a.afiliasi else "unknown"
            expected = a.scopus_artikel
        except Exception:
            kode_pt  = "unknown"
            expected = 0
        authors = [(args.sinta_id, kode_pt, expected)]
    else:
        print("Mengambil daftar author Scopus dari DB...")
        authors = get_authors_with_pt()
        print(f"  → {len(authors):,} author ditemukan")

    if args.limit:
        authors = authors[:args.limit]

    run(authors, force=args.force, username=args.username, password=args.password)


if __name__ == "__main__":
    main()
