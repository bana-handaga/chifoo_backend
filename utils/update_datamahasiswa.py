#!/usr/bin/env python3
"""
Update universities_datamahasiswa table dari file PDDikti pelaporan JSON.

Format input (outs/[kode_pt]_pelaporan.json):
    {
        "kode_pt": "051007",
        "nama_pt": "...",
        "jumlah_semester": N,
        "pelaporan": [
            {
                "semester": "Ganjil 2025",
                "program_studi": [ { "Kode": ..., "Jumlah Mahasiswa": ..., ... } ]
            },
            ...
        ]
    }

Untuk setiap program studi aktif pada periode yang dipilih:
  - Resolve kode_pt → perguruan_tinggi_id
  - Resolve kode_prodi → program_studi_id
  - Jika baris (pt_id, ps_id, tahun_akademik, semester) sudah ada → UPDATE mahasiswa_aktif
  - Jika belum ada → INSERT baris baru

tahun_akademik dan semester di-derive otomatis dari label periode:
    "Ganjil YYYY" → tahun_akademik=YYYY/YYYY+1, semester=ganjil
    "Genap YYYY"  → tahun_akademik=YYYY-1/YYYY,  semester=genap

Usage:
    python update_datamahasiswa.py [--file PATH] [--periode PERIODE] [--dry-run]

    # Preview semester terbaru
    python3 utils/update_datamahasiswa.py --dry-run

    # Periode tertentu
    python3 utils/update_datamahasiswa.py --periode "Genap 2024" --dry-run
"""

import argparse
import json
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

# ── Load .env ────────────────────────────────────────────────
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

def _derive_tahun_semester(periode_label: str) -> tuple[str, str]:
    """
    Derive (tahun_akademik, semester) dari label periode PDDikti.
      "Ganjil YYYY" → ("YYYY/YYYY+1", "ganjil")
      "Genap YYYY"  → ("YYYY/YYYY+1", "genap")
    YYYY selalu menjadi tahun pertama tahun akademik.
    """
    parts = periode_label.strip().split()
    if len(parts) != 2:
        raise ValueError(f"Format periode tidak dikenali: {periode_label!r}")
    tipe, tahun = parts[0].lower(), int(parts[1])
    if tipe not in ("ganjil", "genap"):
        raise ValueError(f"Tipe semester tidak dikenali: {tipe!r}")
    return f"{tahun}/{tahun + 1}", tipe


def run(json_path: str, periode: str | None, dry_run: bool) -> None:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        print("JSON file is empty.")
        return

    # ── Parse format pelaporan ──────────────────────────────────
    kode_pt   = data.get("kode_pt", "").strip()
    nama_pt   = data.get("nama_pt", "")
    pelaporan = data.get("pelaporan", [])

    if not pelaporan:
        print("Tidak ada data pelaporan dalam file.")
        return

    # Pilih periode dari file
    if periode:
        match = next(
            (s for s in pelaporan if s.get("semester", "").strip().lower() == periode.strip().lower()),
            None,
        )
        if match is None:
            tersedia = [s.get("semester", "") for s in pelaporan]
            print(f"[ERROR] Periode {periode!r} tidak ditemukan. Tersedia: {tersedia}", file=sys.stderr)
            return
        dipilih = match
    else:
        dipilih = pelaporan[0]

    periode_label = dipilih.get("semester", "")
    all_items     = dipilih.get("program_studi", [])

    # Derive tahun_akademik dan semester dari label periode
    try:
        tahun_akademik, semester = _derive_tahun_semester(periode_label)
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return

    total = len(all_items)
    items = [i for i in all_items if i.get("Status", "").strip().upper() == "AKTIF"]

    print(f"PT      : {nama_pt} ({kode_pt})")
    print(f"Periode : {periode_label}  →  tahun_akademik={tahun_akademik!r}, semester={semester!r}")
    print(f"Loaded {total} items, {len(items)} aktif (others ignored)\n")

    conn = pymysql.connect(**DB_CONFIG)

    updated = 0
    inserted = 0
    skipped = 0
    errors = 0

    try:
        with conn.cursor() as cur:
            # ── Resolve kode_pt → perguruan_tinggi_id ────────────
            cur.execute(
                "SELECT id FROM universities_perguruantinggi WHERE kode_pt = %s",
                (kode_pt,),
            )
            pt_row = cur.fetchone()
            if pt_row is None:
                print(f"[ERROR] kode_pt={kode_pt!r} tidak ditemukan di universities_perguruantinggi")
                return
            pt_id = pt_row["id"]

            for item in items:
                kode_prodi = item.get("Kode", "").strip()
                nama_ps    = item.get("Nama Program Studi", "").strip()

                try:
                    mhs_aktif = int(item.get("Jumlah Mahasiswa", 0))
                except (ValueError, TypeError):
                    mhs_aktif = 0

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
        Path(__file__).resolve().parent / "outs" / "051007_pelaporan.json"
    )
    parser = argparse.ArgumentParser(
        description="Update universities_datamahasiswa dari file pelaporan JSON"
    )
    parser.add_argument("--file",    default=default_file, help="Path ke file pelaporan JSON")
    parser.add_argument("--periode", default=None,
                        help='Periode semester dari file, misal "Ganjil 2025". Default: semester terbaru')
    parser.add_argument("--dry-run", action="store_true",  help="Preview tanpa menulis ke DB")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"File tidak ditemukan: {args.file}", file=sys.stderr)
        sys.exit(1)

    run(args.file, args.periode, args.dry_run)


if __name__ == "__main__":
    main()

