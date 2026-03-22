"""
Script  : sp_import_sinta_departments.py
Deskripsi: Import data departemen SINTA dari JSON ke database Django
           (tabel universities_sintadepartemen)

Input   : utils/sinta/outs/departments/{kode_pt}_departments.json
          → hasil scrape dari scrape_sinta_departments.py

Pola    : hapus semua departemen PT yang lama, lalu insert ulang dari JSON
          (lebih aman daripada update_or_create karena kode_dept bisa berubah)

Usage:
  cd chifoo_backend
  python utils/sinta/sp_import_sinta_departments.py
  python utils/sinta/sp_import_sinta_departments.py --dry-run
  python utils/sinta/sp_import_sinta_departments.py --kode 061008
  python utils/sinta/sp_import_sinta_departments.py --status
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")

import django
django.setup()

from apps.universities.models import SintaAfiliasi, SintaDepartemen

# ---------------------------------------------------------------------------
INPUT_DIR = BASE_DIR / "utils" / "sinta" / "outs" / "departments"
# ---------------------------------------------------------------------------


def import_file(json_file: Path, dry_run=False):
    data = json.loads(json_file.read_text())
    kode_pt  = data.get("kode_pt", "")
    sinta_id = data.get("sinta_id_afiliasi", "")
    depts    = data.get("departments", [])

    try:
        afiliasi = SintaAfiliasi.objects.get(sinta_kode=kode_pt)
    except SintaAfiliasi.DoesNotExist:
        print(f"  SKIP {kode_pt}: SintaAfiliasi tidak ditemukan di database")
        return 0

    if dry_run:
        print(f"  DRY-RUN {kode_pt}: akan import {len(depts)} departemen")
        return len(depts)

    # Hapus data lama, insert ulang
    old_count = afiliasi.departemen.count()
    afiliasi.departemen.all().delete()

    # Deduplikasi berdasarkan kode_dept (data terakhir menimpa yang sebelumnya)
    seen_kode = {}   # kode_dept → index dalam objs
    objs = []
    for d in depts:
        if not d.get("nama"):
            continue
        kode = d.get("kode_dept", "")
        if kode and kode in seen_kode:
            # Timpa dengan data yang lebih baru
            objs[seen_kode[kode]] = None
        if kode:
            seen_kode[kode] = len(objs)
        objs.append(SintaDepartemen(
            afiliasi            = afiliasi,
            nama                = d.get("nama", ""),
            jenjang             = d.get("jenjang", ""),
            kode_dept           = kode,
            url_profil          = d.get("url_profil", ""),
            sinta_score_overall = d.get("sinta_score_overall", 0),
            sinta_score_3year   = d.get("sinta_score_3year", 0),
            jumlah_authors      = d.get("jumlah_authors", 0),
        ))

    objs = [o for o in objs if o is not None]
    SintaDepartemen.objects.bulk_create(objs, ignore_conflicts=True)
    print(f"  {kode_pt} ({afiliasi.perguruan_tinggi.singkatan}): "
          f"{old_count} lama → {len(objs)} baru")
    return len(objs)


def cmd_status():
    files = sorted(INPUT_DIR.glob("*/departments.json"))
    total = SintaDepartemen.objects.count()
    print(f"File JSON  : {len(files)} PT")
    print(f"Database   : {total} departemen\n")
    if files:
        print(f"{'Kode PT':<10} {'JSON':>6}  {'DB':>6}  Nama PT")
        print("-" * 60)
        for f in files[:20]:
            data = json.loads(f.read_text())
            kode = data.get("kode_pt", "?")
            n_json = len(data.get("departments", []))
            try:
                aff  = SintaAfiliasi.objects.get(sinta_kode=kode)
                n_db = aff.departemen.count()
                nama = aff.perguruan_tinggi.singkatan
            except SintaAfiliasi.DoesNotExist:
                n_db, nama = "?", "—"
            print(f"  {kode:<10} {n_json:>6}  {str(n_db):>6}  {nama}")
        if len(files) > 20:
            print(f"  ... dan {len(files) - 20} PT lainnya")


def main():
    parser = argparse.ArgumentParser(description="Import SINTA Departments ke database")
    parser.add_argument("--kode",    help="Filter kode PT (e.g. 061008)")
    parser.add_argument("--dry-run", action="store_true", help="Simulasi tanpa menyimpan")
    parser.add_argument("--status",  action="store_true", help="Tampilkan ringkasan")
    args = parser.parse_args()

    if args.status:
        cmd_status()
        return

    if not INPUT_DIR.exists():
        print(f"Folder input tidak ditemukan: {INPUT_DIR}")
        sys.exit(1)

    if args.kode:
        f = INPUT_DIR / args.kode / "departments.json"
        if not f.exists():
            print(f"File {args.kode}/departments.json tidak ditemukan.")
            sys.exit(1)
        files = [f]
    else:
        files = sorted(INPUT_DIR.glob("*/departments.json"))

    print(f"Memproses {len(files)} file JSON...\n")
    total_imported = 0

    for f in files:
        total_imported += import_file(f, dry_run=args.dry_run)

    print(f"\nSelesai: {total_imported} departemen {'akan ' if args.dry_run else ''}diimport.")
    if not args.dry_run:
        print(f"Total di database: {SintaDepartemen.objects.count()} departemen")


if __name__ == "__main__":
    main()
