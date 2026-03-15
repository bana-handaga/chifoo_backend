#!/usr/bin/env python3
"""
Update universities_datamahasiswa table from a PDDikti programstudi JSON file.

Untuk setiap program studi aktif di file JSON:
  - Cari perguruan_tinggi_id dari universities_perguruantinggi berdasarkan kode_pt
  - Cari program_studi_id dari universities_programstudi berdasarkan kode_prodi
  - Jika baris (pt_id, ps_id, tahun_akademik, semester) sudah ada → UPDATE mahasiswa_aktif
  - Jika belum ada → INSERT baris baru dengan mahasiswa_aktif dari field 'Jumlah Mahasiswa'

Usage:
    python update_datamahasiswa.py [--file PATH] [--tahun TAHUN] [--semester SEMESTER] [--dry-run]

Defaults:
    --file      ~/projects/utils/outs/071024_programstudi.json
    --tahun     2025/2026
    --semester  ganjil
"""

import argparse
import json
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

# ── Load .env from backend dir ───────────────────────────────
ENV_PATH = Path(__file__).resolve().parent.parent / "backend" / ".env"
load_dotenv(ENV_PATH)

DB_CONFIG = {
    "host":        os.environ.get("DB_HOST", "localhost"),
    "port":        int(os.environ.get("DB_PORT", 3306)),
    "user":        os.environ.get("DB_USER", "root"),
    "password":    os.environ.get("DB_PASSWORD", ""),
    "db":          os.environ.get("DB_NAME", "ptma_db"),
    "charset":     "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

VALID_SEMESTER = {"ganjil", "genap"}


def run(json_path: str, tahun_akademik: str, semester: str, dry_run: bool) -> None:
    with open(json_path, encoding="utf-8") as f:
        items = json.load(f)

    if not items:
        print("JSON file is empty.")
        return

    total = len(items)
    items = [i for i in items if i.get("Status", "").strip().upper() == "AKTIF"]
    print(f"Loaded {total} items, {len(items)} aktif (others ignored)")
    print(f"Target: tahun_akademik={tahun_akademik!r}, semester={semester!r}\n")

    conn = pymysql.connect(**DB_CONFIG)

    updated = 0
    inserted = 0
    skipped = 0
    errors = 0

    try:
        with conn.cursor() as cur:
            # ── Resolve kode_pt → perguruan_tinggi_id ────────────
            kode_pt_set = {item["kode_pt"] for item in items}
            ph = ",".join(["%s"] * len(kode_pt_set))
            cur.execute(
                f"SELECT id, kode_pt FROM universities_perguruantinggi WHERE kode_pt IN ({ph})",
                list(kode_pt_set),
            )
            pt_map = {row["kode_pt"]: row["id"] for row in cur.fetchall()}

            for item in items:
                kode_pt    = item.get("kode_pt", "").strip()
                kode_prodi = item.get("Kode", "").strip()
                nama_ps    = item.get("Nama Program Studi", "").strip()

                try:
                    mhs_aktif = int(item.get("Jumlah Mahasiswa", 0))
                except (ValueError, TypeError):
                    mhs_aktif = 0

                # ── Lookup PT ────────────────────────────────────
                pt_id = pt_map.get(kode_pt)
                if pt_id is None:
                    print(f"  [SKIP] kode_pt={kode_pt!r} tidak ditemukan di universities_perguruantinggi")
                    skipped += 1
                    continue

                # ── Lookup Program Studi ──────────────────────────
                cur.execute(
                    "SELECT id FROM universities_programstudi "
                    "WHERE perguruan_tinggi_id = %s AND kode_prodi = %s",
                    (pt_id, kode_prodi),
                )
                ps_row = cur.fetchone()
                if ps_row is None:
                    print(f"  [SKIP] {kode_pt}/{kode_prodi} ({nama_ps}) tidak ditemukan di universities_programstudi")
                    skipped += 1
                    continue
                ps_id = ps_row["id"]

                # ── Cek baris DataMahasiswa ───────────────────────
                cur.execute(
                    "SELECT id, mahasiswa_aktif FROM universities_datamahasiswa "
                    "WHERE perguruan_tinggi_id = %s AND program_studi_id = %s "
                    "  AND tahun_akademik = %s AND semester = %s",
                    (pt_id, ps_id, tahun_akademik, semester),
                )
                existing = cur.fetchone()

                if existing:
                    if dry_run:
                        print(
                            f"  [DRY]  UPDATE {kode_pt}/{kode_prodi} ({nama_ps}) "
                            f"mahasiswa_aktif: {existing['mahasiswa_aktif']} → {mhs_aktif}"
                        )
                        updated += 1
                        continue
                    try:
                        cur.execute(
                            "UPDATE universities_datamahasiswa "
                            "SET mahasiswa_aktif = %s "
                            "WHERE id = %s",
                            (mhs_aktif, existing["id"]),
                        )
                        print(
                            f"  [UPD]  {kode_pt}/{kode_prodi} ({nama_ps}) "
                            f"mahasiswa_aktif: {existing['mahasiswa_aktif']} → {mhs_aktif}"
                        )
                        updated += 1
                    except pymysql.Error as e:
                        print(f"  [ERR]  UPDATE {kode_pt}/{kode_prodi}: {e}")
                        errors += 1
                else:
                    if dry_run:
                        print(
                            f"  [DRY]  INSERT {kode_pt}/{kode_prodi} ({nama_ps}) "
                            f"mahasiswa_aktif={mhs_aktif}"
                        )
                        inserted += 1
                        continue
                    try:
                        cur.execute(
                            "INSERT INTO universities_datamahasiswa "
                            "(tahun_akademik, semester, mahasiswa_baru, mahasiswa_aktif, "
                            " mahasiswa_lulus, mahasiswa_dropout, mahasiswa_pria, mahasiswa_wanita, "
                            " perguruan_tinggi_id, program_studi_id) "
                            "VALUES (%s, %s, 0, %s, 0, 0, 0, 0, %s, %s)",
                            (tahun_akademik, semester, mhs_aktif, pt_id, ps_id),
                        )
                        print(
                            f"  [INS]  {kode_pt}/{kode_prodi} ({nama_ps}) "
                            f"mahasiswa_aktif={mhs_aktif}"
                        )
                        inserted += 1
                    except pymysql.Error as e:
                        print(f"  [ERR]  INSERT {kode_pt}/{kode_prodi}: {e}")
                        errors += 1

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    label = "(dry run) " if dry_run else ""
    print(
        f"\n{label}Done — updated: {updated}, inserted: {inserted}, "
        f"skipped: {skipped}, errors: {errors}"
    )


def main() -> None:
    default_file = str(
        Path(__file__).resolve().parent / "outs" / "071024_programstudi.json"
    )
    parser = argparse.ArgumentParser(
        description="Update universities_datamahasiswa dari file programstudi JSON"
    )
    parser.add_argument("--file",     default=default_file, help="Path ke file JSON program studi")
    parser.add_argument("--tahun",    default="2025/2026",  help="Tahun akademik (default: 2025/2026)")
    parser.add_argument("--semester", default="ganjil",     choices=list(VALID_SEMESTER),
                        help="Semester: ganjil atau genap (default: ganjil)")
    parser.add_argument("--dry-run",  action="store_true",  help="Preview tanpa menulis ke DB")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"File tidak ditemukan: {args.file}", file=sys.stderr)
        sys.exit(1)

    run(args.file, args.tahun, args.semester, args.dry_run)


if __name__ == "__main__":
    main()

'''
Script update_datamahasiswa.py telah dibuat. Yang dilakukan:

Filter hanya item dengan Status = "Aktif"
Lookup perguruan_tinggi_id dari universities_perguruantinggi berdasarkan kode_pt
Lookup program_studi_id dari universities_programstudi berdasarkan (pt_id, kode_prodi)
Cek apakah baris (pt_id, ps_id, tahun_akademik, semester) sudah ada:
Sudah ada → UPDATE mahasiswa_aktif
Belum ada → INSERT baris baru (field lain default 0)
Nilai mahasiswa_aktif diambil dari field "Jumlah Mahasiswa" di JSON
Catatan: tahun_akademik default 2025/2026 (bukan 2005/2006 seperti di request — kemungkinan typo). Bisa diubah via --tahun.

Usage:


# Preview
python3 ~/projects/utils/update_datamahasiswa.py --dry-run

# Jalankan dengan default (tahun 2025/2026, semester ganjil)
python3 ~/projects/utils/update_datamahasiswa.py

# Tahun dan semester custom
python3 ~/projects/utils/update_datamahasiswa.py --tahun 2024/2025 --semester genap
'''