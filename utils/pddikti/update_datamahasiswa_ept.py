#!/usr/bin/env python3
"""
Update universities_datamahasiswa dari file utils/ept/ept_itms.json.

Format input (Django fixture):
    [
        {
            "model": "ept.itms",
            "pk": 1,
            "fields": {
                "kodept":   "064167",
                "kodeps":   "13462",
                "semester": "2025/2026 Ganjil",
                "jumlah":   148,
                ...
            }
        },
        ...
    ]

Mapping field:
    fields.kodept   → universities_perguruantinggi.kode_pt  → perguruan_tinggi_id
    fields.kodeps   → universities_programstudi.kode_prodi  → program_studi_id
    fields.semester → "YYYY/YYYY+1 Ganjil|Genap"
                      → tahun_akademik = "YYYY/YYYY+1"
                      → semester       = "ganjil" | "genap"
    fields.jumlah   → mahasiswa_aktif

Usage:
    # Lihat daftar semester yang tersedia
    python3 utils/update_datamahasiswa_ept.py --list-semesters

    # Preview semester terbaru (tanpa tulis ke DB)
    python3 utils/update_datamahasiswa_ept.py --dry-run

    # Periode tertentu
    python3 utils/update_datamahasiswa_ept.py --periode "2025/2026 Ganjil" --dry-run

    # Jalankan (tulis ke DB)
    python3 utils/update_datamahasiswa_ept.py --periode "2025/2026 Ganjil"
"""

import argparse
import json
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

# ── Load .env ─────────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
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

EPT_FILE = Path(__file__).resolve().parent / "ept" / "ept_itms.json"


def parse_semester(raw: str) -> tuple[str, str]:
    """
    "2025/2026 Ganjil" → ("2025/2026", "ganjil")
    "2024/2025 Genap"  → ("2024/2025", "genap")
    """
    parts = raw.strip().rsplit(" ", 1)
    if len(parts) != 2:
        raise ValueError(f"Format semester tidak dikenali: {raw!r}")
    tahun_akademik, tipe = parts[0], parts[1].lower()
    if tipe not in ("ganjil", "genap"):
        raise ValueError(f"Tipe semester tidak dikenali: {tipe!r}")
    return tahun_akademik, tipe


def load_data(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return [r["fields"] for r in raw if r.get("model") == "ept.itms"]


def list_semesters(records: list[dict]) -> None:
    semesters = sorted(set(r["semester"] for r in records), reverse=True)
    print(f"Tersedia {len(semesters)} semester:")
    for s in semesters:
        count = sum(1 for r in records if r["semester"] == s)
        print(f"  {s:30s}  ({count} prodi)")


def run(periode: str | None, dry_run: bool) -> None:
    records = load_data(EPT_FILE)

    # Pilih semester
    available = sorted(set(r["semester"] for r in records), reverse=True)
    if periode:
        target = periode.strip()
        if target not in available:
            print(f"[ERROR] Periode {target!r} tidak ditemukan.", file=sys.stderr)
            print(f"Tersedia: {available}", file=sys.stderr)
            sys.exit(1)
    else:
        target = available[0]   # terbaru

    # Parse tahun_akademik & semester DB
    try:
        tahun_akademik, semester = parse_semester(target)
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    items = [r for r in records if r["semester"] == target]
    print(f"Periode  : {target}  →  tahun_akademik={tahun_akademik!r}, semester={semester!r}")
    print(f"Records  : {len(items)} prodi dari {len(set(r['kodept'] for r in items))} PT\n")

    conn = pymysql.connect(**DB_CONFIG)
    updated = inserted = skipped = errors = 0

    # Cache kodept → pt_id agar tidak query berulang
    pt_cache: dict[str, int | None] = {}

    try:
        with conn.cursor() as cur:
            for item in items:
                kodept = item.get("kodept", "").strip()
                kodeps = item.get("kodeps", "").strip()
                jumlah = item.get("jumlah", 0)
                try:
                    mhs_aktif = int(jumlah)
                except (ValueError, TypeError):
                    mhs_aktif = 0

                # ── Resolve kodept → pt_id ────────────────────────
                if kodept not in pt_cache:
                    cur.execute(
                        "SELECT id FROM universities_perguruantinggi WHERE kode_pt = %s",
                        (kodept,),
                    )
                    row = cur.fetchone()
                    pt_cache[kodept] = row["id"] if row else None

                pt_id = pt_cache[kodept]
                if pt_id is None:
                    print(f"  [SKIP] kodept={kodept!r} tidak ditemukan di DB")
                    skipped += 1
                    continue

                # ── Resolve kodeps → ps_id ────────────────────────
                cur.execute(
                    "SELECT id FROM universities_programstudi "
                    "WHERE perguruan_tinggi_id = %s AND kode_prodi = %s",
                    (pt_id, kodeps),
                )
                ps_row = cur.fetchone()
                if ps_row is None:
                    print(f"  [SKIP] {kodept}/{kodeps} tidak ditemukan di universities_programstudi")
                    skipped += 1
                    continue
                ps_id = ps_row["id"]

                # ── Cek existing DataMahasiswa ─────────────────────
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
                            f"  [DRY]  UPDATE {kodept}/{kodeps} "
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
                        if existing["mahasiswa_aktif"] != mhs_aktif:
                            print(
                                f"  [UPD]  {kodept}/{kodeps} "
                                f"mahasiswa_aktif: {existing['mahasiswa_aktif']} → {mhs_aktif}"
                            )
                        updated += 1
                    except pymysql.Error as e:
                        print(f"  [ERR]  UPDATE {kodept}/{kodeps}: {e}")
                        errors += 1
                else:
                    if dry_run:
                        print(
                            f"  [DRY]  INSERT {kodept}/{kodeps} mahasiswa_aktif={mhs_aktif}"
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
                        print(f"  [INS]  {kodept}/{kodeps} mahasiswa_aktif={mhs_aktif}")
                        inserted += 1
                    except pymysql.Error as e:
                        print(f"  [ERR]  INSERT {kodept}/{kodeps}: {e}")
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
    parser = argparse.ArgumentParser(
        description="Update universities_datamahasiswa dari ept_itms.json"
    )
    parser.add_argument(
        "--periode", default=None,
        help='Semester target, misal "2025/2026 Ganjil". Default: semester terbaru.'
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview perubahan tanpa menulis ke DB."
    )
    parser.add_argument(
        "--list-semesters", action="store_true",
        help="Tampilkan daftar semester yang tersedia lalu keluar."
    )
    args = parser.parse_args()

    if args.list_semesters:
        list_semesters(load_data(EPT_FILE))
        return

    run(args.periode, args.dry_run)


if __name__ == "__main__":
    main()
