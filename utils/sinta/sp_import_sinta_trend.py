"""
Import SINTA Trend Tahunan → SintaTrendTahunan

Sumber JSON:
  - outs/publications/{kode}_pubhistory.json  → jenis='scopus'
  - outs/researches/{kode}_research.json      → jenis='research'
  - outs/services/{kode}_service.json         → jenis='service'

Usage:
  cd chifoo_backend
  python utils/sinta/sp_import_sinta_trend.py
  python utils/sinta/sp_import_sinta_trend.py --jenis scopus
  python utils/sinta/sp_import_sinta_trend.py --jenis research
  python utils/sinta/sp_import_sinta_trend.py --jenis service
  python utils/sinta/sp_import_sinta_trend.py --kode 061008
  python utils/sinta/sp_import_sinta_trend.py --dry-run
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.production")

import django
django.setup()

from apps.universities.models import SintaAfiliasi, SintaTrendTahunan

SINTA_DIR = Path(__file__).parent / "outs"

JENIS_CONFIG = {
    "scopus": {
        "dir":       SINTA_DIR / "publications",
        "glob":      "*_pubhistory.json",
        "history_key": "pub_history",
        "radar_key": None,
    },
    "research": {
        "dir":       SINTA_DIR / "researches",
        "glob":      "*_research.json",
        "history_key": "research_history",
        "radar_key": "research_radar",
    },
    "service": {
        "dir":       SINTA_DIR / "services",
        "glob":      "*_service.json",
        "history_key": "service_history",
        "radar_key": None,
    },
}


def import_jenis(jenis, dry_run=False, filter_kode=""):
    cfg     = JENIS_CONFIG[jenis]
    files   = sorted(cfg["dir"].glob(cfg["glob"]))
    created = updated = skipped = errors = 0

    print(f"\n--- Import jenis={jenis} ({len(files)} file) ---")

    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)

            kode_pt = data.get("kode_pt", f.stem.split("_")[0])
            if filter_kode and kode_pt != filter_kode:
                continue

            # Cari SintaAfiliasi via kode_pt → perguruan_tinggi
            try:
                afiliasi = SintaAfiliasi.objects.select_related("perguruan_tinggi").get(
                    perguruan_tinggi__kode_pt=kode_pt
                )
            except SintaAfiliasi.DoesNotExist:
                print(f"  SKIP {kode_pt}: SintaAfiliasi tidak ditemukan")
                skipped += 1
                continue

            history = data.get(cfg["history_key"], {})
            radar   = data.get(cfg["radar_key"], {}) if cfg["radar_key"] else {}

            for tahun_str, jumlah in history.items():
                tahun = int(tahun_str)
                defaults = {
                    "jumlah": int(jumlah),
                    "research_article":    int(radar.get("article", 0)),
                    "research_conference": int(radar.get("conference", 0)),
                    "research_others":     int(radar.get("others", 0)),
                }
                if dry_run:
                    print(f"  [DRY] {kode_pt} {jenis} {tahun}: {jumlah}")
                    continue

                obj, is_new = SintaTrendTahunan.objects.update_or_create(
                    afiliasi=afiliasi,
                    jenis=jenis,
                    tahun=tahun,
                    defaults=defaults,
                )
                if is_new:
                    created += 1
                else:
                    updated += 1

        except Exception as e:
            print(f"  ERROR {f.name}: {e}")
            errors += 1

    print(f"  Selesai — created={created} updated={updated} skipped={skipped} errors={errors}")
    return created, updated, skipped, errors


def main():
    parser = argparse.ArgumentParser(description="Import SINTA Trend Tahunan ke DB")
    parser.add_argument("--jenis",   default="all", choices=["all", "scopus", "research", "service"])
    parser.add_argument("--kode",    default="", help="Filter satu PT (e.g. 061008)")
    parser.add_argument("--dry-run", action="store_true", help="Preview tanpa write ke DB")
    args = parser.parse_args()

    jenis_list = list(JENIS_CONFIG.keys()) if args.jenis == "all" else [args.jenis]

    total_created = total_updated = total_skipped = total_errors = 0
    for jenis in jenis_list:
        c, u, s, e = import_jenis(jenis, dry_run=args.dry_run, filter_kode=args.kode)
        total_created  += c
        total_updated  += u
        total_skipped  += s
        total_errors   += e

    print(f"\n=== TOTAL ===")
    print(f"  Created : {total_created}")
    print(f"  Updated : {total_updated}")
    print(f"  Skipped : {total_skipped}")
    print(f"  Errors  : {total_errors}")


if __name__ == "__main__":
    main()
