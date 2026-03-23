"""
Import artikel Scopus dari JSON ke DB.

Input : utils/sinta/outs/scopus/{kode_pt}/{sinta_id}_scopus.json
Output: tabel SintaScopusArtikel + SintaScopusArtikelAuthor

Strategi:
  - SintaScopusArtikel       : update_or_create by eid (unik global)
  - SintaScopusArtikelAuthor : update_or_create by (artikel, author)
  - Author yang tidak ada di DB → di-skip (dicatat)

Usage:
  cd chifoo_backend
  python utils/sinta/sp_import_sinta_scopus_articles.py
  python utils/sinta/sp_import_sinta_scopus_articles.py --dry-run
  python utils/sinta/sp_import_sinta_scopus_articles.py --status
  python utils/sinta/sp_import_sinta_scopus_articles.py --limit 50
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

from apps.universities.models import SintaAuthor, SintaScopusArtikel, SintaScopusArtikelAuthor

INPUT_DIR = BASE_DIR / "utils" / "sinta" / "outs" / "scopus"


def build_author_map() -> dict[str, SintaAuthor]:
    """sinta_id (str) → SintaAuthor instance."""
    return {a.sinta_id: a for a in SintaAuthor.objects.only("id", "sinta_id")}


def import_file(path: Path, author: SintaAuthor, dry_run: bool) -> tuple[int, int]:
    """Return (artikel_upserted, rel_upserted)."""
    data = json.loads(path.read_text())
    articles = data.get("articles", [])
    art_count = rel_count = 0

    for a in articles:
        eid = a.get("eid", "").strip()
        if not eid:
            continue

        defaults = {
            "judul":       (a.get("judul") or "").strip()[:1000],
            "tahun":       a.get("tahun"),
            "sitasi":      a.get("sitasi") or 0,
            "kuartil":     (a.get("kuartil") or "")[:2],
            "jurnal_nama": (a.get("jurnal_nama") or "")[:500],
            "jurnal_url":  (a.get("jurnal_url") or "")[:400],
            "scopus_url":  (a.get("scopus_url") or "")[:600],
        }

        if not dry_run:
            artikel, _ = SintaScopusArtikel.objects.update_or_create(
                eid=eid, defaults=defaults
            )
            SintaScopusArtikelAuthor.objects.update_or_create(
                artikel=artikel,
                author=author,
                defaults={
                    "urutan_penulis": a.get("urutan_penulis") or 0,
                    "total_penulis":  a.get("total_penulis")  or 0,
                    "nama_singkat":   (a.get("nama_singkat") or "")[:100],
                },
            )
        art_count += 1
        rel_count += 1

    return art_count, rel_count


def status():
    files  = list(INPUT_DIR.glob("*/*_scopus.json"))
    total_arts = sum(
        len(json.loads(f.read_text()).get("articles", []))
        for f in files
        if f.stat().st_size > 0
    )
    print(f"File JSON         : {len(files):,}")
    print(f"Total artikel raw : {total_arts:,}")
    print(f"SintaScopusArtikel: {SintaScopusArtikel.objects.count():,}")
    print(f"ArtikelAuthor     : {SintaScopusArtikelAuthor.objects.count():,}")


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

    files = sorted(INPUT_DIR.glob("*/*_scopus.json"))
    if args.offset:
        files = files[args.offset:]
    if args.limit:
        files = files[:args.limit]

    print(f"Membangun author map...")
    author_map = build_author_map()
    print(f"  {len(author_map):,} author di DB")

    print(f"Memproses {len(files):,} file JSON...\n")

    ok = skip_no_author = skip_empty = err = 0
    total_art = total_rel = 0

    for i, f in enumerate(files, 1):
        sinta_id = f.stem.replace("_scopus", "")
        author   = author_map.get(sinta_id)

        if author is None:
            skip_no_author += 1
            continue

        try:
            data = json.loads(f.read_text())
            if not data.get("articles"):
                skip_empty += 1
                continue

            n_art, n_rel = import_file(f, author, args.dry_run)
            total_art += n_art
            total_rel += n_rel
            ok += 1

        except Exception as e:
            print(f"  ERROR {f.name}: {e}")
            err += 1

        if i % 200 == 0:
            print(f"  [{i:,}/{len(files):,}] ok={ok} skip_noauth={skip_no_author} "
                  f"skip_empty={skip_empty} err={err} | art={total_art:,}")

    mode = "dry-run" if args.dry_run else "imported"
    print(f"\nSelesai: {ok} file {mode}, {skip_empty} kosong, "
          f"{skip_no_author} author tidak ditemukan, {err} error.")
    print(f"Artikel  : {total_art:,}")
    print(f"DB total : {SintaScopusArtikel.objects.count():,} artikel, "
          f"{SintaScopusArtikelAuthor.objects.count():,} relasi")


if __name__ == "__main__":
    main()
