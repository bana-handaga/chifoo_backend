"""
settings/production_migrate.py
================================
Settings KHUSUS untuk migrate pertama kali.
FOREIGN_KEY_CHECKS=0 dinonaktifkan agar migrate tidak error.

Cara pakai:
  python manage.py migrate --settings=ptma.settings.production_migrate

Setelah migrate selesai, JANGAN gunakan file ini untuk operasional normal.
Gunakan: ptma.settings.production
"""
from ptma.settings.production import *  # noqa

# Override DATABASES — tambahkan FOREIGN_KEY_CHECKS=0
DATABASES['default']['OPTIONS']['init_command'] = (
    "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci,"
    " sql_mode='STRICT_TRANS_TABLES',"
    " FOREIGN_KEY_CHECKS=0"
)
