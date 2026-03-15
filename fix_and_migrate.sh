#!/bin/bash
# ============================================================
#  PTMA Monitor — Script Fix Migration (v2)
#
#  Cara pakai di Terminal cPanel:
#  $ source ~/virtualenv/ptma-backend/3.11/bin/activate
#  $ cd ~/ptma-backend
#  $ bash fix_and_migrate.sh
# ============================================================

set -e

echo "======================================"
echo " PTMA Monitor — Fix & Migrate (v2)"
echo "======================================"

# Load variabel dari .env
if [ ! -f .env ]; then
    echo "ERROR: File .env tidak ditemukan di $(pwd)"
    exit 1
fi
export $(grep -v '^#' .env | grep -v '^$' | xargs)

echo ""
echo "[1/4] Reset database — hapus semua tabel lama..."
mysql -u"$DB_USER" -p"$DB_PASSWORD" -h"${DB_HOST:-localhost}" "$DB_NAME" << 'SQLEOF'
SET FOREIGN_KEY_CHECKS = 0;
SET @tables = NULL;
SELECT GROUP_CONCAT('`', table_name, '`') INTO @tables
  FROM information_schema.tables
  WHERE table_schema = DATABASE()
    AND table_type = 'BASE TABLE';
SET @drop_sql = IF(
    @tables IS NOT NULL,
    CONCAT('DROP TABLE IF EXISTS ', @tables),
    'SELECT "Tidak ada tabel"'
);
PREPARE stmt FROM @drop_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SET FOREIGN_KEY_CHECKS = 1;
SQLEOF
echo "   OK - Tabel lama dihapus"

echo ""
echo "[2/4] Set charset database ke utf8mb4..."
mysql -u"$DB_USER" -p"$DB_PASSWORD" -h"${DB_HOST:-localhost}" \
    -e "ALTER DATABASE \`$DB_NAME\` CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci;"
echo "   OK - Database charset: utf8mb4_unicode_ci"

echo ""
echo "[3/4] Verifikasi charset..."
mysql -u"$DB_USER" -p"$DB_PASSWORD" -h"${DB_HOST:-localhost}" \
    -e "SELECT schema_name, default_character_set_name, default_collation_name FROM information_schema.schemata WHERE schema_name = '$DB_NAME';"

echo ""
echo "[4/4] Jalankan migrate..."
DJANGO_SETTINGS_MODULE=ptma.settings.production python manage.py migrate --verbosity=1
echo "   OK - Migrate selesai"

echo ""
echo "Kumpulkan static files..."
DJANGO_SETTINGS_MODULE=ptma.settings.production python manage.py collectstatic --noinput
echo "   OK - Static files selesai"

echo ""
echo "======================================"
echo " BERHASIL! Jalankan selanjutnya:"
echo " python manage.py createsuperuser"
echo " Lalu restart Python App di cPanel."
echo "======================================"
