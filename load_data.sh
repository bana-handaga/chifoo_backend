#!/bin/bash
# ============================================================
#  PTMA Monitor — Load Contoh Data
#
#  Jalankan SETELAH migrate selesai:
#  $ bash load_data.sh
# ============================================================

set -e

SETTINGS="ptma.settings.production_migrate"

echo "======================================="
echo " PTMA Monitor — Load Contoh Data"
echo "======================================="

echo ""
echo "[1/6] Load data Wilayah..."
python manage.py loaddata apps/universities/fixtures/wilayah.json --settings=$SETTINGS
echo "   OK"

echo ""
echo "[2/6] Load data Perguruan Tinggi (12 PT Muhammadiyah)..."
python manage.py loaddata apps/universities/fixtures/perguruan_tinggi.json --settings=$SETTINGS
echo "   OK"

echo ""
echo "[3/6] Load data Program Studi..."
python manage.py loaddata apps/universities/fixtures/program_studi.json --settings=$SETTINGS
echo "   OK"

echo ""
echo "[4/6] Load data Mahasiswa & Dosen..."
python manage.py loaddata apps/universities/fixtures/data_mahasiswa.json --settings=$SETTINGS
python manage.py loaddata apps/universities/fixtures/data_dosen.json --settings=$SETTINGS
echo "   OK"

echo ""
echo "[5/6] Load data Monitoring (Indikator & Periode)..."
python manage.py loaddata apps/monitoring/fixtures/monitoring.json --settings=$SETTINGS
echo "   OK"

echo ""
echo "[6/6] Load data Laporan..."
python manage.py loaddata apps/monitoring/fixtures/laporan.json --settings=$SETTINGS
echo "   OK"

echo ""
echo "======================================="
echo " Data berhasil dimuat!"
echo ""
echo " Sekarang buat akun admin:"
echo " python manage.py createsuperuser --settings=$SETTINGS"
echo "======================================="
