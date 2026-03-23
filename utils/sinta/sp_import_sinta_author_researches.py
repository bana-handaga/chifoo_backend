"""
Import data penelitian author dari JSON ke DB.

Input : utils/sinta/outs/author_researches/{kode_pt}/{sinta_id}_researches.json
Output: tabel SintaPenelitian + SintaPenelitianAuthor

Strategi:
  - SintaPenelitian    : update_or_create by (judul, tahun, skema_kode)
  - SintaPenelitianAuthor: update_or_create by (penelitian, author)
  - Author scrape page (ketua/personil) dicocokkan ke SintaAuthor via sinta_id
  - Author tidak ada di DB → di-skip

Usage:
  cd chifoo_backend
  python utils/sinta/sp_import_sinta_author_researches.py
  python utils/sinta/sp_import_sinta_author_researches.py --dry-run
  python utils/sinta/sp_import_sinta_author_researches.py --status
  python utils/sinta/sp_import_sinta_author_researches.py --limit 50
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

from apps.universities.models import SintaAuthor, SintaPenelitian, SintaPenelitianAuthor

INPUT_DIR = BASE_DIR / "utils" / "sinta" / "outs" / "author_researches"


def build_author_map():
    return {a.sinta_id: a for a in SintaAuthor.objects.only("id", "sinta_id")}


def import_file(path, page_author, author_map, dry_run):
    """Return (penelitian_upserted, rel_upserted)."""
    data = json.loads(path.read_text())
    researches = data.get("researches", [])
    p_count = r_count = 0

    for r in researches:
        judul      = (r.get("judul") or "").strip()[:1000]
        skema_kode = (r.get("skema_kode") or "")[:20]
        tahun      = r.get("tahun")

        if not judul:
            continue

        defaults = {
            "leader_nama": (r.get("leader_nama") or "")[:200],
            "skema":       (r.get("skema") or "")[:300],
            "dana":        (r.get("dana") or "")[:50],
            "status":      (r.get("status") or "")[:50],
            "sumber":      (r.get("sumber") or "")[:50],
        }

        if not dry_run:
            penelitian, _ = SintaPenelitian.objects.update_or_create(
                judul=judul, tahun=tahun, skema_kode=skema_kode,
                defaults=defaults,
            )

            # Relasi: author pemilik halaman ini (selalu anggota/ketua)
            SintaPenelitianAuthor.objects.update_or_create(
                penelitian=penelitian,
                author=page_author,
                defaults={"is_leader": False},  # akan di-update jika dia ketua
            )

            # Cek apakah page_author adalah ketua
            leader_nama = defaults["leader_nama"].strip().lower()
            author_nama = (page_author.nama or "").strip().lower()
            if leader_nama and author_nama and leader_nama == author_nama:
                SintaPenelitianAuthor.objects.filter(
                    penelitian=penelitian, author=page_author
                ).update(is_leader=True)

            # Personils dengan sinta_id
            for p in r.get("personils", []):
                p_sinta_id = p.get("sinta_id", "").strip()
                p_author = author_map.get(p_sinta_id) if p_sinta_id else None
                if p_author and p_author != page_author:
                    SintaPenelitianAuthor.objects.update_or_create(
                        penelitian=penelitian,
                        author=p_author,
                        defaults={"is_leader": False},
                    )

        p_count += 1
        r_count += 1 + len(r.get("personils", []))

    return p_count, r_count


def status():
    files = list(INPUT_DIR.glob("*/*_researches.json"))
    total_items = sum(
        len(json.loads(f.read_text()).get("researches", []))
        for f in files if f.stat().st_size > 0
    )
    print(f"File JSON            : {len(files):,}")
    print(f"Total penelitian raw : {total_items:,}")
    print(f"SintaPenelitian      : {SintaPenelitian.objects.count():,}")
    print(f"PenelitianAuthor     : {SintaPenelitianAuthor.objects.count():,}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status",  action="store_true")
    parser.add_argument("--offset",  type=int, default=0)
    parser.add_argument("--limit",   type=int, default=0)
    args = parser.parse_args()

    if args.status:
        status()
        return

    files = sorted(INPUT_DIR.glob("*/*_researches.json"))
    if args.offset:
        files = files[args.offset:]
    if args.limit:
        files = files[:args.limit]

    print("Membangun author map...")
    author_map = build_author_map()
    print(f"  {len(author_map):,} author di DB")
    print(f"Memproses {len(files):,} file JSON...\n")

    ok = skip_no_author = skip_empty = err = 0
    total_p = total_r = 0

    for i, f in enumerate(files, 1):
        sinta_id   = f.stem.replace("_researches", "")
        page_author = author_map.get(sinta_id)

        if page_author is None:
            skip_no_author += 1
            continue

        try:
            data = json.loads(f.read_text())
            if not data.get("researches"):
                skip_empty += 1
                continue

            n_p, n_r = import_file(f, page_author, author_map, args.dry_run)
            total_p += n_p
            total_r += n_r
            ok += 1

        except Exception as e:
            print(f"  ERROR {f.name}: {e}")
            err += 1

        if i % 200 == 0:
            print(f"  [{i:,}/{len(files):,}] ok={ok} skip_noauth={skip_no_author} "
                  f"skip_empty={skip_empty} err={err} | penelitian={total_p:,}")

    mode = "dry-run" if args.dry_run else "imported"
    print(f"\nSelesai: {ok} file {mode}, {skip_empty} kosong, "
          f"{skip_no_author} author tidak ditemukan, {err} error.")
    print(f"Penelitian : {total_p:,}")
    print(f"DB total   : {SintaPenelitian.objects.count():,} penelitian, "
          f"{SintaPenelitianAuthor.objects.count():,} relasi")


if __name__ == "__main__":
    main()
