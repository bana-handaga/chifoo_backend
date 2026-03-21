#!/usr/bin/env python3
"""
Update universities_programstudi table from a PDDikti pelaporan JSON file.

Format input (outs/[kode_pt]_pelaporan.json):
    {
        "kode_pt": "051007",
        "nama_pt": "...",
        "jumlah_semester": N,
        "pelaporan": [
            {
                "semester": "Ganjil 2025",
                "program_studi": [ { "Kode": ..., "Nama Program Studi": ..., ... } ]
            },
            ...
        ]
    }

Data program studi diambil dari semester terbaru (index 0).

Usage:
    python update_programstudi.py [--file PATH] [--dry-run]

    # Preview tanpa menulis ke DB
    python3 utils/update_programstudi.py --dry-run

    # File default (051007_pelaporan.json)
    python3 utils/update_programstudi.py

    # File lain
    python3 utils/update_programstudi.py --file utils/outs/061008_pelaporan.json
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
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
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
    "SP-1": "profesi",
    "SP-2": "profesi",
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


def run(json_path: str, dry_run: bool, semester: str | None = None) -> None:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        print("JSON file is empty.")
        return

    # ── Parse format pelaporan ──────────────────────────────────
    kode_pt = data.get("kode_pt", "").strip()
    nama_pt = data.get("nama_pt", "")
    pelaporan = data.get("pelaporan", [])

    if not pelaporan:
        print("Tidak ada data pelaporan dalam file.")
        return

    # Pilih semester berdasarkan input, atau gunakan yang terbaru (index 0)
    if semester:
        match = next(
            (s for s in pelaporan if s.get("semester", "").strip().lower() == semester.strip().lower()),
            None,
        )
        if match is None:
            tersedia = [s.get("semester", "") for s in pelaporan]
            print(f"[ERROR] Semester {semester!r} tidak ditemukan. Tersedia: {tersedia}", file=sys.stderr)
            return
        semester_dipilih = match
    else:
        semester_dipilih = pelaporan[0]

    semester_label = semester_dipilih.get("semester", "")
    all_items      = semester_dipilih.get("program_studi", [])

    print(f"PT     : {nama_pt} ({kode_pt})")
    print(f"Semester: {semester_label} ({len(all_items)} prodi)")

    total = len(all_items)
    items = [i for i in all_items if i.get("Status", "").strip().upper() == "AKTIF"]
    print(f"Loaded {total} items, {len(items)} aktif (others ignored)")

    conn = pymysql.connect(**DB_CONFIG)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    inserted = 0
    skipped = 0
    errors = 0

    try:
        with conn.cursor() as cur:
            # ── Resolve kode_pt → perguruan_tinggi_id ──────────────
            cur.execute(
                "SELECT id, kode_pt FROM universities_perguruantinggi "
                "WHERE kode_pt = %s",
                (kode_pt,),
            )
            row = cur.fetchone()
            if row is None:
                print(f"[ERROR] kode_pt={kode_pt!r} tidak ditemukan di universities_perguruantinggi")
                return
            pt_id = row["id"]

            for item in items:
                kode_prodi = item.get("Kode", "").strip()
                nama       = item.get("Nama Program Studi", "").strip()
                jenjang    = map_jenjang(item.get("Jenjang", ""))
                akreditasi = map_akreditasi(item.get("Akreditasi", ""))
                is_active  = item.get("Status", "").strip().upper() == "AKTIF"

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
        Path(__file__).resolve().parent / "outs" / "051007_pelaporan.json"
    )
    parser = argparse.ArgumentParser(description="Update universities_programstudi from JSON")
    parser.add_argument("--file", default=default_file, help="Path to pelaporan JSON file")
    parser.add_argument("--semester", default=None, help='Semester yang digunakan, misal "Ganjil 2025". Default: semester terbaru')
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    run(args.file, args.dry_run, args.semester)


if __name__ == "__main__":
    main()
