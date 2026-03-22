"""
Scraper SINTA — Daftar Departemen (Program Studi) per Afiliasi PT

Sumber data:
  https://sinta.kemdiktisaintek.go.id/affiliations/departments/{sinta_id}/{kode_pt}

Data yang diambil per departemen:
  - nama                : nama departemen/program studi
  - jenjang             : jenjang pendidikan (S1, S2, S3, D3, D4, dll.)
  - kode_dept           : kode numerik departemen di SINTA
  - url_profil          : URL profil departemen di SINTA
  - sinta_score_overall : SINTA Score Overall departemen
  - sinta_score_3year   : SINTA Score 3Yr departemen
  - jumlah_authors      : total jumlah anggota dosen/peneliti

HTML selectors kunci:
  div.row.d-item              → setiap baris departemen
  div.tbl-content-meta span   → jenjang (S1/S2/S3/D3)
  div.tbl-content-name > a    → nama + URL profil (UUID-based)
  div.tbl-content-meta-num    → kode numerik departemen
  span.profile-id.text-warning → "SINTA Score Overall : XXXXX"
  span.profile-id.text-success → "SINTA Score 3Yr : XXXXX"
  li.au-more > a               → "+ N more Authors" (jumlah tambahan)
  ul.au-list.dept-list > li (non .au-more) → preview authors (jumlah awal)

Pagination:
  URL + ?page=N  (loop sampai tidak ada data baru)

Input  : Database Django → semua SintaAfiliasi (sinta_id + sinta_kode)
Output : utils/sinta/outs/departments/{kode_pt}_departments.json

Usage:
  # Scrape semua PT (resumable — skip jika file sudah ada)
  python utils/sinta/scrape_sinta_departments.py

  # Filter satu PT saja (testing)
  python utils/sinta/scrape_sinta_departments.py --kode 061008

  # Limit jumlah PT
  python utils/sinta/scrape_sinta_departments.py --limit 5

  # Paksa re-scrape (overwrite file yang sudah ada)
  python utils/sinta/scrape_sinta_departments.py --force

  # Tampilkan ringkasan output yang sudah ada
  python utils/sinta/scrape_sinta_departments.py --status
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR    = Path(__file__).resolve().parents[2]          # chifoo_backend/
OUTPUT_DIR  = Path(__file__).parent / "outs" / "departments"

SINTA_BASE  = "https://sinta.kemdiktisaintek.go.id"
DEPT_URL    = SINTA_BASE + "/affiliations/departments/{sinta_id}/{kode_pt}"

DELAY_PAGE  = 1.5   # jeda antar halaman (detik)
DELAY_PT    = 2.5   # jeda antar PT (detik)
TIMEOUT     = 30    # timeout request (detik)
RETRY       = 4     # jumlah retry
RETRY_WAIT  = 8     # jeda antar retry (detik)

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
    """GET url, kembalikan BeautifulSoup atau None jika gagal."""
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return BeautifulSoup(r.text, "lxml")
        except Exception as e:
            print(f"  [attempt {attempt}/{retries}] {url}: {e}")
            if attempt < retries:
                time.sleep(RETRY_WAIT)
    return None


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_number(text):
    """'1.318.091' atau '117,66' → int/float. Return 0 jika gagal."""
    if not text:
        return 0
    clean = text.strip().replace(".", "").replace(",", ".")
    try:
        v = float(clean)
        return int(v) if v == int(v) else v
    except ValueError:
        return 0


def _extract_score(span_el):
    """Ekstrak angka dari teks 'SINTA Score Overall : 31161' → 31161."""
    if not span_el:
        return 0
    m = re.search(r":\s*([\d.,]+)", span_el.get_text())
    return _parse_number(m.group(1)) if m else 0


def parse_departments_page(soup):
    """
    Parse satu halaman daftar departemen.
    Return list of dict.
    """
    departments = []

    for row in soup.select("div.row.d-item"):
        dept = {}

        # --- Jenjang (S1/S2/S3/D3 dll.) ---
        meta_div = row.select_one("div.tbl-content-meta")
        if meta_div:
            span = meta_div.find("span")
            if span:
                dept["jenjang"] = span.get_text(strip=True).upper()

        # --- Nama & URL profil ---
        name_div = row.select_one("div.tbl-content-name")
        if name_div:
            a = name_div.find("a", href=True)
            if a:
                dept["nama"]      = a.get_text(strip=True)
                dept["url_profil"] = a["href"]

        # --- SINTA Score Overall & 3Yr ---
        dept["sinta_score_overall"] = _extract_score(
            row.select_one("span.profile-id.text-warning")
        )
        dept["sinta_score_3year"] = _extract_score(
            row.select_one("span.profile-id.text-success")
        )

        # --- Kode departemen numerik ---
        kode_el = row.select_one("div.tbl-content-meta-num")
        if kode_el:
            dept["kode_dept"] = kode_el.get_text(strip=True)

        # --- Jumlah authors ---
        # Preview authors: semua <li> di au-list.dept-list kecuali li.au-more
        preview_count = 0
        extra_count   = 0

        dept_list = row.select_one("ul.au-list.dept-list")
        if dept_list:
            for li in dept_list.find_all("li"):
                if "au-more" in li.get("class", []):
                    # Teks: "+ 11 more Authors"
                    m = re.search(r"[+\s]*(\d+)", li.get_text())
                    if m:
                        extra_count = int(m.group(1))
                else:
                    preview_count += 1

        dept["jumlah_authors"] = preview_count + extra_count

        if dept.get("nama"):
            departments.append(dept)

    return departments


def has_next_page(soup, current_page):
    """Return True jika ada halaman berikutnya."""
    for li in soup.select("ul.pagination li.page-item a.page-link"):
        text = li.get_text(strip=True)
        # Ada link page yang lebih besar dari current
        if re.fullmatch(r"\d+", text) and int(text) > current_page:
            return True
    return False


# ---------------------------------------------------------------------------
# Scrape satu PT
# ---------------------------------------------------------------------------

def scrape_pt_departments(session, sinta_id, kode_pt):
    """
    Scrape semua halaman departemen untuk satu PT.
    Return list of dept dicts.
    """
    all_depts = []
    page = 1

    while True:
        url = DEPT_URL.format(sinta_id=sinta_id, kode_pt=kode_pt)
        if page > 1:
            url += f"?page={page}"

        print(f"    halaman {page}: {url}")
        soup = fetch(session, url)

        if soup is None:
            print(f"  ERROR: gagal fetch halaman {page}")
            break

        depts = parse_departments_page(soup)
        if not depts:
            print(f"    halaman {page}: tidak ada departemen, berhenti.")
            break

        all_depts.extend(depts)
        print(f"    halaman {page}: {len(depts)} departemen ditemukan")

        if has_next_page(soup, page):
            page += 1
            time.sleep(DELAY_PAGE)
        else:
            break

    return all_depts


# ---------------------------------------------------------------------------
# Load daftar PT dari database
# ---------------------------------------------------------------------------

def load_pt_list_from_db():
    """
    Load sinta_id + sinta_kode dari tabel SintaAfiliasi di database Django.
    Return list of (sinta_id, kode_pt, nama) sorted by kode_pt.
    """
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")

    import django
    django.setup()

    from apps.universities.models import SintaAfiliasi

    qs = SintaAfiliasi.objects.exclude(sinta_id="").exclude(sinta_kode="") \
                               .values("sinta_id", "sinta_kode", "nama_sinta") \
                               .order_by("sinta_kode")
    return [(r["sinta_id"], r["sinta_kode"], r["nama_sinta"]) for r in qs]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def out_file_for(kode_pt):
    """Return path: outs/departments/{kode_pt}/departments.json"""
    return OUTPUT_DIR / kode_pt / "departments.json"


def cmd_status():
    folders = sorted([d for d in OUTPUT_DIR.iterdir() if d.is_dir()])
    if not folders:
        print("Belum ada folder output.")
        return

    total_depts = 0
    print(f"{'Kode PT':<10} {'Jumlah Dept':>12}")
    print("-" * 40)
    for d in folders:
        f = d / "departments.json"
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text())
            n = len(data.get("departments", []))
            total_depts += n
            print(f"  {d.name:<10} {n:>10}")
        except Exception as e:
            print(f"  {d.name}: ERROR {e}")
    print("-" * 40)
    print(f"  Total: {len(folders)} PT, {total_depts} departemen")


def main():
    parser = argparse.ArgumentParser(description="Scraper SINTA Departments")
    parser.add_argument("--kode",  help="Filter kode PT tertentu saja (e.g. 061008)")
    parser.add_argument("--limit", type=int, help="Maksimum jumlah PT yang di-scrape")
    parser.add_argument("--force", action="store_true", help="Overwrite file yang sudah ada")
    parser.add_argument("--status", action="store_true", help="Tampilkan ringkasan output")
    args = parser.parse_args()

    if args.status:
        cmd_status()
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading daftar PT dari database...")
    pt_list = load_pt_list_from_db()
    print(f"  {len(pt_list)} PT ditemukan di database.\n")

    if args.kode:
        pt_list = [p for p in pt_list if p[1] == args.kode]
        if not pt_list:
            print(f"Kode PT '{args.kode}' tidak ditemukan di database.")
            return

    if args.limit:
        pt_list = pt_list[:args.limit]

    session = make_session()
    done = skip = error = 0

    for idx, (sinta_id, kode_pt, nama) in enumerate(pt_list, 1):
        out_file = out_file_for(kode_pt)

        if out_file.exists() and not args.force:
            print(f"[{idx}/{len(pt_list)}] SKIP {kode_pt} ({nama}) — file sudah ada")
            skip += 1
            continue

        print(f"[{idx}/{len(pt_list)}] {kode_pt} — {nama} (SINTA ID: {sinta_id})")

        depts = scrape_pt_departments(session, sinta_id, kode_pt)

        result = {
            "sinta_id_afiliasi": sinta_id,
            "kode_pt": kode_pt,
            "nama_pt": nama,
            "jumlah_departments": len(depts),
            "departments": depts,
        }

        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"  → {len(depts)} departemen disimpan ke {kode_pt}/departments.json\n")
        done += 1

        if idx < len(pt_list):
            time.sleep(DELAY_PT)

    print(f"\nSelesai: {done} di-scrape, {skip} dilewati, {error} error.")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
