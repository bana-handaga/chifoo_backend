"""
Script  : sp_import_sinta_authors.py
Deskripsi: Import data author SINTA dari JSON ke database Django
           (tabel universities_sintaauthor + universities_sintaauthortrend)

Input   : utils/sinta/outs/authors/{sinta_id}_authordetail.json
          → hasil scrape dari scrape_sinta_author_detail.py

Strategi:
  - SintaAuthor    : update_or_create by sinta_id (aman untuk re-run)
  - SintaAuthorTrend : hapus & insert ulang per author (3 jenis × N tahun)
  - Relasi afiliasi  : lookup via sinta_id_pt dari URL profil dept author
  - Relasi departemen: lookup via kode_dept yang tersimpan di author list

Usage:
  cd chifoo_backend
  python utils/sinta/sp_import_sinta_authors.py
  python utils/sinta/sp_import_sinta_authors.py --dry-run
  python utils/sinta/sp_import_sinta_authors.py --limit 100
  python utils/sinta/sp_import_sinta_authors.py --status
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")

import django
django.setup()

from apps.universities.models import SintaAfiliasi, SintaDepartemen, SintaAuthor, SintaAuthorTrend

# ---------------------------------------------------------------------------
INPUT_DIR = BASE_DIR / "utils" / "sinta" / "outs" / "authors"
DEPT_DIR  = BASE_DIR / "utils" / "sinta" / "outs" / "departments"
# ---------------------------------------------------------------------------


def build_author_dept_map():
    """
    Baca semua *_author_list.json, buat mapping:
      sinta_id_author → (sinta_id_pt, kode_dept)
    Jika satu author ada di beberapa dept, ambil yang pertama ditemukan.
    """
    mapping = {}
    for f in sorted(DEPT_DIR.glob("*/*_author_list.json")):
        try:
            data = json.loads(f.read_text())
            kode_pt   = data.get("kode_pt", "")
            kode_dept = data.get("kode_dept", "")
            for a in data.get("authors", []):
                sid = a.get("sinta_id", "")
                if sid and sid not in mapping:
                    mapping[sid] = (kode_pt, kode_dept)
        except Exception:
            pass
    return mapping


def build_dept_db_map():
    """
    Mapping (kode_pt, kode_dept) → SintaDepartemen instance.
    Preload semua departemen untuk menghindari per-author query.
    """
    result = {}
    for dept in SintaDepartemen.objects.select_related("afiliasi").all():
        key = (dept.afiliasi.sinta_kode, dept.kode_dept)
        result[key] = dept
    return result


def build_afiliasi_map():
    """sinta_kode (kode_pt) → SintaAfiliasi instance."""
    return {a.sinta_kode: a for a in SintaAfiliasi.objects.all()}


def import_author(data, dept_map, afiliasi_map, dry_run=False):
    """Import satu author JSON dict ke database."""
    sinta_id = data.get("sinta_id", "")
    if not sinta_id:
        return False

    # Cari afiliasi & departemen via sinta_id_pt dan kode_dept
    afiliasi   = None
    departemen = None
    sinta_id_pt = data.get("sinta_id_pt", "")
    kode_dept   = data.get("kode_dept", "")

    if sinta_id_pt:
        # Cari berdasarkan sinta_id SINTA (bukan kode_pt)
        afiliasi = next(
            (a for a in afiliasi_map.values() if a.sinta_id == sinta_id_pt),
            None
        )
    if afiliasi and kode_dept:
        departemen = dept_map.get((afiliasi.sinta_kode, kode_dept))

    if dry_run:
        return True

    author, _ = SintaAuthor.objects.update_or_create(
        sinta_id=sinta_id,
        defaults={
            "nama":        data.get("nama", ""),
            "url_profil":  data.get("url_profil", ""),
            "foto_url":    data.get("foto_url", ""),
            "bidang_keilmuan": data.get("bidang_keilmuan", []),
            "afiliasi":    afiliasi,
            "departemen":  departemen,
            # SINTA Scores
            "sinta_score_overall": data.get("sinta_score_overall", 0),
            "sinta_score_3year":   data.get("sinta_score_3year", 0),
            "affil_score":         data.get("affil_score", 0),
            "affil_score_3year":   data.get("affil_score_3year", 0),
            # Scopus
            "scopus_artikel":   data.get("scopus_artikel", 0),
            "scopus_sitasi":    data.get("scopus_sitasi", 0),
            "scopus_cited_doc": data.get("scopus_cited_doc", 0),
            "scopus_h_index":   data.get("scopus_h_index", 0),
            "scopus_i10_index": data.get("scopus_i10_index", 0),
            "scopus_g_index":   data.get("scopus_g_index", 0),
            # Google Scholar
            "gscholar_artikel":   data.get("gscholar_artikel", 0),
            "gscholar_sitasi":    data.get("gscholar_sitasi", 0),
            "gscholar_cited_doc": data.get("gscholar_cited_doc", 0),
            "gscholar_h_index":   data.get("gscholar_h_index", 0),
            "gscholar_i10_index": data.get("gscholar_i10_index", 0),
            "gscholar_g_index":   data.get("gscholar_g_index", 0),
            # WOS
            "wos_artikel":   data.get("wos_artikel", 0),
            "wos_sitasi":    data.get("wos_sitasi", 0),
            "wos_cited_doc": data.get("wos_cited_doc", 0),
            "wos_h_index":   data.get("wos_h_index", 0),
            "wos_i10_index": data.get("wos_i10_index", 0),
            "wos_g_index":   data.get("wos_g_index", 0),
            # Kuartil
            "scopus_q1":  data.get("scopus_q1", 0),
            "scopus_q2":  data.get("scopus_q2", 0),
            "scopus_q3":  data.get("scopus_q3", 0),
            "scopus_q4":  data.get("scopus_q4", 0),
            "scopus_noq": data.get("scopus_noq", 0),
            # Radar
            "research_conference": data.get("research_conference", 0),
            "research_articles":   data.get("research_articles", 0),
            "research_others":     data.get("research_others", 0),
        }
    )

    # Import trend (hapus & insert ulang)
    author.trend.all().delete()
    trend_objs = []
    for jenis, key in [("scopus", "trend_scopus"), ("research", "trend_research"), ("service", "trend_service")]:
        for item in data.get(key, []):
            trend_objs.append(SintaAuthorTrend(
                author=author,
                jenis=jenis,
                tahun=item["tahun"],
                jumlah=item["jumlah"],
            ))
    if trend_objs:
        SintaAuthorTrend.objects.bulk_create(trend_objs, ignore_conflicts=True)

    return True


def cmd_status():
    files_count = len(list(INPUT_DIR.glob("*_authordetail.json")))
    author_count = SintaAuthor.objects.count()
    trend_count  = SintaAuthorTrend.objects.count()
    linked_afiliasi = SintaAuthor.objects.filter(afiliasi__isnull=False).count()
    linked_dept     = SintaAuthor.objects.filter(departemen__isnull=False).count()
    print(f"File JSON       : {files_count:,}")
    print(f"SintaAuthor DB  : {author_count:,}")
    print(f"  linked PT     : {linked_afiliasi:,}")
    print(f"  linked dept   : {linked_dept:,}")
    print(f"SintaAuthorTrend: {trend_count:,}")
    print(f"Sisa import     : {files_count - author_count:,}")


def main():
    parser = argparse.ArgumentParser(description="Import SINTA Author Detail ke database")
    parser.add_argument("--dry-run", action="store_true", help="Simulasi tanpa menyimpan")
    parser.add_argument("--limit",   type=int, help="Maksimum jumlah file diproses")
    parser.add_argument("--status",  action="store_true", help="Tampilkan ringkasan")
    args = parser.parse_args()

    if args.status:
        cmd_status()
        return

    if not INPUT_DIR.exists():
        print(f"Folder input tidak ditemukan: {INPUT_DIR}")
        sys.exit(1)

    files = sorted(INPUT_DIR.glob("*/*/*.json"))
    if not files:
        print("Tidak ada file author detail ditemukan.")
        sys.exit(0)

    if args.limit:
        files = files[:args.limit]

    print(f"Memuat mapping dept & afiliasi...")
    dept_map     = build_dept_db_map()
    afiliasi_map = build_afiliasi_map()
    print(f"  {len(dept_map)} departemen, {len(afiliasi_map)} PT dimuat.")

    print(f"\nMemproses {len(files):,} file JSON...\n")
    ok = skip = err = 0

    for i, f in enumerate(files, 1):
        try:
            data = json.loads(f.read_text())
            if data.get("error"):
                skip += 1
                continue
            if import_author(data, dept_map, afiliasi_map, dry_run=args.dry_run):
                ok += 1
            else:
                skip += 1
        except Exception as e:
            print(f"  ERROR {f.name}: {e}")
            err += 1

        if i % 500 == 0:
            print(f"  [{i:,}/{len(files):,}] ok={ok:,}  skip={skip}  err={err}")

    mode = "DRY-RUN" if args.dry_run else "imported"
    print(f"\nSelesai: {ok:,} {mode}, {skip} dilewati, {err} error.")
    if not args.dry_run:
        print(f"Total SintaAuthor di DB : {SintaAuthor.objects.count():,}")
        print(f"Total SintaAuthorTrend  : {SintaAuthorTrend.objects.count():,}")


if __name__ == "__main__":
    main()
