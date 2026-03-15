"""
Management command: migrate_fix
================================
Jalankan dengan: python manage.py migrate_fix

Melakukan tiga hal sebelum migrate:
1. Set charset database ke utf8mb4_unicode_ci
2. Drop semua tabel lama (reset bersih)
3. Patch sql_create_table agar semua tabel dibuat utf8mb4
4. Jalankan migrate normal

Menyelesaikan error:
  "Foreign key constraint is incorrectly formed"
di shared hosting cPanel (charset server latin1).
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection


class Command(BaseCommand):
    help = 'Fix charset lalu jalankan migrate (untuk shared hosting cPanel)'

    def handle(self, *args, **options):

        # ── STEP 1: Patch sql_create_table ──────────────────────
        self.stdout.write('[1/4] Patch Django MySQL SchemaEditor...')
        try:
            from django.db.backends.mysql import schema as mysql_schema
            mysql_schema.DatabaseSchemaEditor.sql_create_table = (
                "CREATE TABLE %(table)s (%(definition)s) "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            self.stdout.write(self.style.SUCCESS('    OK - Patch berhasil'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'    SKIP - {e}'))

        # ── STEP 2: Set charset database ────────────────────────
        self.stdout.write('[2/4] Set charset database ke utf8mb4...')
        db_name = connection.settings_dict['NAME']
        with connection.cursor() as cursor:
            cursor.execute(
                f"ALTER DATABASE `{db_name}` "
                f"CHARACTER SET = utf8mb4 "
                f"COLLATE = utf8mb4_unicode_ci"
            )
        self.stdout.write(self.style.SUCCESS('    OK - Charset database: utf8mb4_unicode_ci'))

        # ── STEP 3: Drop semua tabel lama ───────────────────────
        self.stdout.write('[3/4] Drop semua tabel lama...')
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            cursor.execute(
                "SELECT GROUP_CONCAT('`', table_name, '`') "
                "FROM information_schema.tables "
                "WHERE table_schema = DATABASE() "
                "AND table_type = 'BASE TABLE'"
            )
            row = cursor.fetchone()
            if row and row[0]:
                cursor.execute(f"DROP TABLE IF EXISTS {row[0]}")
                self.stdout.write(self.style.SUCCESS('    OK - Tabel lama dihapus'))
            else:
                self.stdout.write('    SKIP - Tidak ada tabel')
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        # ── STEP 4: Jalankan migrate ─────────────────────────────
        self.stdout.write('[4/4] Jalankan migrate...')
        call_command('migrate', verbosity=1)
        self.stdout.write(self.style.SUCCESS('\nSELESAI! Jalankan: python manage.py createsuperuser'))
