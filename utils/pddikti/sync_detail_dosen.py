#!/usr/bin/env python3
"""
Sinkronisasi detail dosen dari PDDikti ke database.

Alur:
  1. Baca daftar dosen dari universities_profildosen (filter per PT atau semua)
  2. Untuk tiap dosen: jalankan scraper detail (scrape_pddikti_detaildosen.py)
  3. Update universities_profildosen: jabatan_fungsional, pendidikan_tertinggi,
     ikatan_kerja, jenis_kelamin, status, nuptk, url_pencarian, scraped_at
  4. Upsert universities_riwayatpendidikandosen: hapus lama, insert baru

Usage:
    # Sync semua dosen satu PT
    python sync_detail_dosen.py --kode_pt 064167

    # Sync satu dosen berdasarkan NIDN
    python sync_detail_dosen.py --kode_pt 064167 --nidn 0610107606

    # Preview tanpa tulis ke DB
    python sync_detail_dosen.py --kode_pt 064167 --dry-run

    # Batasi jumlah dosen yang diproses
    python sync_detail_dosen.py --kode_pt 064167 --limit 5
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

# Tambahkan path utils agar bisa import scraper
UTILS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(UTILS_DIR))
from scrape_pddikti_detaildosen import init_driver, find_dosen_detail_url, scrape_detail_dosen

# ── Config ────────────────────────────────────────────────────
ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(ENV_PATH)

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

PENDIDIKAN_MAP = {
    "S3": "s3", "S2": "s2", "S1": "s1",
    "PROFESI": "profesi", "D4": "s1",
}
JK_MAP = {
    "LAKI-LAKI": "L", "LAKI": "L", "L": "L",
    "PEREMPUAN": "P", "P": "P",
}
JENJANG_MAP = {
    "S3": "s3", "S2": "s2", "S1": "s1",
    "D4": "d4", "D3": "d3", "D2": "d2", "D1": "d1",
    "PROFESI": "profesi", "SPESIALIS": "profesi",
}


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── DB helpers ─────────────────────────────────────────────

def get_pt(cur, kode_pt):
    cur.execute(
        "SELECT id, nama FROM universities_perguruantinggi WHERE kode_pt = %s",
        (kode_pt,)
    )
    return cur.fetchone()


def get_dosens(cur, pt_id, nidn_filter=None, limit=None):
    sql = ("SELECT id, nidn, nuptk, nama, jabatan_fungsional, "
           "pendidikan_tertinggi, scraped_at "
           "FROM universities_profildosen "
           "WHERE perguruan_tinggi_id = %s")
    params = [pt_id]
    if nidn_filter:
        sql += " AND nidn = %s"
        params.append(nidn_filter)
    sql += " ORDER BY nama"
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql, params)
    return cur.fetchall()


def safe_str(val, maxlen):
    if not val:
        return ""
    return str(val).strip()[:maxlen]


def map_pendidikan(raw):
    return PENDIDIKAN_MAP.get(raw.strip().upper(), "lainnya") if raw else ""


def map_jk(raw):
    return JK_MAP.get(raw.strip().upper(), "") if raw else ""


def map_jenjang(raw):
    return JENJANG_MAP.get(raw.strip().upper(), "") if raw else ""


def detect_luar_negeri(pt_asal):
    """Heuristik sederhana — PT asal di luar Indonesia."""
    if not pt_asal:
        return False
    keywords_ln = ["university", "universität", "université", "universidad",
                   "college", "institute of technology", "usa", "uk", "japan",
                   "malaysia", "australia", "germany", "netherlands"]
    pt_lower = pt_asal.lower()
    return any(k in pt_lower for k in keywords_ln)


# ── DB writes ──────────────────────────────────────────────

def db_update_profil(cur, now, dosen_id, profil, url_pencarian, dry_run):
    jabatan     = safe_str(profil.get("Jabatan Fungsional", ""), 50)
    pend_raw    = profil.get("Pendidikan Tertinggi", "").strip().upper()
    pendidikan  = map_pendidikan(pend_raw)
    jk_raw      = profil.get("Jenis Kelamin", "").strip().upper()
    jenis_kelamin = map_jk(jk_raw)
    nuptk       = safe_str(profil.get("NUPTK", ""), 20)
    status      = safe_str(profil.get("Status Aktif", ""), 30)

    # Ikatan kerja dari "Status Ikatan Kerja" atau "Ikatan Kerja"
    ik_raw = profil.get("Ikatan Kerja", profil.get("Status Ikatan Kerja", "")).strip().upper()
    ikatan_kerja = ""
    if "TIDAK TETAP" in ik_raw:
        ikatan_kerja = "tidak_tetap"
    elif "TETAP" in ik_raw:
        ikatan_kerja = "tetap"

    log(f"    jabatan={jabatan!r} pendidikan={pendidikan!r} jk={jenis_kelamin!r} "
        f"ik={ikatan_kerja!r} status={status!r}")

    if dry_run:
        log(f"    [DRY] UPDATE profildosen id={dosen_id}")
        return

    cur.execute(
        "UPDATE universities_profildosen SET "
        "jabatan_fungsional=%s, pendidikan_tertinggi=%s, jenis_kelamin=%s, "
        "ikatan_kerja=%s, status=%s, nuptk=IF(%s='', nuptk, %s), "
        "url_pencarian=%s, scraped_at=%s, updated_at=%s "
        "WHERE id=%s",
        (jabatan, pendidikan, jenis_kelamin,
         ikatan_kerja, status,
         nuptk, nuptk,
         safe_str(url_pencarian, 500), now, now,
         dosen_id),
    )
    log(f"    [UPD] profildosen id={dosen_id}")


def db_upsert_riwayat_pendidikan(cur, now, dosen_id, riwayat, dry_run):
    if not riwayat:
        return 0

    # Hapus riwayat lama, insert ulang dari hasil scrape terbaru
    if not dry_run:
        cur.execute(
            "DELETE FROM universities_riwayatpendidikandosen WHERE profil_dosen_id = %s",
            (dosen_id,)
        )

    inserted = 0
    for item in riwayat:
        # Kolom dari scraper: bervariasi, coba beberapa kemungkinan nama kolom
        pt_asal   = (item.get("Perguruan Tinggi") or item.get("Nama PT") or
                     item.get("Institusi") or "").strip()
        gelar     = (item.get("Gelar") or item.get("Gelar Akademik") or "").strip()
        jenjang_raw = (item.get("Jenjang") or item.get("Strata") or "").strip().upper()
        jenjang   = map_jenjang(jenjang_raw) or jenjang_raw[:20]
        thn_lulus = (item.get("Tahun Lulus") or item.get("Tahun") or "").strip()[:4]
        is_ln     = detect_luar_negeri(pt_asal)

        if not pt_asal and not gelar and not jenjang:
            continue

        if dry_run:
            log(f"      [DRY] INSERT riwayat: {jenjang} {thn_lulus} {pt_asal[:40]!r} {gelar!r} LN={is_ln}")
        else:
            cur.execute(
                "INSERT INTO universities_riwayatpendidikandosen "
                "(profil_dosen_id, perguruan_tinggi_asal, gelar, jenjang, tahun_lulus, is_luar_negeri) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (dosen_id, pt_asal[:300], gelar[:150], jenjang, thn_lulus, is_ln),
            )
        inserted += 1

    log(f"    riwayat_pendidikan: {inserted} baris {'(dry)' if dry_run else 'diinsert'}")
    return inserted


# ── Main ───────────────────────────────────────────────────

def sync(kode_pt, dry_run, nidn_filter=None, limit=None):
    log("=" * 65)
    log(f"Sync Detail Dosen  Kode PT : {kode_pt}")
    if nidn_filter:
        log(f"                   NIDN    : {nidn_filter}")
    log(f"                   Limit   : {limit or 'semua'}")
    log(f"                   Mode    : {'DRY RUN' if dry_run else 'LIVE'}")
    log("=" * 65)

    conn = pymysql.connect(**DB_CONFIG)
    stats = {"updated": 0, "riwayat": 0, "skipped": 0, "errors": 0}

    try:
        with conn.cursor() as cur:
            pt = get_pt(cur, kode_pt)
            if not pt:
                log(f"[ERROR] kode_pt={kode_pt!r} tidak ditemukan di DB.")
                return
            pt_id   = pt["id"]
            nama_pt = pt["nama"]
            log(f"PT: {nama_pt} (id={pt_id})")

            dosens = get_dosens(cur, pt_id, nidn_filter, limit)
            log(f"Dosen ditemukan: {len(dosens)}\n")

            if not dosens:
                log("Tidak ada dosen untuk diproses.")
                return

        # Buka browser sekali untuk semua dosen
        driver = init_driver(headless=True)
        try:
            for idx, dosen in enumerate(dosens, 1):
                dosen_id = dosen["id"]
                nidn     = dosen["nidn"] or ""
                nuptk    = dosen["nuptk"] or ""
                nama     = dosen["nama"]

                log(f"\n[{idx}/{len(dosens)}] {nama} | NIDN={nidn}")

                try:
                    # Scrape dari PDDikti
                    detail_url, url_pencarian = find_dosen_detail_url(
                        driver, nama, nama_pt, nidn_target=nidn or None
                    )

                    if not detail_url:
                        log(f"  [SKIP] Halaman detail tidak ditemukan di PDDikti.")
                        stats["skipped"] += 1
                        continue

                    data = scrape_detail_dosen(
                        driver, detail_url,
                        url_pencarian    = url_pencarian or "",
                        nuptk_input      = nuptk,
                        full             = False,  # profil + riwayat pendidikan
                    )

                    profil   = data.get("profil", {})
                    riwayat  = data.get("riwayat_pendidikan", [])
                    now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # Update DB
                    with conn.cursor() as cur:
                        db_update_profil(cur, now, dosen_id, profil, url_pencarian, dry_run)
                        n = db_upsert_riwayat_pendidikan(cur, now, dosen_id, riwayat, dry_run)
                        stats["riwayat"] += n
                        stats["updated"] += 1

                    if not dry_run:
                        conn.ping(reconnect=True)
                        conn.commit()

                except Exception as e:
                    log(f"  [ERROR] {e}")
                    import traceback
                    traceback.print_exc()
                    stats["errors"] += 1
                    try:
                        conn.rollback()
                    except Exception:
                        pass

                # Jeda antar dosen untuk menghindari rate limit
                if idx < len(dosens):
                    time.sleep(3)

        finally:
            driver.quit()

    finally:
        conn.close()

    log("\n" + "=" * 65)
    log("RINGKASAN")
    log(f"  ProfilDosen diupdate      : {stats['updated']}")
    log(f"  RiwayatPendidikan diinsert: {stats['riwayat']}")
    log(f"  Dilewati (tidak ditemukan): {stats['skipped']}")
    log(f"  Error                     : {stats['errors']}")
    log("=" * 65)


def main():
    parser = argparse.ArgumentParser(
        description="Sync detail dosen dari PDDikti → DB (profil + riwayat pendidikan)"
    )
    parser.add_argument("--kode_pt",  required=True, help="Kode PT, contoh: 064167")
    parser.add_argument("--nidn",     default="",    help="Filter satu dosen berdasarkan NIDN")
    parser.add_argument("--limit",    default=0,     type=int, help="Batasi jumlah dosen (0=semua)")
    parser.add_argument("--dry-run",  action="store_true", help="Preview tanpa menulis ke DB")
    args = parser.parse_args()

    sync(
        kode_pt     = args.kode_pt,
        nidn_filter = args.nidn or None,
        limit       = args.limit or None,
        dry_run     = args.dry_run,
    )


if __name__ == "__main__":
    main()
