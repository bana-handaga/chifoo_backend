"""
Scraper SINTA — Detail Author (profil + tren penelitian + tren pengabdian)

Sumber data (3 request per author):
  1. GET /authors/profile/{sinta_id}               → scores, stat-table, kuartil, radar, tren Scopus
  2. GET /authors/profile/{sinta_id}/?view=researches → tren penelitian per tahun
  3. GET /authors/profile/{sinta_id}/?view=services   → tren pengabdian per tahun

Data yang diambil:
  - Identitas   : nama, foto_url, afiliasi, departemen, bidang_keilmuan
  - SINTA Score : overall, 3yr, affil_score, affil_score_3yr
  - Statistik   : Scopus/GScholar/WOS × artikel, sitasi, cited_doc, h_index, i10_index, g_index
  - Kuartil     : Q1, Q2, Q3, Q4, No-Q (ECharts #quartile-pie)
  - Radar       : conference, articles, others (ECharts #research-radar)
  - Tren Scopus : per tahun (ECharts #scopus-chart-articles)
  - Tren Research: per tahun (ECharts #research-chart-articles)
  - Tren Service : per tahun (ECharts #service-chart-articles)

Input  : utils/sinta/outs/departments/*/ *_author_list.json
         → deduplikasi berdasarkan sinta_id → 17.861 author unik

Output : utils/sinta/outs/authors/{sinta_id}_authordetail.json

Usage:
  # Scrape semua (resumable, ~8-10 jam)
  python utils/sinta/scrape_sinta_author_detail.py

  # Limit untuk testing
  python utils/sinta/scrape_sinta_author_detail.py --limit 10

  # Paksa re-scrape
  python utils/sinta/scrape_sinta_author_detail.py --force

  # Ringkasan
  python utils/sinta/scrape_sinta_author_detail.py --status
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
OUT_DIR    = Path(__file__).parent / "outs" / "authors"
SINTA_BASE = "https://sinta.kemdiktisaintek.go.id"

DELAY       = 1.0   # jeda antar request dalam satu author (3 req × 1.0s = 3s/author)
DELAY_NEXT  = 0.8   # jeda sebelum author berikutnya
TIMEOUT     = 30
RETRY       = 4
RETRY_WAIT  = 8

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
            return BeautifulSoup(r.text, "lxml"), r.text
        except Exception as e:
            print(f"    [attempt {attempt}/{retries}] {e}")
            if attempt < retries:
                time.sleep(RETRY_WAIT)
    return None, None


# ---------------------------------------------------------------------------
# ECharts helpers (sama dengan scrape_sinta_dept_detail.py)
# ---------------------------------------------------------------------------

def _parse_num(text):
    if not text:
        return 0
    clean = re.sub(r"[^\d]", "", text.strip())
    return int(clean) if clean else 0


def _get_echarts_snippet(raw, chart_id):
    """Ambil blok JS dari getElementById('{chart_id}') + 10KB."""
    for quote in ("'", '"'):
        target = f"getElementById({quote}{chart_id}{quote})"
        idx = raw.find(target)
        if idx != -1:
            return raw[max(0, idx - 50): idx + 10000]
    return None


def _extract_array_at(text, pos):
    """Scan dari pos sampai menemukan '[...]' dengan bracket matching."""
    start = text.find("[", pos)
    if start == -1:
        return None
    depth = 0
    for i in range(start, min(start + 6000, len(text))):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return text[start: i + 1]
    return None


def _parse_trend_chart(raw, chart_id):
    """
    Ekstrak tren dari ECharts chart_id.
    Return list of {"tahun": int, "jumlah": int} (hanya jumlah > 0).
    """
    snippet = _get_echarts_snippet(raw, chart_id)
    if not snippet:
        return []

    data_positions = [m.start() for m in re.finditer(r"\bdata\s*:", snippet)]
    if len(data_positions) < 2:
        return []

    years_raw = _extract_array_at(snippet, data_positions[0])
    vals_raw  = _extract_array_at(snippet, data_positions[1])
    if not years_raw or not vals_raw:
        return []

    try:
        def _clean(s):
            s = re.sub(r"\s+", "", s).replace("'", '"')
            return json.loads(re.sub(r",\]", "]", s))

        years = _clean(years_raw)
        vals  = [int(v) for v in re.findall(r"\d+", vals_raw)]
    except Exception:
        return []

    if len(years) != len(vals):
        return []

    return [{"tahun": int(y), "jumlah": v} for y, v in zip(years, vals) if v > 0]


def _parse_quartile(raw):
    snippet = _get_echarts_snippet(raw, "quartile-pie")
    if not snippet:
        return {}
    result = {}
    for m in re.finditer(r"value:\s*(\d+)[\s\S]*?name:\s*['\"]([^'\"]+)['\"]", snippet):
        result[m.group(2).strip()] = int(m.group(1))
    return result


def _parse_radar(raw):
    snippet = _get_echarts_snippet(raw, "research-radar")
    if not snippet:
        return {}
    names = re.findall(r"name:\s*['\"]([A-Za-z][^'\"]*)['\"]", snippet)
    val_m = re.search(r"value:\s*\[([\d\s,]+)\]", snippet)
    if not val_m:
        return {}
    vals = [int(v.strip()) for v in val_m.group(1).split(",") if v.strip().isdigit()]
    return {n.lower().replace(" ", "_"): v for n, v in zip(names, vals)}


# ---------------------------------------------------------------------------
# Parser halaman default (articles view)
# ---------------------------------------------------------------------------

def parse_default_view(soup, raw):
    result = {}

    # --- Identitas ---
    h3 = soup.select_one("div.content-box h3 a")
    if h3:
        result["nama"] = h3.get_text(strip=True)

    img = soup.select_one("img.img-thumbnail.round-corner")
    if img:
        result["foto_url"] = img.get("src", "")

    # Afiliasi & departemen dari meta-profile
    meta_links = soup.select("div.meta-profile a")
    for a in meta_links:
        href = a.get("href", "")
        if "/affiliations/profile/" in href:
            result["afiliasi_url"]  = href
            m = re.search(r"/affiliations/profile/(\d+)", href)
            if m:
                result["sinta_id_pt"] = m.group(1)
        elif "/departments/profile/" in href:
            result["dept_url"] = href
            # Ekstrak kode dept numerik dari URL: /departments/profile/27/kode_pt/kode_dept
            m = re.search(r"/departments/profile/\d+/\w+/(\d+)$", href)
            if m:
                result["kode_dept"] = m.group(1)

    # Bidang keilmuan (subjects)
    subjects = [a.get_text(strip=True) for a in soup.select("ul.subject-list li a")]
    if subjects:
        result["bidang_keilmuan"] = subjects

    # --- SINTA Scores (pr-num / pr-txt) ---
    pr_nums = soup.find_all("div", class_="pr-num")
    pr_txts = soup.find_all("div", class_="pr-txt")
    score_map = {
        "sinta score overall": "sinta_score_overall",
        "sinta score 3yr":     "sinta_score_3year",
        "affil score":         "affil_score",
        "affil score 3yr":     "affil_score_3year",
    }
    for num_el, txt_el in zip(pr_nums, pr_txts):
        lbl = txt_el.get_text(strip=True).lower()
        key = score_map.get(lbl)
        if key:
            result[key] = _parse_num(num_el.get_text(strip=True))

    # --- Tabel statistik (stat-table): Article, Citation, Cited Doc, H-Index, i10-Index, G-Index ---
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

        row_map = {
            "article":      "artikel",
            "citation":     "sitasi",
            "cited document":"cited_doc",
            "h-index":      "h_index",
            "i10-index":    "i10_index",
            "g-index":      "g_index",
        }
        for tr in tbl.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            lbl = tds[0].get_text(strip=True).lower()
            suffix = row_map.get(lbl)
            if suffix:
                for src, td in zip(headers, tds[1:]):
                    result[f"{src}_{suffix}"] = _parse_num(td.get_text(strip=True))

    # --- ECharts ---
    quartile = _parse_quartile(raw)
    if quartile:
        result["scopus_q1"]  = quartile.get("Q1", 0)
        result["scopus_q2"]  = quartile.get("Q2", 0)
        result["scopus_q3"]  = quartile.get("Q3", 0)
        result["scopus_q4"]  = quartile.get("Q4", 0)
        result["scopus_noq"] = quartile.get("No-Q", 0)

    radar = _parse_radar(raw)
    if radar:
        result["research_conference"] = radar.get("conference", 0)
        result["research_articles"]   = radar.get("articles", 0)
        result["research_others"]     = radar.get("others", 0)

    trend_scopus = _parse_trend_chart(raw, "scopus-chart-articles")
    if trend_scopus:
        result["trend_scopus"] = trend_scopus

    return result


# ---------------------------------------------------------------------------
# Scrape satu author (3 request)
# ---------------------------------------------------------------------------

def scrape_author(session, sinta_id, url_profil):
    base_url = url_profil.rstrip("/")
    result   = {"sinta_id": sinta_id, "url_profil": url_profil}

    # Request 1: default view
    soup, raw = fetch(session, base_url)
    if soup:
        result.update(parse_default_view(soup, raw))
    else:
        result["error"] = "fetch gagal"
        return result

    time.sleep(DELAY)

    # Request 2: researches → trend penelitian
    soup2, raw2 = fetch(session, f"{base_url}/?view=researches")
    if soup2:
        trend_research = _parse_trend_chart(raw2, "research-chart-articles")
        if trend_research:
            result["trend_research"] = trend_research

    time.sleep(DELAY)

    # Request 3: services → trend pengabdian
    soup3, raw3 = fetch(session, f"{base_url}/?view=services")
    if soup3:
        trend_service = _parse_trend_chart(raw3, "service-chart-articles")
        if trend_service:
            result["trend_service"] = trend_service

    return result


# ---------------------------------------------------------------------------
# Build daftar author unik dari semua author_list files
# ---------------------------------------------------------------------------

def load_author_list():
    """
    Baca semua *_author_list.json, deduplikasi by sinta_id.
    Return list of (sinta_id, url_profil, kode_pt, kode_dept) sorted by sinta_id.
    """
    authors = {}  # sinta_id → (url_profil, kode_pt, kode_dept)
    for f in sorted(DEPT_DIR.glob("*/*_author_list.json")):
        try:
            data = json.loads(f.read_text())
            kode_pt   = data.get("kode_pt", "")
            kode_dept = data.get("kode_dept", "")
            for a in data.get("authors", []):
                sid = a.get("sinta_id", "")
                url = a.get("url_profil", "")
                if sid and url and sid not in authors:
                    authors[sid] = (url, kode_pt, kode_dept)
        except Exception:
            pass
    return sorted(
        [(sid, url, kpt, kdept) for sid, (url, kpt, kdept) in authors.items()],
        key=lambda x: x[0]
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def cmd_status():
    total_unique = len(load_author_list())
    done = len(list(OUT_DIR.glob("*/*/*.json")))
    print(f"Author unik   : {total_unique:,}")
    print(f"Sudah di-scrape: {done:,}")
    print(f"Sisa          : {total_unique - done:,}")
    if done > 0:
        remaining = total_unique - done
        est_hours = remaining * (DELAY * 2 + DELAY_NEXT + 0.5) / 3600
        print(f"Estimasi sisa : ~{est_hours:.1f} jam")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scraper Detail Author SINTA")
    parser.add_argument("--limit",  type=int, help="Maksimum jumlah author")
    parser.add_argument("--force",  action="store_true", help="Overwrite file yang ada")
    parser.add_argument("--status", action="store_true", help="Tampilkan ringkasan")
    args = parser.parse_args()

    if args.status:
        cmd_status()
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading daftar author unik...")
    author_list = load_author_list()
    print(f"  {len(author_list):,} author unik ditemukan.\n")

    if args.limit:
        author_list = author_list[:args.limit]

    session = make_session()
    done = skip = error = 0
    total = len(author_list)

    for idx, (sinta_id, url_profil, kode_pt, kode_dept) in enumerate(author_list, 1):
        out_dir  = OUT_DIR / (kode_pt or "_unknown") / (kode_dept or "_unknown")
        out_file = out_dir / f"{sinta_id}_authordetail.json"

        if out_file.exists() and not args.force:
            skip += 1
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{idx}/{total}] {sinta_id} ...", end=" ", flush=True)

        detail = scrape_author(session, sinta_id, url_profil)

        if detail.get("error"):
            print(f"ERROR: {detail['error']}")
            error += 1
        else:
            out_file.write_text(json.dumps(detail, ensure_ascii=False, indent=2))
            score = detail.get("sinta_score_overall", 0)
            scopus = detail.get("scopus_artikel", 0)
            trend_r = len(detail.get("trend_research", []))
            trend_s = len(detail.get("trend_service", []))
            print(f"OK  score={score:,}  scopus={scopus}  R={trend_r}yr  S={trend_s}yr")
            done += 1

        if idx < total:
            time.sleep(DELAY_NEXT)

    print(f"\nSelesai: {done:,} di-scrape, {skip:,} dilewati, {error} error.")
    print(f"Output : {OUT_DIR}")


if __name__ == "__main__":
    main()
