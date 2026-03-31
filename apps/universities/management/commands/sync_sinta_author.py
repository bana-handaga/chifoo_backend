"""
Management command: sinkron satu (atau lebih) author SINTA dari terminal.

Contoh penggunaan:
  # Sync berdasarkan SINTA ID (angka di URL profil):
  python manage.py sync_sinta_author --sinta_id 6005631

  # Sync berdasarkan primary key di database:
  python manage.py sync_sinta_author --id 1451

  # Sync berdasarkan nama (pencarian parsial, case-insensitive):
  python manage.py sync_sinta_author --nama "Budi"

  # Dry-run (tanpa menyimpan ke DB):
  python manage.py sync_sinta_author --sinta_id 6005631 --dry-run

  # Sync semua author dari satu PT (kode SINTA PT):
  python manage.py sync_sinta_author --kode_pt UMS001 --limit 10
"""

import sys
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

RUNNER_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "utils" / "sinta"
sys.path.insert(0, str(RUNNER_DIR))


class Command(BaseCommand):
    help = "Sinkron author SINTA ke database (satu atau lebih author)"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--sinta_id", type=str, help="SINTA ID author (angka di URL profil)")
        group.add_argument("--id",       type=int, help="Primary key author di database")
        group.add_argument("--nama",     type=str, help="Cari author berdasarkan nama (parsial)")
        group.add_argument("--kode_pt",  type=str, help="Sync semua author dari kode SINTA PT")
        parser.add_argument("--dry-run", action="store_true", help="Simulasi tanpa menyimpan ke DB")
        parser.add_argument("--limit",   type=int, default=None, help="Batas maksimum author (untuk --kode_pt)")

    def handle(self, *args, **options):
        from apps.universities.models import SintaAuthor
        import sync_sinta_author_runner as runner

        dry_run = options["dry_run"]

        # ── Tentukan daftar author ────────────────────────────────
        if options["sinta_id"]:
            qs = SintaAuthor.objects.filter(sinta_id=options["sinta_id"])
        elif options["id"]:
            qs = SintaAuthor.objects.filter(pk=options["id"])
        elif options["nama"]:
            qs = SintaAuthor.objects.filter(nama__icontains=options["nama"])
        else:  # kode_pt
            qs = SintaAuthor.objects.filter(afiliasi__sinta_kode=options["kode_pt"])

        qs = qs.exclude(url_profil="").exclude(url_profil__isnull=True)

        if options["limit"]:
            qs = qs[: options["limit"]]

        authors = list(qs.values("id", "sinta_id", "nama", "url_profil"))

        if not authors:
            raise CommandError("Tidak ada author yang ditemukan dengan kriteria tersebut.")

        total = len(authors)
        self.stdout.write(
            self.style.WARNING(
                f"{'[DRY-RUN] ' if dry_run else ''}Akan sync {total} author..."
            )
        )

        # ── Jalankan scrape ───────────────────────────────────────
        import pymysql
        conn = runner.get_conn()
        session = runner.make_session()
        ok = err = skip = 0

        for i, a in enumerate(authors, 1):
            sinta_id = str(a["sinta_id"])
            nama     = a["nama"] or sinta_id
            url      = a["url_profil"]
            self.stdout.write(f"[{i}/{total}] {nama} (sinta_id={sinta_id}) ...", ending=" ")
            self.stdout.flush()
            try:
                data = runner.scrape_author(session, url, sinta_id)
                if data.get("error"):
                    self.stdout.write(self.style.ERROR(f"✗ {data['error']}"))
                    skip += 1
                elif dry_run:
                    self.stdout.write(self.style.SUCCESS("✓ (dry-run)"))
                    ok += 1
                else:
                    if runner.import_author(conn, data):
                        self.stdout.write(self.style.SUCCESS("✓"))
                        ok += 1
                    else:
                        self.stdout.write(self.style.WARNING("- dilewati"))
                        skip += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"✗ {exc}"))
                err += 1
            if i < total:
                time.sleep(runner.DELAY_NEXT)

        conn.close()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nSelesai: {ok} berhasil, {skip} dilewati, {err} error dari {total} author."
            )
        )
