"""
Import SINTA WCU Tahunan → SintaWcuTahunan

Sumber JSON:
  - outs/wcu/{kode}_wcu.json

Usage:
  cd chifoo_backend
  python utils/sinta/sp_import_sinta_wcu.py
  python utils/sinta/sp_import_sinta_wcu.py --kode 061008
  python utils/sinta/sp_import_sinta_wcu.py --dry-run
"""

import argparse
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.production")

import django
django.setup()

from apps.universities.models import SintaAfiliasi, SintaWcuTahunan

WCU_DIR = Path(__file__).parent / "outs" / "wcu"

SUBJECTS = [
    "arts_humanities",
    "engineering_technology",
    "life_sciences_medicine",
    "natural_sciences",
    "social_sciences_management",
    "overall",
]


def main():
    parser = argparse.ArgumentParser(description="Import SINTA WCU Tahunan ke DB")
    parser.add_argument("--kode",    default="", help="Filter satu PT (e.g. 061008)")
    parser.add_argument("--dry-run", action="store_true", help="Preview tanpa write ke DB")
    args = parser.parse_args()

    files = sorted(WCU_DIR.glob("*_wcu.json"))
    created = updated = skipped = errors = 0

    print(f"Total file WCU: {len(files)}")

    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)

            kode_pt = data.get("kode_pt", f.stem.replace("_wcu", ""))
            if args.kode and kode_pt != args.kode:
                continue

            pps = data.get("paper_per_subject", {})
            # Skip jika semua subject kosong
            if not any(pps.get(s) for s in SUBJECTS):
                continue

            try:
                afiliasi = SintaAfiliasi.objects.get(perguruan_tinggi__kode_pt=kode_pt)
            except SintaAfiliasi.DoesNotExist:
                print(f"  SKIP {kode_pt}: SintaAfiliasi tidak ditemukan")
                skipped += 1
                continue

            # Kumpulkan semua tahun dari semua subject
            all_years = set()
            for s in SUBJECTS:
                all_years.update(pps.get(s, {}).keys())

            for tahun_str in sorted(all_years):
                tahun = int(tahun_str)
                defaults = {s: int(pps.get(s, {}).get(tahun_str, 0)) for s in SUBJECTS}

                if dry_run := args.dry_run:
                    print(f"  [DRY] {kode_pt} {tahun}: overall={defaults.get('overall', 0)}")
                    continue

                obj, is_new = SintaWcuTahunan.objects.update_or_create(
                    afiliasi=afiliasi,
                    tahun=tahun,
                    defaults=defaults,
                )
                if is_new:
                    created += 1
                else:
                    updated += 1

            print(f"  OK {kode_pt} — {len(all_years)} tahun")

        except Exception as e:
            print(f"  ERROR {f.name}: {e}")
            errors += 1

    print(f"\n=== Selesai ===")
    print(f"  Created : {created}")
    print(f"  Updated : {updated}")
    print(f"  Skipped : {skipped}")
    print(f"  Errors  : {errors}")


if __name__ == "__main__":
    main()
