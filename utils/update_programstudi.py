#!/usr/bin/env python3
"""
Update universities_programstudi table from a PDDikti programstudi JSON file.

Usage:
    python update_programstudi.py [--file PATH] [--dry-run]

Defaults:
    --file  ~/projects/utils/outs/071024_programstudi.json


Script created at utils/update_programstudi.py. Here's what it does:

Loads DB credentials from ~/projects/backend/.env
Reads the JSON file (default: outs/071024_programstudi.json)
Resolves all kode_pt → perguruan_tinggi_id in one query
For each prodi item: checks if (perguruan_tinggi_id, kode_prodi) already exists → skips if yes, inserts if no
Maps jenjang (S1→s1, S2→s2, etc.) and akreditasi (Unggul→unggul, Baik Sekali→baik_sekali, etc.) to Django model choices
Usage:


# Preview without writing
python3 ~/projects/utils/update_programstudi.py --dry-run

# Run for default file (071024_programstudi.json)
python3 ~/projects/utils/update_programstudi.py

# Run for a different file
python3 ~/projects/utils/update_programstudi.py --file ~/projects/utils/outs/061008_programstudi.json

"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

# ── Load .env from backend dir ───────────────────────────────
ENV_PATH = Path(__file__).resolve().parent.parent / "backend" / ".env"
load_dotenv(ENV_PATH)

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 3306)),
    "user":     os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "db":       os.environ.get("DB_NAME", "ptma_db"),
    "charset":  "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

JENJANG_MAP = {
    "D1": "d1",
    "D2": "d2",
    "D3": "d3",
    "D4": "d4",
    "S1": "s1",
    "S2": "s2",
    "S3": "s3",
    "PROFESI": "profesi",
    "SPESIALIS": "profesi",
}

AKREDITASI_MAP = {
    "UNGGUL":      "unggul",
    "BAIK SEKALI": "baik_sekali",
    "BAIK":        "baik",
    "C":           "c",
}


def map_jenjang(raw: str) -> str:
    return JENJANG_MAP.get(raw.strip().upper(), "s1")


def map_akreditasi(raw: str) -> str:
    return AKREDITASI_MAP.get(raw.strip().upper(), "belum")


def run(json_path: str, dry_run: bool) -> None:
    with open(json_path, encoding="utf-8") as f:
        items = json.load(f)

    if not items:
        print("JSON file is empty.")
        return

    total = len(items)
    items = [i for i in items if i.get("Status", "").strip().upper() == "AKTIF"]
    print(f"Loaded {total} items, {len(items)} aktif (others ignored)")

    conn = pymysql.connect(**DB_CONFIG)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    inserted = 0
    skipped = 0
    errors = 0

    try:
        with conn.cursor() as cur:
            # ── Resolve all kode_pt → perguruan_tinggi_id up front ──
            kode_pt_set = {item["kode_pt"] for item in items}
            placeholders = ",".join(["%s"] * len(kode_pt_set))
            cur.execute(
                f"SELECT id, kode_pt FROM universities_perguruantinggi "
                f"WHERE kode_pt IN ({placeholders})",
                list(kode_pt_set),
            )
            pt_map = {row["kode_pt"]: row["id"] for row in cur.fetchall()}

            for item in items:
                kode_pt   = item.get("kode_pt", "").strip()
                kode_prodi = item.get("Kode", "").strip()
                nama       = item.get("Nama Program Studi", "").strip()
                jenjang    = map_jenjang(item.get("Jenjang", ""))
                akreditasi = map_akreditasi(item.get("Akreditasi", ""))
                is_active  = item.get("Status", "").strip().upper() == "AKTIF"

                pt_id = pt_map.get(kode_pt)
                if pt_id is None:
                    print(f"  [SKIP] kode_pt={kode_pt!r} not found in universities_perguruantinggi")
                    skipped += 1
                    continue

                # Check existence: unique_together (perguruan_tinggi_id, kode_prodi)
                cur.execute(
                    "SELECT id FROM universities_programstudi "
                    "WHERE perguruan_tinggi_id = %s AND kode_prodi = %s",
                    (pt_id, kode_prodi),
                )
                if cur.fetchone():
                    print(f"  [SKIP] {kode_pt}/{kode_prodi} ({nama}) already exists")
                    skipped += 1
                    continue

                if dry_run:
                    print(f"  [DRY]  INSERT {kode_pt}/{kode_prodi} — {nama} [{jenjang}] akr={akreditasi}")
                    inserted += 1
                    continue

                try:
                    cur.execute(
                        "INSERT INTO universities_programstudi "
                        "(kode_prodi, nama, jenjang, akreditasi, is_active, "
                        " perguruan_tinggi_id, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (kode_prodi, nama, jenjang, akreditasi, is_active,
                         pt_id, now, now),
                    )
                    print(f"  [INS]  {kode_pt}/{kode_prodi} — {nama} [{jenjang}]")
                    inserted += 1
                except pymysql.Error as e:
                    print(f"  [ERR]  {kode_pt}/{kode_prodi}: {e}")
                    errors += 1

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    label = "(dry run) " if dry_run else ""
    print(f"\n{label}Done — inserted: {inserted}, skipped: {skipped}, errors: {errors}")


def main() -> None:
    default_file = str(
        Path(__file__).resolve().parent / "outs" / "071024_programstudi.json"
    )
    parser = argparse.ArgumentParser(description="Update universities_programstudi from JSON")
    parser.add_argument("--file", default=default_file, help="Path to programstudi JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    run(args.file, args.dry_run)


if __name__ == "__main__":
    main()
