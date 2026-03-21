"""
Script  : sp_import_sinta_afiliasi.py
Deskripsi: Import data SINTA Afiliasi dari JSON ke database Django
           (tabel universities_sintaafiliasi)

Input   : utils/outs/sinta_afiliasi.json
           → hasil scrape dari scrape_sinta_afiliasi.py

Pola    : update_or_create berdasarkan perguruan_tinggi (kode_pt)
           → data lama ditimpa, data baru ditambah

Usage:
  cd chifoo_backend
  python utils/sinta/sp_import_sinta_afiliasi.py
  python utils/sinta/sp_import_sinta_afiliasi.py --dry-run
  python utils/sinta/sp_import_sinta_afiliasi.py --kode 061008
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

from apps.universities.models import PerguruanTinggi, SintaAfiliasi

# ---------------------------------------------------------------------------
INPUT_FILE = BASE_DIR / "utils" / "outs" / "sinta_afiliasi.json"
# ---------------------------------------------------------------------------


def import_data(data: dict, dry_run=False, filter_kode=""):
    created = updated = skipped = not_found = 0

    for kode, item in data.items():
        if filter_kode and kode != filter_kode:
            continue

        # Skip entri yang tidak ditemukan di SINTA
        if not item.get("sinta_id"):
            print(f"  SKIP {kode}: tidak ditemukan di SINTA")
            not_found += 1
            continue

        # Cari PerguruanTinggi
        try:
            pt = PerguruanTinggi.objects.get(kode_pt=kode)
        except PerguruanTinggi.DoesNotExist:
            print(f"  SKIP {kode}: kode_pt tidak ada di DB")
            not_found += 1
            continue

        fields = {
            "sinta_id":         item.get("sinta_id", ""),
            "sinta_kode":       item.get("sinta_kode", ""),
            "nama_sinta":       item.get("nama", ""),
            "singkatan_sinta":  item.get("singkatan", ""),
            "lokasi_sinta":     item.get("lokasi", ""),
            "sinta_profile_url": item.get("sinta_profile_url", ""),
            "logo_base64":      item.get("logo_base64", ""),

            "jumlah_authors":     int(item.get("jumlah_authors", 0) or 0),
            "jumlah_departments": int(item.get("jumlah_departments", 0) or 0),
            "jumlah_journals":    int(item.get("jumlah_journals", 0) or 0),

            "sinta_score_overall":            int(item.get("sinta_score_overall", 0) or 0),
            "sinta_score_3year":              int(item.get("sinta_score_3year", 0) or 0),
            "sinta_score_productivity":       int(item.get("sinta_score_productivity", 0) or 0),
            "sinta_score_productivity_3year": int(item.get("sinta_score_productivity_3year", 0) or 0),

            "scopus_dokumen":             float(item.get("scopus_dokumen", 0) or 0),
            "scopus_sitasi":              float(item.get("scopus_sitasi", 0) or 0),
            "scopus_dokumen_disitasi":    float(item.get("scopus_dokumen_disitasi", 0) or 0),
            "scopus_sitasi_per_peneliti": float(item.get("scopus_sitasi_per_peneliti", 0) or 0),

            "gscholar_dokumen":             float(item.get("gscholar_dokumen", 0) or 0),
            "gscholar_sitasi":              float(item.get("gscholar_sitasi", 0) or 0),
            "gscholar_dokumen_disitasi":    float(item.get("gscholar_dokumen_disitasi", 0) or 0),
            "gscholar_sitasi_per_peneliti": float(item.get("gscholar_sitasi_per_peneliti", 0) or 0),

            "wos_dokumen":             float(item.get("wos_dokumen", 0) or 0),
            "wos_sitasi":              float(item.get("wos_sitasi", 0) or 0),
            "wos_dokumen_disitasi":    float(item.get("wos_dokumen_disitasi", 0) or 0),
            "wos_sitasi_per_peneliti": float(item.get("wos_sitasi_per_peneliti", 0) or 0),

            "garuda_dokumen":             float(item.get("garuda_dokumen", 0) or 0),
            "garuda_sitasi":              float(item.get("garuda_sitasi", 0) or 0),
            "garuda_dokumen_disitasi":    float(item.get("garuda_dokumen_disitasi", 0) or 0),
            "garuda_sitasi_per_peneliti": float(item.get("garuda_sitasi_per_peneliti", 0) or 0),

            "scopus_q1":  int(item.get("scopus_q1", 0) or 0),
            "scopus_q2":  int(item.get("scopus_q2", 0) or 0),
            "scopus_q3":  int(item.get("scopus_q3", 0) or 0),
            "scopus_q4":  int(item.get("scopus_q4", 0) or 0),
            "scopus_noq": int(item.get("scopus_noq", 0) or 0),

            "sinta_last_update": item.get("sinta_last_update", ""),
        }

        if dry_run:
            print(f"  [DRY] {kode} — {pt.singkatan}: score={fields['sinta_score_overall']:,} "
                  f"scopus={fields['scopus_dokumen']:.0f}dok q1={fields['scopus_q1']}")
            created += 1
            continue

        _, is_created = SintaAfiliasi.objects.update_or_create(
            perguruan_tinggi=pt,
            defaults=fields,
        )
        status = "CREATE" if is_created else "UPDATE"
        print(f"  [{status}] {kode} — {pt.singkatan}: score={fields['sinta_score_overall']:,} "
              f"scopus={fields['scopus_dokumen']:.0f}dok")
        if is_created:
            created += 1
        else:
            updated += 1

    return created, updated, skipped, not_found


def main():
    parser = argparse.ArgumentParser(description="Import SINTA Afiliasi JSON → DB")
    parser.add_argument("--dry-run", action="store_true", help="Simulasi tanpa menyimpan ke DB")
    parser.add_argument("--kode",    default="", help="Filter satu PT berdasarkan kode")
    args = parser.parse_args()

    if not INPUT_FILE.exists():
        print(f"[ERROR] File tidak ditemukan: {INPUT_FILE}")
        print("Jalankan scraper dulu: python utils/sinta/scrape_sinta_afiliasi.py")
        sys.exit(1)

    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    total = len(data)
    print(f"Input  : {INPUT_FILE}")
    print(f"Total  : {total} entri")
    if args.dry_run:
        print("Mode   : DRY RUN (tidak menyimpan ke DB)")
    print()

    created, updated, skipped, not_found = import_data(
        data, dry_run=args.dry_run, filter_kode=args.kode
    )

    print()
    print("=" * 50)
    print(f"  Dibuat  : {created}")
    print(f"  Diupdate: {updated}")
    print(f"  Skip    : {skipped}")
    print(f"  Tdk ada : {not_found} (tidak ditemukan di SINTA atau DB)")
    print("=" * 50)


if __name__ == "__main__":
    main()
