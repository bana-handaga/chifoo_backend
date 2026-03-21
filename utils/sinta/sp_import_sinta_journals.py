"""
Import SINTA Jurnal → SintaJurnal

Sumber JSON:
  - outs/journals/{kode_pt}_journals.json

Usage:
  cd chifoo_backend
  python utils/sinta/sp_import_sinta_journals.py
  python utils/sinta/sp_import_sinta_journals.py --kode 061008
  python utils/sinta/sp_import_sinta_journals.py --dry-run
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

from apps.universities.models import PerguruanTinggi, SintaJurnal

JOURNALS_DIR = Path(__file__).parent / "outs" / "journals"


def main():
    parser = argparse.ArgumentParser(description="Import SINTA Jurnal ke DB")
    parser.add_argument("--kode",    default="", help="Filter satu PT (e.g. 061008)")
    parser.add_argument("--dry-run", action="store_true", help="Preview tanpa write ke DB")
    args = parser.parse_args()

    files = sorted(JOURNALS_DIR.glob("*_journals.json"))
    created = updated = skipped = errors = 0

    print(f"Total file jurnal: {len(files)}")

    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)

            kode_pt = data.get("kode_pt", f.stem.replace("_journals", ""))
            if args.kode and kode_pt != args.kode:
                continue

            journals = data.get("journals", [])
            if not journals:
                continue

            # Cari PerguruanTinggi
            try:
                pt = PerguruanTinggi.objects.get(kode_pt=kode_pt)
            except PerguruanTinggi.DoesNotExist:
                print(f"  SKIP {kode_pt}: PerguruanTinggi tidak ditemukan")
                skipped += 1
                continue

            pt_created = pt_updated = 0
            for j in journals:
                sinta_id = j.get("sinta_id")
                if not sinta_id:
                    continue

                defaults = {
                    "perguruan_tinggi": pt,
                    "nama":          j.get("nama", ""),
                    "p_issn":        j.get("p_issn", ""),
                    "e_issn":        j.get("e_issn", ""),
                    "akreditasi":    j.get("akreditasi", ""),
                    "subject_area":  j.get("subject_area", ""),
                    "afiliasi_teks": j.get("afiliasi_teks", ""),
                    "impact":        j.get("impact", 0.0),
                    "h5_index":      j.get("h5_index", 0),
                    "sitasi_5yr":    j.get("sitasi_5yr", 0),
                    "sitasi_total":  j.get("sitasi_total", 0),
                    "is_scopus":     j.get("is_scopus", False),
                    "is_garuda":     j.get("is_garuda", False),
                    "url_website":   j.get("url_website", ""),
                    "url_scholar":   j.get("url_scholar", ""),
                    "url_editor":    j.get("url_editor", ""),
                    "url_garuda":    j.get("url_garuda", ""),
                    "logo_base64":   j.get("logo_base64", ""),
                }

                if args.dry_run:
                    print(f"  [DRY] {kode_pt} — {j.get('nama','')} ({j.get('akreditasi','')})")
                    continue

                obj, is_new = SintaJurnal.objects.update_or_create(
                    sinta_id=sinta_id,
                    defaults=defaults,
                )
                if is_new:
                    pt_created += 1
                    created += 1
                else:
                    pt_updated += 1
                    updated += 1

            if not args.dry_run:
                print(f"  {kode_pt} ({pt.singkatan}) — created={pt_created} updated={pt_updated}")

        except Exception as e:
            print(f"  ERROR {f.name}: {e}")
            import traceback; traceback.print_exc()
            errors += 1

    print(f"\n=== Selesai ===")
    print(f"  Created : {created}")
    print(f"  Updated : {updated}")
    print(f"  Skipped : {skipped}")
    print(f"  Errors  : {errors}")
    print(f"  Total DB: {SintaJurnal.objects.count()}")


if __name__ == "__main__":
    main()
