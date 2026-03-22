"""
Scraper SINTA — Daftar Author per Departemen

Sumber data:
  https://sinta.kemdiktisaintek.go.id/departments/authors/{sinta_id_pt}/{uuid1}/{uuid2}
  (URL = replace '/profile/' → '/authors/' dari url_profil departemen)

Data per author:
  - sinta_id       : ID author di SINTA
  - nama           : nama lengkap
  - url_profil     : URL profil author di SINTA
  - foto_url       : URL foto (dari Google Scholar atau default)
  - dept_nama      : nama departemen (dari .profile-dept)
  - scopus_hindex  : Scopus H-Index
  - gs_hindex      : Google Scholar H-Index
  - sinta_score_3yr: SINTA Score 3Yr
  - sinta_score    : SINTA Score Overall
  - affil_score_3yr: Affil Score 3Yr
  - affil_score    : Affil Score Overall

Input  : utils/sinta/outs/departments/{kode_pt}/departments.json
         → field url_profil & kode_dept per departemen

Output : utils/sinta/outs/departments/{kode_pt}/{kode_dept}_author_list.json

Usage:
  # Scrape semua PT (resumable)
  python utils/sinta/scrape_sinta_dept_authors.py

  # Filter satu PT
  python utils/sinta/scrape_sinta_dept_authors.py --kode 061008

  # Paksa re-scrape
  python utils/sinta/scrape_sinta_dept_authors.py --force

  # Ringkasan
  python utils/sinta/scrape_sinta_dept_authors.py --status

  # Limit total request (testing)
  python utils/sinta/scrape_sinta_dept_authors.py --limit 5
"""

import argparse
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEPT_DIR   = Path(__file__).parent / "outs" / "departments"
SINTA_BASE = "https://sinta.kemdiktisaintek.go.id"

DELAY      = 1.2   # jeda antar halaman
DELAY_DEPT = 1.5   # jeda antar departemen
DELAY_PT   = 2.0   # jeda ekstra pindah PT
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
# HTTP
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
            return BeautifulSoup(r.text, "lxml")
        except Exception as e:
            print(f"      [attempt {attempt}/{retries}] {e}")
            if attempt < retries:
                time.sleep(RETRY_WAIT)
    return None


# ---------------------------------------------------------------------------
# URL helper
# ---------------------------------------------------------------------------

def authors_url_from_profile(profile_url):
    """
    Konversi URL profil departemen → URL daftar author.
    /departments/profile/... → /departments/authors/...
    """
    return profile_url.replace("/departments/profile/", "/departments/authors/")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_num(text):
    if not text:
        return 0
    clean = re.sub(r"[^\d]", "", text.strip())
    return int(clean) if clean else 0


def parse_authors_page(soup):
    """Parse satu halaman daftar author. Return list of dict."""
    authors = []

    for card in soup.select("div.au-item"):
        author = {}

        # --- Nama & URL profil ---
        name_el = card.select_one("div.profile-name a")
        if name_el:
            author["nama"]      = name_el.get_text(strip=True)
            author["url_profil"] = name_el.get("href", "")
            # SINTA ID dari URL: /authors/profile/6103375
            m = re.search(r"/authors/profile/(\d+)", author["url_profil"])
            if m:
                author["sinta_id"] = m.group(1)

        # --- Foto ---
        img = card.select_one("img.avatar")
        if img:
            author["foto_url"] = img.get("src", "")

        # --- Nama departemen ---
        dept_el = card.select_one("div.profile-dept a")
        if dept_el:
            author["dept_nama"] = dept_el.get_text(strip=True)

        # --- H-Index ---
        hindex_spans = card.select("span.profile-id")
        for span in hindex_spans:
            text = span.get_text(strip=True)
            m = re.search(r"Scopus H-Index\s*:\s*(\d+)", text)
            if m:
                author["scopus_hindex"] = int(m.group(1))
            m = re.search(r"GS H-Index\s*:\s*(\d+)", text)
            if m:
                author["gs_hindex"] = int(m.group(1))

        # --- Score cards (stat-num / stat-text pair) ---
        stat_nums  = card.select("div.stat-num")
        stat_texts = card.select("div.stat-text")
        score_map = {
            "sinta score 3yr": "sinta_score_3yr",
            "sinta score":     "sinta_score",
            "affil score 3yr": "affil_score_3yr",
            "affil score":     "affil_score",
        }
        for num_el, txt_el in zip(stat_nums, stat_texts):
            lbl = txt_el.get_text(strip=True).lower()
            key = score_map.get(lbl)
            if key:
                author[key] = _parse_num(num_el.get_text(strip=True))

        if author.get("nama"):
            authors.append(author)

    return authors


def has_next_page(soup, current_page):
    for li in soup.select("ul.pagination li.page-item a.page-link"):
        text = li.get_text(strip=True)
        if re.fullmatch(r"\d+", text) and int(text) > current_page:
            return True
    return False


def scrape_dept_authors(session, authors_url):
    """Scrape semua halaman author list untuk satu departemen."""
    all_authors = []
    page = 1

    while True:
        url = authors_url if page == 1 else f"{authors_url}?page={page}"
        soup = fetch(session, url)

        if soup is None:
            print(f"      ERROR halaman {page}")
            break

        page_authors = parse_authors_page(soup)
        if not page_authors:
            break

        all_authors.extend(page_authors)

        if has_next_page(soup, page):
            page += 1
            time.sleep(DELAY)
        else:
            break

    return all_authors


# ---------------------------------------------------------------------------
# Load dept list
# ---------------------------------------------------------------------------

def load_dept_list(filter_kode=None):
    folders = sorted([d for d in DEPT_DIR.iterdir() if d.is_dir()])
    if filter_kode:
        folders = [d for d in folders if d.name == filter_kode]

    items = []
    for folder in folders:
        f = folder / "departments.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text())
        kode_pt = data.get("kode_pt", folder.name)
        for dept in data.get("departments", []):
            kode_dept = dept.get("kode_dept", "")
            url       = dept.get("url_profil", "")
            if url and kode_dept:
                items.append((kode_pt, kode_dept, url))
    return items


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def cmd_status():
    folders = sorted([d for d in DEPT_DIR.iterdir() if d.is_dir()])
    total_files  = sum(len(list(d.glob("*_author_list.json"))) for d in folders)
    total_depts  = sum(
        len(json.loads((d / "departments.json").read_text()).get("departments", []))
        for d in folders if (d / "departments.json").exists()
    )
    total_authors = 0
    for f in DEPT_DIR.glob("*/*_author_list.json"):
        try:
            data = json.loads(f.read_text())
            total_authors += len(data.get("authors", []))
        except Exception:
            pass
    print(f"Total folder PT  : {len(folders)}")
    print(f"Total departemen : {total_depts}")
    print(f"Author list file : {total_files}")
    print(f"Total authors    : {total_authors}")
    print(f"Sisa             : {total_depts - total_files}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scraper Author List per Departemen SINTA")
    parser.add_argument("--kode",   help="Filter kode PT (e.g. 061008)")
    parser.add_argument("--limit",  type=int, help="Maksimum jumlah dept")
    parser.add_argument("--force",  action="store_true", help="Overwrite file yang sudah ada")
    parser.add_argument("--status", action="store_true", help="Tampilkan ringkasan")
    args = parser.parse_args()

    if args.status:
        cmd_status()
        return

    items = load_dept_list(filter_kode=args.kode)
    if not items:
        print("Tidak ada departemen ditemukan.")
        return

    if args.limit:
        items = items[:args.limit]

    session  = make_session()
    done = skip = error = 0
    total = len(items)
    prev_pt  = None

    for idx, (kode_pt, kode_dept, profile_url) in enumerate(items, 1):
        out_file = DEPT_DIR / kode_pt / f"{kode_pt}_{kode_dept}_author_list.json"

        if out_file.exists() and not args.force:
            skip += 1
            continue

        if prev_pt and prev_pt != kode_pt:
            time.sleep(DELAY_PT)
        prev_pt = kode_pt

        authors_url = authors_url_from_profile(profile_url)
        print(f"[{idx}/{total}] {kode_pt}/{kode_dept} ...", end=" ", flush=True)

        authors = scrape_dept_authors(session, authors_url)

        result = {
            "kode_pt":          kode_pt,
            "kode_dept":        kode_dept,
            "url_authors":      authors_url,
            "jumlah_authors":   len(authors),
            "authors":          authors,
        }

        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"{len(authors)} authors")
        done += 1

        if idx < total:
            time.sleep(DELAY_DEPT)

    print(f"\nSelesai: {done} di-scrape, {skip} dilewati, {error} error.")


if __name__ == "__main__":
    main()
