"""
Management command: sinkron satu (atau lebih) afiliasi SINTA dari terminal.

Contoh penggunaan:
  # Sync berdasarkan SINTA ID (angka di URL profil):
  python manage.py sync_sinta_afiliasi --sinta_id 27

  # Sync berdasarkan kode_pt di database:
  python manage.py sync_sinta_afiliasi --kode_pt 061008

  # Sync berdasarkan nama (pencarian parsial, case-insensitive):
  python manage.py sync_sinta_afiliasi --nama "Muhammadiyah"

  # Dry-run (tanpa menyimpan ke DB):
  python manage.py sync_sinta_afiliasi --sinta_id 27 --dry-run

  # Sync semua afiliasi yang scraped_at > 30 hari lalu:
  python manage.py sync_sinta_afiliasi --days 30

  # Sync semua afiliasi (paksa ulang):
  python manage.py sync_sinta_afiliasi --days 0 --limit 10
"""

import sys
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

RUNNER_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "utils" / "sinta"
sys.path.insert(0, str(RUNNER_DIR))


class Command(BaseCommand):
    help = "Sinkron afiliasi SINTA ke database (satu atau lebih PT)"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--sinta_id", type=str, help="SINTA ID afiliasi (angka di URL profil)")
        group.add_argument("--kode_pt",  type=str, help="Kode PT di database")
        group.add_argument("--nama",     type=str, help="Cari PT berdasarkan nama SINTA (parsial)")
        parser.add_argument("--dry-run", action="store_true", help="Simulasi tanpa menyimpan ke DB")
        parser.add_argument("--days",    type=int, default=30,
                            help="Scrape ulang afiliasi scraped_at > N hari lalu (0=semua, default: 30)")
        parser.add_argument("--limit",   type=int, default=None,
                            help="Batas maksimum afiliasi per run")

    def handle(self, *args, **options):
        from apps.universities.models import SintaAfiliasi
        import sync_sinta_afiliasi_runner as runner

        dry_run = options["dry_run"]

        # ── Tentukan daftar afiliasi ──────────────────────────
        if options.get("sinta_id"):
            qs = SintaAfiliasi.objects.filter(sinta_id=options["sinta_id"])
        elif options.get("kode_pt"):
            qs = SintaAfiliasi.objects.filter(perguruan_tinggi__kode_pt=options["kode_pt"])
        elif options.get("nama"):
            qs = SintaAfiliasi.objects.filter(nama_sinta__icontains=options["nama"])
        else:
            # Filter berdasarkan --days
            from django.utils import timezone
            from datetime import timedelta
            days = options["days"]
            if days > 0:
                cutoff = timezone.now() - timedelta(days=days)
                qs = SintaAfiliasi.objects.filter(scraped_at__lt=cutoff)
            else:
                qs = SintaAfiliasi.objects.all()

        qs = qs.exclude(sinta_id="").select_related("perguruan_tinggi")

        if options.get("limit"):
            qs = qs.order_by("scraped_at")[: options["limit"]]

        afiliasis = list(qs.values(
            "id", "sinta_id", "nama_sinta", "logo_base64"
        ))

        if not afiliasis:
            raise CommandError("Tidak ada afiliasi yang ditemukan dengan kriteria tersebut.")

        total = len(afiliasis)
        self.stdout.write(
            self.style.WARNING(
                f"{'[DRY-RUN] ' if dry_run else ''}Akan sync {total} afiliasi..."
            )
        )

        # ── Setup session ─────────────────────────────────────
        session = runner.make_session()
        ok = err = skip = 0

        for i, af in enumerate(afiliasis, 1):
            sinta_id   = str(af["sinta_id"])
            nama       = af.get("nama_sinta") or sinta_id
            fetch_logo = not bool(af.get("logo_base64"))
            self.stdout.write(
                f"[{i}/{total}] {nama} (sinta_id={sinta_id}) ...", ending=" "
            )
            self.stdout.flush()
            try:
                data = runner.scrape_afiliasi(session, sinta_id, fetch_logo=fetch_logo)
                if data.get("error"):
                    self.stdout.write(self.style.ERROR(f"✗ {data['error']}"))
                    skip += 1
                elif dry_run:
                    score = data.get("sinta_score_overall", 0)
                    scopus = data.get("scopus_dokumen", 0)
                    self.stdout.write(
                        self.style.SUCCESS(f"✓ (dry-run) score={score:,} scopus={scopus:.0f}")
                    )
                    ok += 1
                else:
                    if runner.import_afiliasi(data):
                        score = data.get("sinta_score_overall", 0)
                        self.stdout.write(self.style.SUCCESS(f"✓ score={score:,}"))
                        ok += 1
                    else:
                        self.stdout.write(self.style.WARNING("- dilewati"))
                        skip += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"✗ {exc}"))
                err += 1
            if i < total:
                time.sleep(runner.DELAY_NEXT)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSelesai: {ok} berhasil, {skip} dilewati, {err} error dari {total} afiliasi."
            )
        )
