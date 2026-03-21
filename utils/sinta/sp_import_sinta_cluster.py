"""
Import SINTA Klasterisasi → SintaCluster + SintaClusterItem

Sumber JSON:
  - outs/cluster/{kode}_cluster.json

Usage:
  cd chifoo_backend
  python utils/sinta/sp_import_sinta_cluster.py
  python utils/sinta/sp_import_sinta_cluster.py --kode 061008
  python utils/sinta/sp_import_sinta_cluster.py --dry-run
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

from apps.universities.models import SintaAfiliasi, SintaCluster, SintaClusterItem

CLUSTER_DIR = Path(__file__).parent / "outs" / "cluster"


def import_cluster(data, afiliasi, dry_run=False):
    cluster_name = data.get("cluster_name", "")
    if not cluster_name:
        return None, False

    scores = data.get("scores", {})

    def w(section, field):
        return scores.get(section, {}).get(field, 0.0)

    defaults = {
        "cluster_name":             cluster_name,
        "total_score":              data.get("total_score", 0.0),
        "score_publication":        w("publication",       "total_weighted"),
        "score_hki":                w("hki",               "total_weighted"),
        "score_kelembagaan":        w("kelembagaan",       "total_weighted"),
        "score_research":           w("research",          "total_weighted"),
        "score_community_service":  w("community_service", "total_weighted"),
        "score_sdm":                w("sdm",               "total_weighted"),
        "ternormal_publication":        w("publication",       "total_ternormal"),
        "ternormal_hki":                w("hki",               "total_ternormal"),
        "ternormal_kelembagaan":        w("kelembagaan",       "total_ternormal"),
        "ternormal_research":           w("research",          "total_ternormal"),
        "ternormal_community_service":  w("community_service", "total_ternormal"),
        "ternormal_sdm":                w("sdm",               "total_ternormal"),
        "periode": "2022-2024",
    }

    if dry_run:
        print(f"  [DRY] cluster={cluster_name} total={defaults['total_score']:.2f}")
        return None, False

    cluster, is_new = SintaCluster.objects.update_or_create(
        afiliasi=afiliasi,
        defaults=defaults,
    )

    # Hapus items lama lalu re-insert
    cluster.items.all().delete()
    items = data.get("items", {})
    SintaClusterItem.objects.bulk_create([
        SintaClusterItem(
            cluster=cluster,
            kode=kode,
            section=item.get("section", ""),
            nama=item.get("name", ""),
            bobot=item.get("weight", 0.0),
            nilai=item.get("value", 0.0),
            total=item.get("total", 0.0),
        )
        for kode, item in items.items()
    ])

    return cluster, is_new


def main():
    parser = argparse.ArgumentParser(description="Import SINTA Klasterisasi ke DB")
    parser.add_argument("--kode",    default="", help="Filter satu PT (e.g. 061008)")
    parser.add_argument("--dry-run", action="store_true", help="Preview tanpa write ke DB")
    args = parser.parse_args()

    files = sorted(CLUSTER_DIR.glob("*_cluster.json"))
    created = updated = skipped = errors = no_cluster = 0

    print(f"Total file cluster: {len(files)}")

    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)

            kode_pt = data.get("kode_pt", f.stem.replace("_cluster", ""))
            if args.kode and kode_pt != args.kode:
                continue

            if not data.get("cluster_name"):
                no_cluster += 1
                continue

            try:
                afiliasi = SintaAfiliasi.objects.get(perguruan_tinggi__kode_pt=kode_pt)
            except SintaAfiliasi.DoesNotExist:
                print(f"  SKIP {kode_pt}: SintaAfiliasi tidak ditemukan")
                skipped += 1
                continue

            cluster, is_new = import_cluster(data, afiliasi, dry_run=args.dry_run)

            if not args.dry_run and cluster:
                items_count = cluster.items.count()
                status = "NEW" if is_new else "UPD"
                print(f"  [{status}] {kode_pt} — {data['cluster_name']} score={data['total_score']:.2f} items={items_count}")
                if is_new:
                    created += 1
                else:
                    updated += 1

        except Exception as e:
            print(f"  ERROR {f.name}: {e}")
            import traceback; traceback.print_exc()
            errors += 1

    print(f"\n=== Selesai ===")
    print(f"  Created    : {created}")
    print(f"  Updated    : {updated}")
    print(f"  No cluster : {no_cluster}")
    print(f"  Skipped    : {skipped}")
    print(f"  Errors     : {errors}")


if __name__ == "__main__":
    main()
