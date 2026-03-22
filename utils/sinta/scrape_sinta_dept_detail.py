"""
Scraper SINTA — Detail per Departemen (Program Studi)

Sumber data:
  https://sinta.kemdiktisaintek.go.id/departments/profile/{sinta_id_pt}/{uuid1}/{uuid2}

Data yang diambil:
  - 4 SINTA Score : overall, 3yr, productivity_overall, productivity_3yr
  - Jumlah authors
  - Statistik publikasi : scopus/gscholar/wos × artikel + sitasi
  - Distribusi kuartil Scopus : Q1, Q2, Q3, Q4, No-Q
  - Research breakdown     : conference, articles, others
  - Trend Scopus tahunan   : list {tahun, jumlah}

Input  : utils/sinta/outs/departments/{kode_pt}/departments.json
         → field url_profil & kode_dept per departemen

Output : utils/sinta/outs/departments/{kode_pt}/{kode_pt}_{kode_dept}_deptdetail.json

Usage:
  # Scrape semua (resumable)
  python utils/sinta/scrape_sinta_dept_detail.py

  # Filter satu PT
  python utils/sinta/scrape_sinta_dept_detail.py --kode 061008

  # Paksa re-scrape
  python utils/sinta/scrape_sinta_dept_detail.py --force

  # Ringkasan output yang sudah ada
  python utils/sinta/scrape_sinta_dept_detail.py --status

  # Limit total request (testing)
  python utils/sinta/scrape_sinta_dept_detail.py --limit 10
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

BASE_DIR   = Path(__file__).resolve().parents[2]
DEPT_DIR   = Path(__file__).parent / "outs" / "departments"

SINTA_BASE = "https://sinta.kemdiktisaintek.go.id"

DELAY      = 1.5   # jeda antar request (detik)
DELAY_PT   = 2.0   # jeda ekstra setelah selesai satu PT
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
            print(f"    [attempt {attempt}/{retries}] {e}")
            if attempt < retries:
                time.sleep(RETRY_WAIT)
    return None, None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_num(text):
    """'1.318' → 1318  |  '12,717' → 12717  |  '0' → 0"""
    if not text:
        return 0
    clean = text.strip().replace(".", "").replace(",", "")
    try:
        return int(clean)
    except ValueError:
        return 0


def _extract_echarts_series(raw_text, chart_id):
    """
    Ekstrak blok JS ECharts dari getElementById('{chart_id}') call.
    Mengambil 10 KB setelah posisi init call agar mencakup semua option data.
    """
    # Cari JS init call: getElementById('scopus-chart-articles')
    target = f"getElementById('{chart_id}')"
    idx = raw_text.find(target)
    if idx == -1:
        target = f'getElementById("{chart_id}")'
        idx = raw_text.find(target)
    if idx == -1:
        return None

    # Ambil blok JS dari init call + 10 KB ke depan
    return raw_text[max(0, idx - 50): idx + 10000]


def _parse_echarts_array(snippet, key):
    """
    Ambil nilai array dari blok JS: key: ['a','b',...] atau key: [1,2,...]
    Mendukung format multiline (tiap nilai di baris berbeda).
    """
    # Temukan key: diikuti [...]
    m = re.search(rf"{re.escape(key)}\s*:\s*(\[[\s\S]*?\])\s*[,}}]", snippet)
    if not m:
        return None
    raw = m.group(1)
    # Normalisasi whitespace, lalu parse sebagai JSON
    raw_clean = re.sub(r"\s+", " ", raw)
    raw_clean = raw_clean.replace("'", '"')
    try:
        return json.loads(raw_clean)
    except Exception:
        return None


def _parse_quartile_pie(raw_text):
    """Ekstrak distribusi kuartil dari ECharts #quartile-pie."""
    snippet = _extract_echarts_series(raw_text, "quartile-pie")
    if not snippet:
        return {}

    result = {}
    # Pola multiline: { value: 31,\n  name: 'Q1' }
    for m in re.finditer(
        r"value:\s*(\d+)[\s\S]*?name:\s*['\"]([^'\"]+)['\"]",
        snippet
    ):
        val, name = int(m.group(1)), m.group(2).strip()
        result[name] = val
    return result


def _parse_research_radar(raw_text):
    """Ekstrak research breakdown dari ECharts #research-radar."""
    snippet = _extract_echarts_series(raw_text, "research-radar")
    if not snippet:
        return {}

    # indicator names (dalam radar.indicator array)
    names = re.findall(r"name:\s*['\"]([A-Za-z][^'\"]*)['\"]", snippet)
    # series data values: value: [74, 5, 1]
    val_m = re.search(r"value:\s*\[([\d\s,]+)\]", snippet)
    if not val_m:
        return {}

    vals = [int(v.strip()) for v in val_m.group(1).split(",") if v.strip().isdigit()]

    result = {}
    for n, v in zip(names, vals):
        key = n.lower().replace(" ", "_")
        result[key] = v
    return result


def _parse_scopus_trend(raw_text):
    """Ekstrak trend publikasi Scopus per tahun dari ECharts #scopus-chart-articles."""
    snippet = _extract_echarts_series(raw_text, "scopus-chart-articles")
    if not snippet:
        return []

    # Cari dua occurrences of "data:" → pertama = xAxis years, kedua = series values
    data_positions = [m.start() for m in re.finditer(r"\bdata\s*:", snippet)]
    if len(data_positions) < 2:
        return []

    def _extract_array_at(text, pos):
        """Ekstrak array [...] mulai dari pos, scan sampai bracket menutup."""
        start = text.find("[", pos)
        if start == -1:
            return None
        depth = 0
        for i in range(start, min(start + 5000, len(text))):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    return text[start: i + 1]
        return None

    # Array tahun (xAxis)
    years_raw = _extract_array_at(snippet, data_positions[0])
    # Array nilai (series)
    vals_raw  = _extract_array_at(snippet, data_positions[1])

    if not years_raw or not vals_raw:
        return []

    try:
        # Hapus trailing comma sebelum ] , lalu parse
        def _clean_arr(s):
            s = re.sub(r"\s+", "", s).replace("'", '"')
            s = re.sub(r",\]", "]", s)   # trailing comma
            return json.loads(s)

        years = _clean_arr(years_raw)
        vals  = [int(v) for v in re.findall(r"\d+", vals_raw)]
    except Exception:
        return []

    if len(years) != len(vals):
        return []

    return [{"tahun": int(y), "jumlah": v} for y, v in zip(years, vals) if v > 0]


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_detail(soup, raw_text, url):
    result = {"url_detail": url}

    # --- SINTA Scores (pr-num / pr-txt) ---
    pr_nums = soup.find_all("div", class_="pr-num")
    pr_txts = soup.find_all("div", class_="pr-txt")
    score_map = {
        "sinta score overall":              "sinta_score_overall",
        "sinta score 3yr":                  "sinta_score_3year",
        "sinta score overall productivity": "sinta_score_productivity",
        "sinta score 3yr productivity":     "sinta_score_productivity_3year",
    }
    for num_el, txt_el in zip(pr_nums, pr_txts):
        lbl = txt_el.get_text(strip=True).lower()
        key = score_map.get(lbl)
        if key:
            result[key] = _parse_num(num_el.get_text(strip=True))

    # --- Jumlah authors (stat-num / stat-text) ---
    stat_nums  = soup.find_all("div", class_="stat-num")
    stat_texts = soup.find_all("div", class_="stat-text")
    for num_el, txt_el in zip(stat_nums, stat_texts):
        lbl = txt_el.get_text(strip=True).lower()
        if "author" in lbl:
            result["jumlah_authors"] = _parse_num(num_el.get_text(strip=True))

    # --- Tabel statistik publikasi (.stat-table) ---
    # Header: Scopus (text-warning), GScholar (text-success), WOS (text-primary)
    # Baris : Article, Citation
    tbl = soup.find("table", class_="stat-table")
    if tbl:
        headers = []
        for th in tbl.find_all("th"):
            cls = " ".join(th.get("class", []))
            if "text-warning" in cls:
                headers.append("scopus")
            elif "text-success" in cls:
                headers.append("gscholar")
            elif "text-primary" in cls:
                headers.append("wos")

        for tr in tbl.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            row_label = tds[0].get_text(strip=True).lower()
            if "article" in row_label or "document" in row_label:
                for src, td in zip(headers, tds[1:]):
                    result[f"{src}_artikel"] = _parse_num(td.get_text(strip=True))
            elif "citation" in row_label:
                for src, td in zip(headers, tds[1:]):
                    result[f"{src}_sitasi"] = _parse_num(td.get_text(strip=True))

    # --- Distribusi kuartil Scopus (ECharts pie) ---
    quartile = _parse_quartile_pie(raw_text)
    if quartile:
        result["scopus_q1"]  = quartile.get("Q1", 0)
        result["scopus_q2"]  = quartile.get("Q2", 0)
        result["scopus_q3"]  = quartile.get("Q3", 0)
        result["scopus_q4"]  = quartile.get("Q4", 0)
        result["scopus_noq"] = quartile.get("No-Q", 0)

    # --- Research breakdown (ECharts radar) ---
    radar = _parse_research_radar(raw_text)
    if radar:
        result["research_conference"] = radar.get("conference", 0)
        result["research_articles"]   = radar.get("articles", 0)
        result["research_others"]     = radar.get("others", 0)

    # --- Trend Scopus tahunan ---
    trend = _parse_scopus_trend(raw_text)
    if trend:
        result["trend_scopus"] = trend

    return result


# ---------------------------------------------------------------------------
# Load dept list dari folder output
# ---------------------------------------------------------------------------

def load_dept_list(filter_kode=None):
    """
    Baca semua departments.json dan kembalikan list:
    (kode_pt, kode_dept, url_profil)
    """
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
    total_files = sum(len(list(d.glob("*_deptdetail.json"))) for d in folders)
    total_depts = sum(
        len(json.loads((d / "departments.json").read_text()).get("departments", []))
        for d in folders if (d / "departments.json").exists()
    )
    print(f"Total folder PT : {len(folders)}")
    print(f"Total departemen: {total_depts}")
    print(f"Detail terscrape: {total_files}")
    print(f"Sisa            : {total_depts - total_files}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scraper Detail Departemen SINTA")
    parser.add_argument("--kode",   help="Filter kode PT (e.g. 061008)")
    parser.add_argument("--limit",  type=int, help="Maksimum jumlah dept yang di-scrape")
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

    session = make_session()
    done = skip = error = 0
    total = len(items)
    prev_kode_pt = None

    for idx, (kode_pt, kode_dept, url) in enumerate(items, 1):
        out_file = DEPT_DIR / kode_pt / f"{kode_pt}_{kode_dept}_deptdetail.json"

        if out_file.exists() and not args.force:
            skip += 1
            continue

        # Jeda ekstra saat pindah PT
        if prev_kode_pt and prev_kode_pt != kode_pt:
            time.sleep(DELAY_PT)
        prev_kode_pt = kode_pt

        print(f"[{idx}/{total}] {kode_pt}/{kode_dept} ...", end=" ", flush=True)

        soup, raw = fetch(session, url)
        if soup is None:
            print("ERROR")
            error += 1
            continue

        detail = parse_detail(soup, raw, url)
        detail["kode_pt"]   = kode_pt
        detail["kode_dept"] = kode_dept

        out_file.write_text(json.dumps(detail, ensure_ascii=False, indent=2))
        print(f"OK  score={detail.get('sinta_score_overall',0):,}  "
              f"scopus={detail.get('scopus_artikel',0)}")
        done += 1

        if idx < total:
            time.sleep(DELAY)

    print(f"\nSelesai: {done} di-scrape, {skip} dilewati, {error} error.")
    print(f"Output : {DEPT_DIR}")


if __name__ == "__main__":
    main()
