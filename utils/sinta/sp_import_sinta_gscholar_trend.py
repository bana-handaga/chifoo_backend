"""
Script  : sp_import_sinta_gscholar_trend.py
Deskripsi: Import tren publikasi & sitasi Google Scholar dari JSON ke
           tabel universities_sintaauthortrend
           (jenis = 'gscholar_pub' dan 'gscholar_cite')

Input   : utils/sinta/outs/gscholar_trend/{kode_pt}/{sinta_id}_trend.json

Pola    : update_or_create berdasarkan (author, jenis, tahun) → idempoten

Usage:
  cd chifoo_backend
  python utils/sinta/sp_import_sinta_gscholar_trend.py
  python utils/sinta/sp_import_sinta_gscholar_trend.py --dry-run
  python utils/sinta/sp_import_sinta_gscholar_trend.py --sinta-id 6005631
  python utils/sinta/sp_import_sinta_gscholar_trend.py --status
"""

import argparse
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")

import django
django.setup()

from apps.universities.models import SintaAuthor, SintaAuthorTrend

IN_BASE = BASE_DIR / "utils" / "sinta" / "outs" / "gscholar"


def all_json_files() -> list[Path]:
    return sorted(IN_BASE.glob("*/*_trend.json"))


def status():
    files      = all_json_files()
    pub_rows   = SintaAuthorTrend.objects.filter(jenis="gscholar_pub").count()
    cite_rows  = SintaAuthorTrend.objects.filter(jenis="gscholar_cite").count()
    print(f"File JSON tersedia        : {len(files)}")
    print(f"Trend gscholar_pub di DB  : {pub_rows:,}")
    print(f"Trend gscholar_cite di DB : {cite_rows:,}")


def import_file(json_file: Path, dry_run=False) -> tuple[int, int, int]:
    data     = json.loads(json_file.read_text(encoding="utf-8"))
    sinta_id = data.get("sinta_id", "")
    trend    = data.get("trend", [])

    if not trend:
        return 0, 0, 0

    try:
        author = SintaAuthor.objects.get(sinta_id=sinta_id)
    except SintaAuthor.DoesNotExist:
        return 0, len(trend) * 2, 0

    ok = skip = err = 0

    for row in trend:
        tahun = row.get("tahun")
        pub   = row.get("pub", 0)
        cite  = row.get("cite", 0)

        if not tahun:
            skip += 2
            continue

        if dry_run:
            ok += 2
            continue

        for jenis, jumlah in [("gscholar_pub", pub), ("gscholar_cite", cite)]:
            if jumlah == 0:
                skip += 1
                continue
            try:
                SintaAuthorTrend.objects.update_or_create(
                    author=author, jenis=jenis, tahun=tahun,
                    defaults={"jumlah": jumlah}
                )
                ok += 1
            except Exception as e:
                print(f"    ERROR {sinta_id} {jenis} {tahun}: {e}")
                err += 1

    return ok, skip, err


def run(files: list[Path], dry_run=False):
    total_ok = total_skip = total_err = 0

    for i, f in enumerate(files, 1):
        sinta_id = f.stem.replace("_trend", "")
        ok, skip, err = import_file(f, dry_run=dry_run)
        total_ok   += ok
        total_skip += skip
        total_err  += err

        if ok > 0 or err > 0:
            tag = "[DRY] " if dry_run else ""
            print(f"  [{i}/{len(files)}] {sinta_id} {tag}ok={ok} skip={skip} err={err}")

        if i % 500 == 0:
            print(f"\n  --- [{i}/{len(files)}] ok={total_ok} skip={total_skip} err={total_err} ---\n")

    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"\n{prefix}Selesai: {total_ok} imported, {total_skip} dilewati, {total_err} error.")
    if not dry_run:
        pub  = SintaAuthorTrend.objects.filter(jenis="gscholar_pub").count()
        cite = SintaAuthorTrend.objects.filter(jenis="gscholar_cite").count()
        print(f"Total gscholar_pub di DB  : {pub:,}")
        print(f"Total gscholar_cite di DB : {cite:,}")


def main():
    parser = argparse.ArgumentParser(description="Import Google Scholar trend ke DB")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--status",   action="store_true")
    parser.add_argument("--sinta-id", help="Import satu author saja")
    args = parser.parse_args()

    if args.status:
        status()
        return

    if args.sinta_id:
        files = list(IN_BASE.glob(f"*/{args.sinta_id}_trend.json"))
        if not files:
            print(f"File tidak ditemukan untuk sinta_id={args.sinta_id}")
            return
    else:
        files = all_json_files()
        print(f"File JSON ditemukan: {len(files)}")

    run(files, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
