"""
Script  : sp_import_sinta_gscholar.py
Deskripsi: Import data publikasi Google Scholar dari JSON hasil scrape
           ke tabel universities_sintaauthorpublication

Input   : utils/sinta/outs/gscholar/{sinta_id}_gscholar.json
           → hasil scrape dari scrape_sinta_author_gscholar.py

Pola    : update_or_create berdasarkan (author, sumber='gscholar', pub_id)
           → aman dijalankan ulang (idempoten)

Usage:
  cd chifoo_backend

  # Import semua file JSON yang ada
  python utils/sinta/sp_import_sinta_gscholar.py

  # Dry-run (tidak simpan ke DB)
  python utils/sinta/sp_import_sinta_gscholar.py --dry-run

  # Import satu author saja
  python utils/sinta/sp_import_sinta_gscholar.py --sinta-id 6681079

  # Ringkasan DB
  python utils/sinta/sp_import_sinta_gscholar.py --status
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

from apps.universities.models import SintaAuthor, SintaAuthorPublication

# ---------------------------------------------------------------------------
IN_BASE = BASE_DIR / "utils" / "sinta" / "outs" / "gscholar"
# ---------------------------------------------------------------------------


def all_json_files() -> list[Path]:
    """Ambil semua file JSON dari root dan subfolder PT."""
    files  = list(IN_BASE.glob("*_gscholar.json"))          # root (lama)
    files += list(IN_BASE.glob("*/*_gscholar.json"))        # subfolder PT (baru)
    return sorted(set(files))


def status():
    total_authors = SintaAuthor.objects.count()
    total_pubs    = SintaAuthorPublication.objects.filter(sumber="gscholar").count()
    authors_with  = SintaAuthorPublication.objects.filter(sumber="gscholar").values("author").distinct().count()
    files         = all_json_files()
    print(f"File JSON tersedia   : {len(files)}")
    print(f"Author di DB         : {total_authors}")
    print(f"Author punya pub GS  : {authors_with}")
    print(f"Total publikasi GS   : {total_pubs}")


def import_file(json_file: Path, dry_run=False) -> tuple[int, int, int]:
    """Return (ok, skip, err) untuk satu file."""
    data = json.loads(json_file.read_text(encoding="utf-8"))
    sinta_id = data.get("sinta_id", "")
    pubs     = data.get("publications", [])

    if not pubs:
        return 0, 0, 0

    try:
        author = SintaAuthor.objects.get(sinta_id=sinta_id)
    except SintaAuthor.DoesNotExist:
        # Author belum ada di DB — lewati (bukan error)
        return 0, len(pubs), 0

    ok = skip = err = 0

    for pub in pubs:
        judul = pub.get("judul", "").strip()
        if not judul:
            skip += 1
            continue

        defaults = {
            "judul":   judul,
            "penulis": pub.get("penulis", "")[:1000],
            "jurnal":  pub.get("jurnal",  "")[:500],
            "tahun":   pub.get("tahun"),
            "sitasi":  pub.get("sitasi", 0),
            "url":     (pub.get("url", "") or "")[:800],
        }

        if dry_run:
            ok += 1
            continue

        try:
            _, created = SintaAuthorPublication.objects.update_or_create(
                author=author,
                sumber="gscholar",
                pub_id=pub.get("pub_id", ""),
                defaults=defaults,
            )
            ok += 1
        except Exception as e:
            print(f"    ERROR pub_id={pub.get('pub_id')}: {e}")
            err += 1

    return ok, skip, err


def run(json_files: list[Path], dry_run=False):
    total_ok = total_skip = total_err = 0

    for i, f in enumerate(json_files, 1):
        sinta_id = f.stem.replace("_gscholar", "")
        ok, skip, err = import_file(f, dry_run=dry_run)
        total_ok   += ok
        total_skip += skip
        total_err  += err

        if ok > 0 or err > 0:
            tag = "[DRY]" if dry_run else ""
            print(f"  [{i}/{len(json_files)}] {sinta_id} {tag} ok={ok} skip={skip} err={err}")

        if i % 200 == 0:
            print(f"\n  --- Progress [{i}]: ok={total_ok} skip={total_skip} err={total_err} ---\n")

    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"\n{prefix}Selesai: {total_ok} imported, {total_skip} dilewati, {total_err} error.")
    print(f"Total SintaAuthorPublication (gscholar) di DB: "
          f"{SintaAuthorPublication.objects.filter(sumber='gscholar').count()}")


def main():
    parser = argparse.ArgumentParser(description="Import publikasi GScholar SINTA ke DB")
    parser.add_argument("--dry-run",  action="store_true", help="Simulasi tanpa simpan ke DB")
    parser.add_argument("--status",   action="store_true", help="Tampilkan ringkasan DB")
    parser.add_argument("--sinta-id", help="Import satu author saja")
    args = parser.parse_args()

    if args.status:
        status()
        return

    if args.sinta_id:
        # Cari di root dan subfolder
        candidates = list(IN_BASE.glob(f"*/{args.sinta_id}_gscholar.json")) + \
                     [IN_BASE / f"{args.sinta_id}_gscholar.json"]
        files = [f for f in candidates if f.exists()]
        if not files:
            print(f"File tidak ditemukan untuk sinta_id={args.sinta_id}")
            return
    else:
        files = all_json_files()
        print(f"File JSON ditemukan: {len(files)}")

    run(files, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
