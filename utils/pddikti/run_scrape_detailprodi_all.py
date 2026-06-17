#!/usr/bin/env python3
"""
Runner: scrape detail prodi semua PTMA dari DB → utils/outs/{kode_pt}/

Memanggil scrape_pddikti_detailprodi.main() untuk setiap PT.
Output: utils/outs/{kode_pt}/{kode_pt}_{kode_ps}_detailprodi.json

Usage:
    # Semua PT (fresh)
    python run_scrape_detailprodi_all.py

    # Resume — skip PT yang sudah semua prodinya ter-scrape;
    #           PT yang sebagian → dilanjutkan (--resume diteruskan ke scraper)
    python run_scrape_detailprodi_all.py --resume

    # Hanya satu PT
    python run_scrape_detailprodi_all.py --kode_pt 071024

    # Batasi jumlah PT
    python run_scrape_detailprodi_all.py --limit 5
"""

import argparse
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

UTILS_DIR   = Path(__file__).resolve().parent
BACKEND_DIR = UTILS_DIR.parent.parent
ENV_PATH    = BACKEND_DIR / ".env"
load_dotenv(ENV_PATH)

sys.path.insert(0, str(UTILS_DIR))
from scrape_pddikti_detailprodi import main as scrape_pt_main

OUT_DIR = str(UTILS_DIR.parent / "outs")

# PT dengan nama panjang+tanda kurung yang tidak bisa dicari dengan nama penuh.
KEYWORD_OVERRIDE = {
    '213388': 'staim blora',
    '213539': 'stebis sumedang',
}

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


def get_pt_list(kode_pt=None):
    conn = pymysql.connect(**DB_CONFIG)
    with conn.cursor() as cur:
        if kode_pt:
            cur.execute(
                "SELECT kode_pt, nama FROM universities_perguruantinggi "
                "WHERE kode_pt = %s AND is_active = 1",
                (kode_pt,),
            )
        else:
            cur.execute(
                "SELECT kode_pt, nama FROM universities_perguruantinggi "
                "WHERE kode_pt IS NOT NULL AND kode_pt != '' AND is_active = 1 "
                "ORDER BY kode_pt"
            )
        rows = cur.fetchall()
    conn.close()
    return rows


def count_scraped_prodi(kode_pt):
    """Hitung jumlah file *_detailprodi.json yang sudah ada untuk PT ini."""
    pt_dir = os.path.join(OUT_DIR, kode_pt)
    if not os.path.isdir(pt_dir):
        return 0
    return sum(1 for f in os.listdir(pt_dir) if f.endswith("_detailprodi.json"))


def main():
    parser = argparse.ArgumentParser(
        description="Scrape detail prodi semua PTMA dari DB"
    )
    parser.add_argument("--kode_pt", default=None, nargs="+",
                        help="Scrape satu atau beberapa PT (pisah spasi)")
    parser.add_argument("--resume",  action="store_true",
                        help="Skip PT yang semua prodinya sudah ada; "
                             "PT yang sebagian tetap dilanjutkan")
    parser.add_argument("--limit",   type=int, default=None,
                        help="Batasi jumlah PT yang diproses")
    args = parser.parse_args()

    if args.kode_pt and len(args.kode_pt) > 1:
        # Multiple kode: ambil data PT dari DB untuk kode-kode tersebut
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(args.kode_pt))
            cur.execute(
                f"SELECT kode_pt, nama FROM universities_perguruantinggi "
                f"WHERE kode_pt IN ({placeholders}) AND is_active = 1 "
                f"ORDER BY FIELD(kode_pt, {placeholders})",
                args.kode_pt * 2,
            )
            pt_list = cur.fetchall()
        conn.close()
    else:
        kode_single = args.kode_pt[0] if args.kode_pt else None
        pt_list = get_pt_list(kode_pt=kode_single)
    total_pt = len(pt_list)
    print(f"Total PT dari DB : {total_pt}")

    if args.limit:
        pt_list = pt_list[:args.limit]
        print(f"Mode limit       : proses {args.limit} PT pertama")

    done = skip = error = 0

    for i, pt in enumerate(pt_list, 1):
        kode = pt["kode_pt"]
        nama = pt["nama"]

        print(f"\n{'='*70}")
        print(f"[{i}/{len(pt_list)}] {kode} — {nama}")
        print(f"{'='*70}")

        n_done = count_scraped_prodi(kode)

        try:
            scrape_pt_main(
                keyword = KEYWORD_OVERRIDE.get(kode, nama),
                nama_pt = nama.upper(),  # pencocokan case-insensitive
                kode_pt = kode,
                resume  = True,          # selalu resume per prodi
                force   = False,
                start   = 1,
                end     = None,
            )
            done += 1
        except Exception as e:
            print(f"  [ERROR] {kode}: {e}")
            error += 1

    print(f"\n{'='*70}")
    print(f"SELESAI")
    print(f"  PT berhasil diproses : {done}")
    print(f"  PT error             : {error}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
