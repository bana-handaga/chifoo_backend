#!/usr/bin/env python3
"""
Runner sinkronisasi SINTA Afiliasi — scrape & langsung simpan ke DB.

Data yang di-sync per afiliasi:
  - Identitas  : sinta_id, sinta_kode, nama_sinta, singkatan_sinta, lokasi_sinta
  - Logo       : logo_base64 (dari /authorverification/public/images/affiliations/{id}.jpg)
  - Ringkasan  : jumlah_authors, jumlah_departments, jumlah_journals
  - SINTA Score: overall, 3yr, productivity, productivity 3yr
  - Statistik  : Scopus, GScholar, WoS, Garuda (dokumen, sitasi, cited, per-researcher)
  - Kuartil    : scopus_q1..noq
  - sinta_last_update
  - Tren tahunan (SintaTrendTahunan): scopus, research, service

URL yang di-scrape per PT:
  /affiliations/profile/{sinta_id}               → data utama + scopus trend
  /affiliations/profile/{sinta_id}/?view=researches → research trend + radar
  /affiliations/profile/{sinta_id}/?view=services   → service trend
  /authorverification/public/images/affiliations/{sinta_id}.jpg  → logo

Opsi filter author yang di-scrape ulang:
  --days N   : hanya afiliasi scraped_at > N hari lalu (default: 30, 0=semua)
  --limit N  : batasi maksimum N afiliasi per run
  --dry-run  : simulasi tanpa simpan ke DB
  --sinta_id : sync satu PT berdasarkan SINTA ID
  --kode_pt  : sync satu PT berdasarkan kode_pt

Usage standalone:
  cd chifoo_backend
  python utils/sinta/sync_sinta_afiliasi_runner.py --limit 5 --dry-run
  python utils/sinta/sync_sinta_afiliasi_runner.py --sinta_id 27
  python utils/sinta/sync_sinta_afiliasi_runner.py --kode_pt 061008
  python utils/sinta/sync_sinta_afiliasi_runner.py --days 30 --limit 50
"""

import argparse
import base64
import os
import re
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ── Paths & env ───────────────────────────────────────────────
UTILS_DIR = Path(__file__).resolve().parent
ROOT_DIR  = UTILS_DIR.parent.parent
ENV_PATH  = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)

sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")

SINTA_BASE = "https://sinta.kemdiktisaintek.go.id"
DELAY      = 1.0   # jeda antar request dalam satu PT
DELAY_NEXT = 1.0   # jeda sebelum PT berikutnya
TIMEOUT    = 30
RETRY      = 3
RETRY_WAIT = 8

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id,en-US;q=0.7,en;q=0.3",
    "Referer":         SINTA_BASE,
}

SINTA_USERNAME = os.environ.get("SINTA_USERNAME", "")
SINTA_PASSWORD = os.environ.get("SINTA_PASSWORD", "")
LOGIN_URL      = f"{SINTA_BASE}/logins/do_login"

LOG_LINES = []


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_LINES.append(line)


# ── HTTP helpers ──────────────────────────────────────────────

def sinta_login(session):
    """Login ke SINTA menggunakan credentials dari .env. Return True jika berhasil."""
    if not SINTA_USERNAME or not SINTA_PASSWORD:
        log("SINTA_USERNAME/SINTA_PASSWORD tidak ada di .env — skip login")
        return False
    try:
        resp = session.post(LOGIN_URL, data={
            "username": SINTA_USERNAME,
            "password": SINTA_PASSWORD,
        }, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code == 200 and "ci_session" in session.cookies:
            log(f"Login SINTA berhasil sebagai {SINTA_USERNAME}")
            return True
        log(f"Login SINTA gagal (status={resp.status_code})")
        return False
    except Exception as e:
        log(f"Login SINTA error: {e}")
        return False


def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    sinta_login(s)
    return s


def fetch(session, url):
    """GET url dengan retry. Return (BeautifulSoup, raw_text) atau (None, '')."""
    for attempt in range(RETRY):
        try:
            r = session.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "html.parser"), r.text
            if r.status_code == 404:
                return None, ""
        except Exception as e:
            if attempt < RETRY - 1:
                time.sleep(RETRY_WAIT)
    return None, ""


def fetch_logo_base64(session, sinta_id):
    """Download logo afiliasi dari SINTA dan encode ke data URI base64. Return '' jika gagal."""
    url = f"{SINTA_BASE}/authorverification/public/images/affiliations/{sinta_id}.jpg"
    try:
        r = session.get(url, timeout=TIMEOUT)
        if r.status_code == 200 and r.content:
            b64 = base64.b64encode(r.content).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
    except Exception:
        pass
    return ""


# ── Parse helpers ─────────────────────────────────────────────

def _parse_number(text):
    """'1.318.091' atau '117,66' → float. Return 0.0 jika gagal."""
    if not text:
        return 0.0
    clean = str(text).strip().replace(".", "").replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return 0.0


def _chunk_after(raw, anchor, size=8000):
    """Ambil N karakter setelah kemunculan pertama anchor."""
    for q in (f"'{anchor}'", f'"{anchor}"', anchor):
        idx = raw.find(q)
        if idx != -1:
            return raw[idx: idx + size]
    return ""


def _parse_trend_chart(raw, chart_id):
    """
    Parse chart tren satu seri dari raw JS.
    Return list of {tahun: int, jumlah: int}.
    """
    chunk = _chunk_after(raw, chart_id)
    if not chunk:
        return []
    mx = re.search(r'xAxis.*?data\s*:\s*\[([^\]]+)\]', chunk, re.DOTALL)
    ms = re.search(r'series\s*:.*?data\s*:\s*\[([^\]]+)\]', chunk, re.DOTALL)
    if not mx or not ms:
        # Fallback: cari array data lurus
        arrays = re.findall(r"data\s*:\s*\[([^\]]+)\]", chunk, re.DOTALL)
        if len(arrays) < 2:
            return []
        mx_group = arrays[0]
        ms_group = arrays[1]
    else:
        mx_group = mx.group(1)
        ms_group = ms.group(1)

    years  = [x.strip().strip("'\"") for x in re.split(r',', mx_group) if x.strip().strip("'\"")]
    values = [x.strip() for x in re.split(r',', ms_group) if x.strip()]
    result = []
    for y, v in zip(years, values):
        try:
            result.append({"tahun": int(y), "jumlah": int(v)})
        except (ValueError, TypeError):
            pass
    return result


def _parse_quartile(raw):
    """
    Parse distribusi kuartil Scopus dari JS eCharts (quartile-pie).
    Return dict {Q1: int, Q2: int, ...} atau {}.
    """
    # Cari blok JS quartile
    chunk = ""
    m = re.search(r"var\s+quartilePie|optionQ\s*=\s*\{|quartile-pie", raw, re.IGNORECASE)
    if m:
        chunk = raw[m.start(): m.start() + 3000]
    if not chunk:
        chunk = _chunk_after(raw, "quartile-pie", 3000)
    if not chunk:
        return {}

    result = {}
    for m in re.finditer(
        r'value\s*:\s*(\d+)[\s\S]{0,30}?name\s*:\s*[\'\"](Q\d+|No-Q|NoQ)[\'\"]\s*}'
        r'|name\s*:\s*[\'\"](Q\d+|No-Q|NoQ)[\'\"][\s\S]{0,30}?value\s*:\s*(\d+)',
        chunk
    ):
        if m.group(1):
            result[m.group(2)] = int(m.group(1))
        else:
            result[m.group(3)] = int(m.group(4))
    return result


def _parse_research_radar(raw):
    """
    Parse radar chart penelitian (research-radar).
    Return dict {article: int, conference: int, others: int}.
    """
    chunk = _chunk_after(raw, "research-radar", 3000)
    if not chunk:
        return {}

    indicators = re.findall(r"name\s*:\s*['\"]([^'\"]+)['\"]", chunk)
    indicators = [n for n in indicators if n.lower() in ("article", "conference", "others", "output")]

    m_val = re.search(r"value\s*:\s*\[\s*([\d\s,]+)\s*\]", chunk)
    if not m_val or not indicators:
        return {}

    values = [int(v.strip()) for v in m_val.group(1).split(",") if v.strip().isdigit()]
    return {k.lower(): v for k, v in zip(indicators, values)}


# ── Main scraper per PT ───────────────────────────────────────

STAT_SOURCES = [
    ("text-warning", "scopus"),
    ("text-success", "gscholar"),
    ("text-primary", "wos"),
    ("text-danger",  "garuda"),
]

STAT_ROW_MAP = {
    "documents":               "dokumen",
    "citation":                "sitasi",
    "cited document":          "dokumen_disitasi",
    "citation per researcher": "sitasi_per_peneliti",
    "citation per researchers":"sitasi_per_peneliti",
}

SCORE_MAP = {
    "sinta score overall":          "sinta_score_overall",
    "sinta score 3yr":              "sinta_score_3year",
    "sinta score productivity":     "sinta_score_productivity",
    "sinta score productivity 3yr": "sinta_score_productivity_3year",
}


def scrape_afiliasi(session, sinta_id, fetch_logo=True):
    """
    Scrape semua data profil afiliasi untuk satu PT.
    Return dict atau dict dengan key 'error'.
    """
    profile_url = f"{SINTA_BASE}/affiliations/profile/{sinta_id}"
    result = {"sinta_id": sinta_id, "sinta_profile_url": profile_url}

    # ── Halaman utama ─────────────────────────────────────────
    soup, raw = fetch(session, profile_url)
    if not soup:
        result["error"] = "fetch gagal"
        return result

    # Nama PT
    univ_div = soup.find("div", class_="univ-name")
    if univ_div:
        h = univ_div.find(["h3", "h2", "h1"])
        if h:
            result["nama_sinta"] = h.get_text(strip=True)

    # Singkatan
    el = soup.find(class_="affil-abbrev")
    if el:
        result["singkatan_sinta"] = el.get_text(strip=True)

    # Lokasi
    el = soup.find(class_="affil-loc")
    if el:
        result["lokasi_sinta"] = el.get_text(strip=True)

    # SINTA ID & Kode PT
    el = soup.find(class_="affil-code")
    if el:
        code_text = el.get_text(" ", strip=True)
        m = re.search(r"ID\s*:\s*(\d+)", code_text)
        if m:
            result["sinta_id"] = m.group(1)
        m = re.search(r"CODE\s*:\s*(\S+)", code_text)
        if m:
            result["sinta_kode"] = m.group(1)

    # Ringkasan: Authors, Departments, Journals
    stat_nums  = soup.find_all("div", class_="stat-num")
    stat_texts = soup.find_all("div", class_="stat-text")
    for num_el, txt_el in zip(stat_nums, stat_texts):
        num = num_el.get_text(strip=True)
        lbl = txt_el.get_text(strip=True).lower()
        if num and lbl:
            field = "jumlah_" + lbl.replace(" ", "_")
            result[field] = int(_parse_number(num))

    # SINTA Score
    pr_nums = soup.find_all("div", class_="pr-num")
    pr_txts = soup.find_all("div", class_="pr-txt")
    for num_el, txt_el in zip(pr_nums, pr_txts):
        num = num_el.get_text(strip=True)
        lbl = txt_el.get_text(strip=True).lower()
        field = SCORE_MAP.get(lbl)
        if field and num:
            result[field] = int(_parse_number(num))

    # Tabel statistik publikasi
    stat_tbl = soup.find("table", class_="stat-table")
    if stat_tbl:
        thead_ths = stat_tbl.find("thead").find_all("th") if stat_tbl.find("thead") else []
        col_source = []
        for th in thead_ths:
            classes = th.get("class", [])
            matched = None
            for cls, src_name in STAT_SOURCES:
                if cls in classes:
                    matched = src_name
                    break
            col_source.append(matched)

        tbody = stat_tbl.find("tbody")
        for tr in (tbody.find_all("tr") if tbody else []):
            cells = tr.find_all("td")
            if not cells:
                continue
            row_label = cells[0].get_text(strip=True).lower()
            field_suffix = None
            for key, val in STAT_ROW_MAP.items():
                if key in row_label:
                    field_suffix = val
                    break
            if not field_suffix:
                continue
            for ci, cell in enumerate(cells):
                if ci >= len(col_source) or col_source[ci] is None:
                    continue
                src = col_source[ci]
                field = f"{src}_{field_suffix}"
                result[field] = _parse_number(cell.get_text(strip=True))

    # Distribusi kuartil Scopus
    q = _parse_quartile(raw)
    if q:
        result.update({
            "scopus_q1":  q.get("Q1", 0),
            "scopus_q2":  q.get("Q2", 0),
            "scopus_q3":  q.get("Q3", 0),
            "scopus_q4":  q.get("Q4", 0),
            "scopus_noq": q.get("No-Q", q.get("NoQ", 0)),
        })

    # Tren Scopus
    trend_scopus = _parse_trend_chart(raw, "scopus-chart-articles")
    if trend_scopus:
        result["trend_scopus"] = trend_scopus

    # Last update
    for small in soup.find_all("small"):
        txt = small.get_text(strip=True)
        if "last update" in txt.lower():
            m = re.search(r"last update\s*[:\-]?\s*(.+)", txt, re.IGNORECASE)
            if m:
                result["sinta_last_update"] = m.group(1).strip()
            break

    time.sleep(DELAY)

    # ── ?view=researches ──────────────────────────────────────
    soup_r, raw_r = fetch(session, f"{profile_url}/?view=researches")
    if soup_r:
        trend_r = _parse_trend_chart(raw_r, "research-chart-articles")
        if trend_r:
            result["trend_research"] = trend_r
        radar = _parse_research_radar(raw_r)
        if radar:
            result["research_radar"] = radar
    time.sleep(DELAY)

    # ── ?view=services ────────────────────────────────────────
    soup_s, raw_s = fetch(session, f"{profile_url}/?view=services")
    if soup_s:
        trend_s = _parse_trend_chart(raw_s, "service-chart-articles")
        if trend_s:
            result["trend_service"] = trend_s
    time.sleep(DELAY)

    # ── Logo (hanya jika belum ada) ────────────────────────────
    if fetch_logo:
        logo = fetch_logo_base64(session, result["sinta_id"])
        if logo:
            result["logo_base64"] = logo
        time.sleep(DELAY)

    return result


# ── Import ke DB ──────────────────────────────────────────────

def import_afiliasi(data):
    """
    Simpan hasil scrape satu PT ke DB via Django ORM.
    Return True jika berhasil, False jika skip.
    """
    import django
    django.setup()
    from apps.universities.models import SintaAfiliasi, SintaTrendTahunan
    from django.utils import timezone

    sinta_id = data.get("sinta_id", "")
    if not sinta_id or data.get("error"):
        return False

    # Cari SintaAfiliasi berdasarkan sinta_id
    try:
        afiliasi = SintaAfiliasi.objects.get(sinta_id=sinta_id)
    except SintaAfiliasi.DoesNotExist:
        log(f"  SKIP: sinta_id={sinta_id} tidak ada di DB — jalankan import awal dulu")
        return False

    defaults: dict = {
        "sinta_kode":       data.get("sinta_kode", afiliasi.sinta_kode),
        "nama_sinta":       data.get("nama_sinta", afiliasi.nama_sinta),
        "singkatan_sinta":  data.get("singkatan_sinta", afiliasi.singkatan_sinta),
        "lokasi_sinta":     data.get("lokasi_sinta", afiliasi.lokasi_sinta),
        "sinta_profile_url": data.get("sinta_profile_url", afiliasi.sinta_profile_url),

        "jumlah_authors":     int(data.get("jumlah_authors", 0) or 0),
        "jumlah_departments": int(data.get("jumlah_departments", 0) or 0),
        "jumlah_journals":    int(data.get("jumlah_journals", 0) or 0),

        "sinta_score_overall":            int(data.get("sinta_score_overall", 0) or 0),
        "sinta_score_3year":              int(data.get("sinta_score_3year", 0) or 0),
        "sinta_score_productivity":       int(data.get("sinta_score_productivity", 0) or 0),
        "sinta_score_productivity_3year": int(data.get("sinta_score_productivity_3year", 0) or 0),

        "scopus_dokumen":             float(data.get("scopus_dokumen", 0) or 0),
        "scopus_sitasi":              float(data.get("scopus_sitasi", 0) or 0),
        "scopus_dokumen_disitasi":    float(data.get("scopus_dokumen_disitasi", 0) or 0),
        "scopus_sitasi_per_peneliti": float(data.get("scopus_sitasi_per_peneliti", 0) or 0),

        "gscholar_dokumen":             float(data.get("gscholar_dokumen", 0) or 0),
        "gscholar_sitasi":              float(data.get("gscholar_sitasi", 0) or 0),
        "gscholar_dokumen_disitasi":    float(data.get("gscholar_dokumen_disitasi", 0) or 0),
        "gscholar_sitasi_per_peneliti": float(data.get("gscholar_sitasi_per_peneliti", 0) or 0),

        "wos_dokumen":             float(data.get("wos_dokumen", 0) or 0),
        "wos_sitasi":              float(data.get("wos_sitasi", 0) or 0),
        "wos_dokumen_disitasi":    float(data.get("wos_dokumen_disitasi", 0) or 0),
        "wos_sitasi_per_peneliti": float(data.get("wos_sitasi_per_peneliti", 0) or 0),

        "garuda_dokumen":             float(data.get("garuda_dokumen", 0) or 0),
        "garuda_sitasi":              float(data.get("garuda_sitasi", 0) or 0),
        "garuda_dokumen_disitasi":    float(data.get("garuda_dokumen_disitasi", 0) or 0),
        "garuda_sitasi_per_peneliti": float(data.get("garuda_sitasi_per_peneliti", 0) or 0),

        "scopus_q1":  int(data.get("scopus_q1", 0) or 0),
        "scopus_q2":  int(data.get("scopus_q2", 0) or 0),
        "scopus_q3":  int(data.get("scopus_q3", 0) or 0),
        "scopus_q4":  int(data.get("scopus_q4", 0) or 0),
        "scopus_noq": int(data.get("scopus_noq", 0) or 0),

        "sinta_last_update": data.get("sinta_last_update", ""),
    }

    # Logo: hanya update jika ada hasil baru
    logo = data.get("logo_base64", "")
    if logo:
        defaults["logo_base64"] = logo

    for field, val in defaults.items():
        setattr(afiliasi, field, val)
    afiliasi.save()

    # Tren Tahunan — hapus & insert ulang per jenis yang ter-scrape
    radar = data.get("research_radar", {})

    for jenis, key in [
        ("scopus",   "trend_scopus"),
        ("research", "trend_research"),
        ("service",  "trend_service"),
    ]:
        items = data.get(key, [])
        if not items:
            continue
        afiliasi.trend_tahunan.filter(jenis=jenis).delete()
        trend_objs = []
        for item in items:
            extra = {}
            if jenis == "research":
                extra = {
                    "research_article":    radar.get("article", 0),
                    "research_conference": radar.get("conference", 0),
                    "research_others":     radar.get("others", 0),
                }
            trend_objs.append(SintaTrendTahunan(
                afiliasi=afiliasi,
                jenis=jenis,
                tahun=item["tahun"],
                jumlah=item["jumlah"],
                **extra,
            ))
        if trend_objs:
            SintaTrendTahunan.objects.bulk_create(trend_objs, ignore_conflicts=True)

    return True


# ── Load afiliasi dari DB ─────────────────────────────────────

def load_afiliasi(days_threshold=30, sinta_id=None, kode_pt=None, limit=None):
    """
    Return list dict {id, sinta_id, nama_sinta} dari DB.
    Filter: scraped_at lebih tua dari days_threshold hari (0=semua).
    """
    import django
    django.setup()
    from apps.universities.models import SintaAfiliasi
    from django.utils import timezone

    qs = SintaAfiliasi.objects.select_related("perguruan_tinggi").exclude(sinta_id="")

    if sinta_id:
        qs = qs.filter(sinta_id=str(sinta_id))
    elif kode_pt:
        qs = qs.filter(perguruan_tinggi__kode_pt=kode_pt)
    elif days_threshold > 0:
        cutoff = timezone.now() - timedelta(days=days_threshold)
        qs = qs.filter(scraped_at__lt=cutoff)

    qs = qs.order_by("scraped_at")
    if limit:
        qs = qs[:limit]

    return list(qs.values("id", "sinta_id", "nama_sinta",
                          "sinta_profile_url", "logo_base64"))


# ── Main runner ───────────────────────────────────────────────

def run(dry_run=False, days=30, limit=None, sinta_id=None, kode_pt=None):
    import django
    django.setup()

    session = make_session()
    afiliasis = load_afiliasi(
        days_threshold=days,
        sinta_id=sinta_id,
        kode_pt=kode_pt,
        limit=limit,
    )

    total = len(afiliasis)
    log(f"Afiliasi yang akan di-sync: {total} (days={days}, limit={limit}, dry_run={dry_run})")

    if total == 0:
        log("Tidak ada afiliasi yang perlu diperbarui.")
        return

    ok = err = skip = 0

    for i, af in enumerate(afiliasis, 1):
        sid  = str(af["sinta_id"])
        nama = af.get("nama_sinta") or sid
        fetch_logo = not bool(af.get("logo_base64"))  # hanya fetch jika belum ada
        log(f"[{i}/{total}] {nama} (sinta_id={sid})")

        try:
            data = scrape_afiliasi(session, sid, fetch_logo=fetch_logo)
            if data.get("error"):
                log(f"  ✗ {data['error']}")
                skip += 1
            elif dry_run:
                log(f"  ✓ (dry-run) score={data.get('sinta_score_overall', 0):,} "
                    f"scopus={data.get('scopus_dokumen', 0):.0f}")
                ok += 1
            else:
                if import_afiliasi(data):
                    log(f"  ✓ score={data.get('sinta_score_overall', 0):,} "
                        f"scopus={data.get('scopus_dokumen', 0):.0f}")
                    ok += 1
                else:
                    skip += 1
        except Exception as e:
            log(f"  ✗ {sid}: {e}")
            traceback.print_exc()
            err += 1

        if i < total:
            time.sleep(DELAY_NEXT)

    log(
        f"\nSelesai: {ok} berhasil, {skip} dilewati, {err} error dari {total} afiliasi — "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )


# ── CLI standalone ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync SINTA Afiliasi ke database")
    parser.add_argument("--sinta_id", type=str, default=None, help="Sync satu PT berdasarkan SINTA ID")
    parser.add_argument("--kode_pt",  type=str, default=None, help="Sync satu PT berdasarkan kode_pt")
    parser.add_argument("--dry-run",  action="store_true",    help="Simulasi tanpa menyimpan ke DB")
    parser.add_argument("--days",     type=int, default=30,
                        help="Scrape ulang afiliasi scraped_at > N hari lalu (0=semua)")
    parser.add_argument("--limit",    type=int, default=None, help="Maksimum afiliasi per run")
    args = parser.parse_args()

    run(
        dry_run=args.dry_run,
        days=args.days,
        limit=args.limit,
        sinta_id=args.sinta_id,
        kode_pt=args.kode_pt,
    )


if __name__ == "__main__":
    main()
