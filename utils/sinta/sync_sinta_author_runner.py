#!/usr/bin/env python3
"""
Runner sinkronisasi SINTA Author — dipanggil oleh sync_runner.py.

Alur per eksekusi:
  1. Baca daftar author dari DB (semua, atau filter per PT pilihan)
  2. Scrape halaman profil SINTA per author (3 URL × 1 author)
  3. Import langsung ke DB (update_or_create)
  4. Update status jadwal setiap 50 author

Opsi filter author yang di-scrape ulang:
  --days N   : hanya author yang scraped_at > N hari lalu (default: 30)
               0 = scrape ulang semua
  --limit N  : batasi maksimum N author per run
  --dry-run  : simulasi tanpa simpan ke DB
  --jadwal_id: (wajib saat dipanggil dari sync_runner)

Usage standalone:
  cd chifoo_backend
  python utils/sinta/sync_sinta_author_runner.py --limit 10 --dry-run
  python utils/sinta/sync_sinta_author_runner.py --days 30 --limit 500
"""

import argparse
import os
import re
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import pymysql
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ── Paths & env ───────────────────────────────────────────────
UTILS_DIR = Path(__file__).resolve().parent
ROOT_DIR  = UTILS_DIR.parent.parent
ENV_PATH  = ROOT_DIR / ".env"
load_dotenv(ENV_PATH)

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(UTILS_DIR.parent / "pddikti"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")

DB_CONFIG = {
    "host":        os.environ.get("DB_HOST", "localhost"),
    "port":        int(os.environ.get("DB_PORT", 3306)),
    "user":        os.environ.get("DB_USER", "root"),
    "password":    os.environ.get("DB_PASSWORD", ""),
    "db":          os.environ.get("DB_NAME", "ptma_db"),
    "charset":     "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "connect_timeout": 30,
}

SINTA_BASE  = "https://sinta.kemdiktisaintek.go.id"
DELAY       = 1.0   # jeda antar request dalam satu author
DELAY_NEXT  = 0.5   # jeda sebelum author berikutnya
TIMEOUT     = 30
RETRY       = 3
RETRY_WAIT  = 8
BATCH_LOG   = 50    # update status DB setiap N author

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id,en-US;q=0.7,en;q=0.3",
    "Referer":         SINTA_BASE,
}

LOG_LINES = []


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_LINES.append(line)


# ── DB helpers ────────────────────────────────────────────────

def get_conn():
    return pymysql.connect(**DB_CONFIG)


def update_status(conn, jadwal_id, status, pesan):
    if jadwal_id is None:
        return
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE universities_sinkronisasijadwal "
            "SET status_terakhir=%s, pesan_terakhir=%s, pid=%s WHERE id=%s",
            (status, pesan[:1000], os.getpid(), jadwal_id)
        )
    conn.commit()


def load_authors(conn, jadwal_id, days_threshold):
    """
    Kembalikan list dict {id, sinta_id, url_profil, afiliasi_sinta_kode}
    yang perlu di-rescrape.
    Filter:
      - scraped_at IS NULL atau scraped_at < NOW() - days_threshold hari
      - Jika jadwal mode_pt='pilihan', hanya author dari PT terpilih
    """
    cutoff_clause = ""
    params = []

    if days_threshold > 0:
        cutoff = datetime.now() - timedelta(days=days_threshold)
        cutoff_clause = "AND (a.scraped_at IS NULL OR a.scraped_at < %s)"
        params.append(cutoff.strftime("%Y-%m-%d %H:%M:%S"))

    # Cek mode_pt jika ada jadwal_id
    mode_pt = "semua"
    if jadwal_id:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT mode_pt FROM universities_sinkronisasijadwal WHERE id=%s",
                (jadwal_id,)
            )
            row = cur.fetchone()
            if row:
                mode_pt = row["mode_pt"]

    if mode_pt == "pilihan" and jadwal_id:
        # Filter hanya author dari PT yang dipilih di jadwal
        sql = f"""
            SELECT a.id, a.sinta_id, a.url_profil
            FROM universities_sintaauthor a
            JOIN universities_sintaafiliasi af ON a.afiliasi_id = af.id
            JOIN universities_perguruantinggi pt ON af.sinta_kode = pt.kode_pt
            JOIN universities_sinkronisasijadwal_pt_list sl
              ON pt.id = sl.perguruantinggi_id AND sl.sinkronisasijadwal_id = %s
            WHERE a.url_profil != '' AND a.url_profil IS NOT NULL
            {cutoff_clause}
            ORDER BY a.scraped_at ASC, a.id ASC
        """
        params = [jadwal_id] + params
    else:
        sql = f"""
            SELECT a.id, a.sinta_id, a.url_profil
            FROM universities_sintaauthor a
            WHERE a.url_profil != '' AND a.url_profil IS NOT NULL
            {cutoff_clause}
            ORDER BY a.scraped_at ASC, a.id ASC
        """

    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


# ── Scraping helpers ──────────────────────────────────────────

def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch(session, url):
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


def _parse_num(s):
    s = re.sub(r"[^\d]", "", str(s))
    return int(s) if s else 0


def _parse_trend_chart(raw, chart_id):
    pattern = rf'id="{chart_id}".*?xAxis.*?"data"\s*:\s*(\[[^\]]+\]).*?series.*?"data"\s*:\s*(\[[^\]]+\])'
    m = re.search(pattern, raw, re.DOTALL)
    if not m:
        return []
    try:
        years  = [int(x.strip().strip('"\'')) for x in m.group(1).strip("[]").split(",") if x.strip()]
        values = [int(x.strip()) for x in m.group(2).strip("[]").split(",") if x.strip()]
        return [{"tahun": y, "jumlah": v} for y, v in zip(years, values)]
    except Exception:
        return []


def _parse_quartile(raw):
    m = re.search(r"quartilePie\s*=\s*echarts\.init.*?data\s*:\s*(\[.*?\])", raw, re.DOTALL)
    if not m:
        return {}
    result = {}
    for item in re.finditer(r'\{[^}]*"value"\s*:\s*(\d+)[^}]*"name"\s*:\s*"([^"]+)"[^}]*\}', m.group(1)):
        result[item.group(2)] = int(item.group(1))
    for item in re.finditer(r'\{[^}]*"name"\s*:\s*"([^"]+)"[^}]*"value"\s*:\s*(\d+)[^}]*\}', m.group(1)):
        result[item.group(1)] = int(item.group(2))
    return result


def _parse_radar(raw):
    m = re.search(r'research-radar.*?series.*?"data"\s*:\s*\[(\[[^\]]+\])\]', raw, re.DOTALL)
    if not m:
        return {}
    vals = [int(x.strip()) for x in m.group(1).strip("[]").split(",") if x.strip().isdigit()]
    keys = ["conference", "articles", "others"]
    return {k: v for k, v in zip(keys, vals)}


def scrape_author(session, url_profil, sinta_id):
    base_url = url_profil.rstrip("/")
    result   = {"sinta_id": sinta_id, "url_profil": url_profil}

    soup, raw = fetch(session, base_url)
    if not soup:
        result["error"] = "fetch gagal"
        return result

    # Foto
    img = soup.select_one("div.profile-picture img")
    if img:
        result["foto_url"] = img.get("src", "")

    # Nama
    h3 = soup.select_one("h3.au-name")
    if h3:
        result["nama"] = h3.get_text(strip=True)

    # Afiliasi & departemen
    for a in soup.select("div.meta-profile a"):
        href = a.get("href", "")
        if "/affiliations/profile/" in href:
            result["afiliasi_url"] = href
            m = re.search(r"/affiliations/profile/(\d+)", href)
            if m:
                result["sinta_id_pt"] = m.group(1)
        elif "/departments/profile/" in href:
            m = re.search(r"/departments/profile/\d+/\w+/(\d+)$", href)
            if m:
                result["kode_dept"] = m.group(1)

    # Bidang keilmuan
    subjects = [a.get_text(strip=True) for a in soup.select("ul.subject-list li a")]
    if subjects:
        result["bidang_keilmuan"] = subjects

    # SINTA Scores
    score_map = {
        "sinta score overall": "sinta_score_overall",
        "sinta score 3yr":     "sinta_score_3year",
        "affil score":         "affil_score",
        "affil score 3yr":     "affil_score_3year",
    }
    for num_el, txt_el in zip(soup.find_all("div", class_="pr-num"), soup.find_all("div", class_="pr-txt")):
        key = score_map.get(txt_el.get_text(strip=True).lower())
        if key:
            result[key] = _parse_num(num_el.get_text(strip=True))

    # Tabel statistik
    tbl = soup.find("table", class_="stat-table")
    if tbl:
        headers = []
        for th in tbl.find_all("th"):
            cls = " ".join(th.get("class", []))
            if "text-warning" in cls:   headers.append("scopus")
            elif "text-success" in cls: headers.append("gscholar")
            elif "text-primary" in cls: headers.append("wos")
        row_map = {
            "article": "artikel", "citation": "sitasi",
            "cited document": "cited_doc", "h-index": "h_index",
            "i10-index": "i10_index", "g-index": "g_index",
        }
        for tr in tbl.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            suffix = row_map.get(tds[0].get_text(strip=True).lower())
            if suffix:
                for src, td in zip(headers, tds[1:]):
                    result[f"{src}_{suffix}"] = _parse_num(td.get_text(strip=True))

    # Kuartil & Radar
    q = _parse_quartile(raw)
    if q:
        result.update({
            "scopus_q1": q.get("Q1", 0), "scopus_q2": q.get("Q2", 0),
            "scopus_q3": q.get("Q3", 0), "scopus_q4": q.get("Q4", 0),
            "scopus_noq": q.get("No-Q", 0),
        })
    rad = _parse_radar(raw)
    if rad:
        result["research_conference"] = rad.get("conference", 0)
        result["research_articles"]   = rad.get("articles", 0)
        result["research_others"]     = rad.get("others", 0)

    # Tren Scopus
    trend_scopus = _parse_trend_chart(raw, "scopus-chart-articles")
    if trend_scopus:
        result["trend_scopus"] = trend_scopus

    time.sleep(DELAY)

    # Tren Penelitian
    soup2, raw2 = fetch(session, f"{base_url}/?view=researches")
    if soup2:
        t = _parse_trend_chart(raw2, "research-chart-articles")
        if t:
            result["trend_research"] = t
    time.sleep(DELAY)

    # Tren Pengabdian
    soup3, raw3 = fetch(session, f"{base_url}/?view=services")
    if soup3:
        t = _parse_trend_chart(raw3, "service-chart-articles")
        if t:
            result["trend_service"] = t

    return result


# ── Import ke DB ──────────────────────────────────────────────

def import_author(conn, data):
    """Import satu author hasil scrape langsung ke DB via Django ORM."""
    import django
    django.setup()
    from apps.universities.models import SintaAfiliasi, SintaDepartemen, SintaAuthor, SintaAuthorTrend
    from django.utils import timezone

    sinta_id = data.get("sinta_id", "")
    if not sinta_id or data.get("error"):
        return False

    # Resolve afiliasi & departemen
    afiliasi = departemen = None
    sinta_id_pt = data.get("sinta_id_pt", "")
    kode_dept   = data.get("kode_dept", "")
    if sinta_id_pt:
        afiliasi = SintaAfiliasi.objects.filter(sinta_id=sinta_id_pt).first()
    if afiliasi and kode_dept:
        departemen = SintaDepartemen.objects.filter(
            afiliasi=afiliasi, kode_dept=kode_dept
        ).first()

    defaults: dict = {
        "nama":        data.get("nama", ""),
        "url_profil":  data.get("url_profil", ""),
    }
    foto_url = data.get("foto_url", "")
    if foto_url:
        defaults["foto_url"] = foto_url

    defaults.update({
        "bidang_keilmuan": data.get("bidang_keilmuan", []),
        "afiliasi":    afiliasi,
        "departemen":  departemen,
        "sinta_score_overall": data.get("sinta_score_overall", 0),
        "sinta_score_3year":   data.get("sinta_score_3year", 0),
        "affil_score":         data.get("affil_score", 0),
        "affil_score_3year":   data.get("affil_score_3year", 0),
        "scopus_artikel":    data.get("scopus_artikel", 0),
        "scopus_sitasi":     data.get("scopus_sitasi", 0),
        "scopus_cited_doc":  data.get("scopus_cited_doc", 0),
        "scopus_h_index":    data.get("scopus_h_index", 0),
        "scopus_i10_index":  data.get("scopus_i10_index", 0),
        "scopus_g_index":    data.get("scopus_g_index", 0),
        "gscholar_artikel":   data.get("gscholar_artikel", 0),
        "gscholar_sitasi":    data.get("gscholar_sitasi", 0),
        "gscholar_cited_doc": data.get("gscholar_cited_doc", 0),
        "gscholar_h_index":   data.get("gscholar_h_index", 0),
        "gscholar_i10_index": data.get("gscholar_i10_index", 0),
        "gscholar_g_index":   data.get("gscholar_g_index", 0),
        "wos_artikel":   data.get("wos_artikel", 0),
        "wos_sitasi":    data.get("wos_sitasi", 0),
        "wos_cited_doc": data.get("wos_cited_doc", 0),
        "wos_h_index":   data.get("wos_h_index", 0),
        "wos_i10_index": data.get("wos_i10_index", 0),
        "wos_g_index":   data.get("wos_g_index", 0),
        "scopus_q1":  data.get("scopus_q1", 0),
        "scopus_q2":  data.get("scopus_q2", 0),
        "scopus_q3":  data.get("scopus_q3", 0),
        "scopus_q4":  data.get("scopus_q4", 0),
        "scopus_noq": data.get("scopus_noq", 0),
        "research_conference": data.get("research_conference", 0),
        "research_articles":   data.get("research_articles", 0),
        "research_others":     data.get("research_others", 0),
        "scraped_at": timezone.now(),
    })

    author, _ = SintaAuthor.objects.update_or_create(
        sinta_id=sinta_id,
        defaults=defaults,
    )

    # Trend — hapus & insert ulang
    author.trend.all().delete()
    trend_objs = []
    for jenis, key in [("scopus", "trend_scopus"), ("research", "trend_research"), ("service", "trend_service")]:
        for item in data.get(key, []):
            trend_objs.append(SintaAuthorTrend(
                author=author, jenis=jenis,
                tahun=item["tahun"], jumlah=item["jumlah"],
            ))
    if trend_objs:
        SintaAuthorTrend.objects.bulk_create(trend_objs, ignore_conflicts=True)

    return True


# ── Main runner ───────────────────────────────────────────────

def load_single_author(conn, author_id):
    """Kembalikan list satu author berdasarkan id DB."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, sinta_id, url_profil FROM universities_sintaauthor "
            "WHERE id = %s AND url_profil != '' AND url_profil IS NOT NULL",
            (author_id,)
        )
        row = cur.fetchone()
    return [row] if row else []


def run(jadwal_id=None, dry_run=False, days=30, limit=None, author_id=None):
    import django
    django.setup()

    conn = get_conn()
    session = make_session()

    if author_id:
        authors = load_single_author(conn, author_id)
    else:
        if jadwal_id:
            update_status(conn, jadwal_id, "berjalan", "Memuat daftar author...")
        authors = load_authors(conn, jadwal_id, days)
        if limit:
            authors = authors[:limit]

    total = len(authors)
    log(f"Author yang akan di-sync: {total} (days={days}, limit={limit}, dry_run={dry_run})")

    if total == 0:
        msg = "Tidak ada author yang perlu diperbarui."
        log(msg)
        if jadwal_id:
            update_status(conn, jadwal_id, "selesai", msg)
        return

    ok = err = skip = 0
    errors = []

    for i, author in enumerate(authors, 1):
        sinta_id  = str(author["sinta_id"])
        url       = author["url_profil"]
        pesan_log = f"[{i}/{total}] Scrape author sinta_id={sinta_id}"
        log(pesan_log)

        if i % BATCH_LOG == 0 and jadwal_id:
            update_status(conn, jadwal_id, "berjalan",
                          f"[{i}/{total}] Scrape author sinta_id={sinta_id} — ok={ok} err={err}")

        try:
            data = scrape_author(session, url, sinta_id)
            if data.get("error"):
                log(f"  ✗ {sinta_id}: {data['error']}")
                skip += 1
            elif dry_run:
                ok += 1
                log(f"  ✓ (dry-run) {data.get('nama', sinta_id)}")
            else:
                if import_author(conn, data):
                    ok += 1
                    log(f"  ✓ {data.get('nama', sinta_id)}")
                else:
                    skip += 1
        except Exception as e:
            msg = f"{sinta_id}: {e}"
            log(f"  ✗ {msg}")
            errors.append(msg)
            err += 1

        time.sleep(DELAY_NEXT)

    # Ringkasan
    mode   = "DRY-RUN" if dry_run else "diperbarui"
    ringkasan = (
        f"Selesai: {ok} author {mode}, {skip} dilewati, {err} error "
        f"dari {total} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    if errors:
        ringkasan += "\nError:\n" + "\n".join(errors[:10])

    log(ringkasan)
    if jadwal_id:
        status_akhir = "error" if err > 0 else "selesai"
        update_status(conn, jadwal_id, status_akhir, ringkasan[:1000])

    conn.close()


# ── CLI standalone ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync SINTA Author ke database")
    parser.add_argument("--jadwal_id", type=int, default=None)
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--days",      type=int, default=30,
                        help="Scrape ulang author yang scraped_at > N hari lalu (0=semua)")
    parser.add_argument("--limit",     type=int, default=None,
                        help="Maksimum author per run")
    parser.add_argument("--author_id", type=int, default=None,
                        help="Sync satu author berdasarkan id DB")
    args = parser.parse_args()
    run(jadwal_id=args.jadwal_id, dry_run=args.dry_run, days=args.days,
        limit=args.limit, author_id=args.author_id)


if __name__ == "__main__":
    main()
