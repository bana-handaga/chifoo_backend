"""
Scraper SINTA — Jurnal per Afiliasi PT

Sumber data:
  Halaman listing : /journals/index/{sinta_id}?page={n}

Data yang diambil per jurnal:
  - sinta_id, nama, p_issn, e_issn
  - akreditasi (S1–S6)
  - subject_area, afiliasi_teks
  - impact, h5_index, sitasi_5yr, sitasi_total
  - is_scopus, is_garuda
  - url_website, url_scholar, url_editor, url_garuda
  - logo_base64 (dari Google Scholar, jika tersedia)

Prasyarat:
  Data profil afiliasi sudah ada di utils/sinta/outs/affprofile/

Input  : utils/sinta/outs/affprofile/*_sinta_afiliasi.json
Output : utils/sinta/outs/journals/{kode_pt}_journals.json

Usage:
  cd chifoo_backend
  python utils/sinta/scrape_sinta_journals.py
  python utils/sinta/scrape_sinta_journals.py --kode 061008
  python utils/sinta/scrape_sinta_journals.py --limit 5
  python utils/sinta/scrape_sinta_journals.py --no-logo
  python utils/sinta/scrape_sinta_journals.py --status
"""

import argparse
import base64
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
JOURNALS_DIR = Path(__file__).parent / "outs" / "journals"

SINTA_BASE    = "https://sinta.kemdiktisaintek.go.id"
JOURNALS_URL  = SINTA_BASE + "/journals/index/{sinta_id}"
SCHOLAR_LOGO  = "https://scholar.googleusercontent.com/citations?view_op=medium_photo&user={user}&citpid=2"

DELAY_PAGE   = 1.5   # antar halaman listing
DELAY_LOGO   = 1.0   # antar download logo
TIMEOUT      = 30
RETRY        = 3
RETRY_WAIT   = 6

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id,en-US;q=0.7,en;q=0.3",
    "Referer":         SINTA_BASE,
}

LOGO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Accept":  "image/avif,image/webp,*/*",
    "Referer": "https://scholar.google.com/",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_html(session, url, retries=RETRY):
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


def fetch_logo(session, scholar_user):
    """Download logo dari Google Scholar → data URI base64. Return '' jika gagal."""
    if not scholar_user:
        return ""
    url = SCHOLAR_LOGO.format(user=scholar_user)
    for attempt in range(1, RETRY + 1):
        try:
            r = session.get(url, headers=LOGO_HEADERS, timeout=TIMEOUT)
            if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                mime = r.headers["content-type"].split(";")[0].strip()
                b64  = base64.b64encode(r.content).decode()
                return f"data:{mime};base64,{b64}"
            return ""
        except Exception as e:
            if attempt < RETRY:
                time.sleep(RETRY_WAIT)
    return ""


# ---------------------------------------------------------------------------
# Parse angka format Indonesia → float/int
# ---------------------------------------------------------------------------

def parse_num(text):
    """'3.632' → 3632 | '4,68' → 4.68 | '0,00' → 0.0"""
    clean = text.strip().replace("\xa0", "")
    if not clean or clean == "-":
        return 0.0
    if "," in clean and "." in clean:
        # Format Indonesia: 1.234,56
        clean = clean.replace(".", "").replace(",", ".")
    elif "," in clean:
        # Desimal koma: 4,68
        clean = clean.replace(",", ".")
    elif "." in clean:
        # Ribuan titik: 3.632 → cek posisi titik
        dot_pos = clean.rfind(".")
        if len(clean) - dot_pos - 1 == 3:
            # Titik ribuan, bukan desimal
            clean = clean.replace(".", "")
    try:
        return float(clean)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Parse satu halaman listing
# ---------------------------------------------------------------------------

def parse_page(soup):
    """Parse semua jurnal dari satu halaman. Return list of dict."""
    journals = []

    for item in soup.select("div.list-item"):
        j = {
            "sinta_id":     0,
            "nama":         "",
            "p_issn":       "",
            "e_issn":       "",
            "akreditasi":   "",
            "subject_area": "",
            "afiliasi_teks":"",
            "impact":       0.0,
            "h5_index":     0,
            "sitasi_5yr":   0,
            "sitasi_total": 0,
            "is_scopus":    False,
            "is_garuda":    False,
            "url_website":  "",
            "url_scholar":  "",
            "url_editor":   "",
            "url_garuda":   "",
            "scholar_user": "",   # untuk fetch logo, dihapus dari output final
            "logo_base64":  "",
        }

        # --- sinta_id + nama ---
        link = item.select_one("div.affil-name a")
        if link:
            j["nama"] = link.get_text(strip=True)
            m = re.search(r"/journals/profile/(\d+)", link.get("href", ""))
            if m:
                j["sinta_id"] = int(m.group(1))

        # --- scholar_user dari class div logo ---
        logo_div = item.select_one("div.pr-top.text-center")
        if logo_div:
            classes = [c for c in logo_div.get("class", [])
                       if c not in ("pr-top", "text-center") and len(c) >= 6]
            if classes:
                j["scholar_user"] = classes[0]

        # --- URLs (affil-abbrev links) ---
        abbrev = item.select_one("div.affil-abbrev")
        if abbrev:
            for a in abbrev.find_all("a", href=True):
                href = a["href"]
                if href in ("#!", ""):
                    continue
                icon = a.find("i")
                icon_class = " ".join(icon.get("class", [])) if icon else ""
                if "zmdi-label" in icon_class:
                    j["url_scholar"] = href
                    # Ekstrak user ID dari URL scholar
                    m2 = re.search(r"user=([A-Za-z0-9_-]+)", href)
                    if m2:
                        j["scholar_user"] = m2.group(1)
                elif "el-globe-alt" in icon_class:
                    j["url_editor"] = href
                elif "el-globe" in icon_class:
                    j["url_website"] = href

        # --- afiliasi_teks ---
        loc = item.select_one("div.affil-loc a")
        if loc:
            j["afiliasi_teks"] = loc.get_text(strip=True)

        # --- P-ISSN / E-ISSN / Subject Area ---
        profile_id = item.select_one("div.profile-id")
        if profile_id:
            pid_text = profile_id.get_text(" ", strip=True)
            m_p = re.search(r"P-ISSN\s*:\s*(\S+)", pid_text)
            m_e = re.search(r"E-ISSN\s*:\s*(\S+)", pid_text)
            m_s = re.search(r"Subject Area\s*:\s*(.+?)(?:\s*\||\s*$)", pid_text)
            if m_p: j["p_issn"]       = m_p.group(1).strip()
            if m_e: j["e_issn"]       = m_e.group(1).strip()
            if m_s: j["subject_area"] = m_s.group(1).strip()

        # --- Akreditasi ---
        accr = item.select_one("span.num-stat.accredited")
        if accr:
            m_a = re.search(r"S[1-6]", accr.get_text())
            if m_a:
                j["akreditasi"] = m_a.group(0)

        # --- is_scopus ---
        if item.select_one("span.scopus-indexed"):
            j["is_scopus"] = True

        # --- is_garuda + url_garuda ---
        garuda_a = item.select_one("a span.garuda-indexed")
        if garuda_a:
            j["is_garuda"] = True
            parent_a = garuda_a.find_parent("a")
            if parent_a:
                j["url_garuda"] = parent_a.get("href", "")

        # --- Statistik (4 pr-num dalam urutan: impact, h5, sitasi5yr, sitasi_total) ---
        nums = [parse_num(d.get_text()) for d in item.select("div.pr-num")]
        if len(nums) >= 4:
            j["impact"]      = nums[0]
            j["h5_index"]    = int(nums[1])
            j["sitasi_5yr"]  = int(nums[2])
            j["sitasi_total"]= int(nums[3])

        journals.append(j)

    return journals


# ---------------------------------------------------------------------------
# Scrape satu PT (semua halaman)
# ---------------------------------------------------------------------------

def get_total_pages(soup):
    """Ambil jumlah halaman dari pagination."""
    pagination_text = soup.select_one("div.pagination-text small")
    if pagination_text:
        m = re.search(r"Page \d+ of (\d+)", pagination_text.get_text())
        if m:
            return int(m.group(1))
    # Fallback: hitung dari link pagination
    pages = soup.select("ul.pagination li a.page-link")
    nums = []
    for p in pages:
        t = p.get_text(strip=True)
        if t.isdigit():
            nums.append(int(t))
    return max(nums) if nums else 1


def scrape_journals(session, kode, sinta_id, nama, fetch_logos=True):
    """Scrape semua jurnal untuk satu PT. Return dict."""
    base_url = JOURNALS_URL.format(sinta_id=sinta_id)

    # Halaman pertama
    soup = fetch_html(session, base_url + "?page=1")
    if soup is None:
        return None

    total_pages = get_total_pages(soup)
    all_journals = parse_page(soup)

    # Halaman berikutnya
    for page in range(2, total_pages + 1):
        time.sleep(DELAY_PAGE)
        soup = fetch_html(session, f"{base_url}?page={page}")
        if soup:
            all_journals.extend(parse_page(soup))

    # Download logo
    if fetch_logos:
        for j in all_journals:
            user = j.get("scholar_user", "")
            if user:
                j["logo_base64"] = fetch_logo(session, user)
                time.sleep(DELAY_LOGO)
            del j["scholar_user"]
    else:
        for j in all_journals:
            j.pop("scholar_user", None)

    return {
        "kode_pt":      kode,
        "sinta_id_pt":  sinta_id,
        "nama_pt":      nama,
        "total_journals": len(all_journals),
        "journals":     all_journals,
        "scraped_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Load daftar PT
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
# Status
# ---------------------------------------------------------------------------

def print_status(journals_dir):
    files = list(journals_dir.glob("*_journals.json"))
    total_j = 0
    with_logo = 0
    akr = {}
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        for j in d.get("journals", []):
            total_j += 1
            if j.get("logo_base64"):
                with_logo += 1
            a = j.get("akreditasi", "")
            if a:
                akr[a] = akr.get(a, 0) + 1
    print(f"\n{'='*50}")
    print(f"  PT tersimpan : {len(files)}")
    print(f"  Total jurnal : {total_j}")
    print(f"  Dengan logo  : {with_logo}")
    for k in sorted(akr):
        print(f"  {k:<5}: {akr[k]}")
    print(f"  Output dir   : {journals_dir}")
    print(f"{'='*50}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape jurnal SINTA per PT",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--kode",    default="", help="Filter satu PT (e.g. 061008)")
    parser.add_argument("--limit",   type=int, default=0, help="Batasi jumlah PT")
    parser.add_argument("--no-logo", action="store_true", help="Skip download logo")
    parser.add_argument("--status",  action="store_true", help="Tampilkan ringkasan")
    args = parser.parse_args()

    JOURNALS_DIR.mkdir(parents=True, exist_ok=True)

    if args.status:
        print_status(JOURNALS_DIR)
        return

    pt_list = load_pt_list()
    print(f"Total PT dari affprofile: {len(pt_list)}")

    if args.kode:
        pt_list = [p for p in pt_list if p["kode"] == args.kode]
        if not pt_list:
            print(f"Kode '{args.kode}' tidak ditemukan")
            return

    if args.limit:
        pt_list = pt_list[:args.limit]

    session   = make_session()
    done = skipped = no_sinta = errors = 0

    for i, pt in enumerate(pt_list, 1):
        kode     = pt["kode"]
        sinta_id = pt["sinta_id"]
        nama     = pt["nama"]

        if not sinta_id:
            print(f"[{i}/{len(pt_list)}] SKIP {kode}: tidak ada sinta_id")
            no_sinta += 1
            continue

        out_file = JOURNALS_DIR / f"{kode}_journals.json"
        if out_file.exists() and not args.kode:
            print(f"[{i}/{len(pt_list)}] Skip: {kode} {nama}")
            skipped += 1
            continue

        print(f"\n[{i}/{len(pt_list)}] {kode} — {nama}  (sinta_id={sinta_id})")

        try:
            data = scrape_journals(session, kode, sinta_id, nama,
                                   fetch_logos=not args.no_logo)
            if data is None:
                print(f"  ERROR: fetch gagal")
                errors += 1
                continue

            n   = data["total_journals"]
            lgs = sum(1 for j in data["journals"] if j.get("logo_base64"))
            print(f"  Jurnal : {n} | Logo : {lgs}")

            # Distribusi akreditasi
            akr = {}
            for j in data["journals"]:
                a = j.get("akreditasi", "-")
                akr[a] = akr.get(a, 0) + 1
            print(f"  Akreditasi: {dict(sorted(akr.items()))}")

            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            done += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
            errors += 1

    print(f"\n=== Selesai ===")
    print(f"  Diproses : {done}")
    print(f"  Di-skip  : {skipped}")
    print(f"  No sinta : {no_sinta}")
    print(f"  Error    : {errors}")
    print_status(JOURNALS_DIR)


if __name__ == "__main__":
    main()
