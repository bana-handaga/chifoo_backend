"""
Import / Update DataDosen dan DataMahasiswa dari *_listprodi.json
(hasil scrape Data Pelaporan Tahunan PDDikti).

Sumber  : outs/{kode_pt}/{kode_pt}_listprodi.json
DataDosen: dosen_tetap, dosen_tidak_tetap, dosen_rasio, rasio
DataMahasiswa: mahasiswa_aktif

Perbaikan:
  1. Duplikat kode_prodi dalam satu semester → gabungkan: ambil nilai non-zero,
     skip baris yang semua nilai == 0 jika sudah ada baris non-zero untuk kode sama.
  2. Prodi Tutup/Alih Bentuk tidak ada di DB → dilewati (tidak buat NULL FK).
  3. Prodi Aktif tidak ada di DB → dibuat otomatis di ProgramStudi.

Mapping semester PDDikti → DB:
    Ganjil YYYY  →  tahun='{YYYY}/{YYYY+1}', semester='ganjil'
    Genap  YYYY  →  tahun='{YYYY-1}/{YYYY}', semester='genap'

Usage:
    cd /home/ubuntu/_chifoo/chifoo_backend
    conda run -n chifoo python utils/import_datadosen_pelaporan.py
    conda run -n chifoo python utils/import_datadosen_pelaporan.py --dry-run
    conda run -n chifoo python utils/import_datadosen_pelaporan.py --kode_pt 213388 213539
"""

import os, sys, json, glob, argparse
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ptma.settings.base')

import django
django.setup()

from apps.universities.models import PerguruanTinggi, ProgramStudi, DataDosen, DataMahasiswa

OUTS_DIR = BASE_DIR / 'utils' / 'outs'

STATUS_SKIP = {'tutup', 'alih bentuk', 'non aktif'}

JENJANG_MAP = {
    'd1': 'D1', 'd2': 'D2', 'd3': 'D3', 'd4': 'D4',
    's1': 'S1', 's2': 'S2', 's3': 'S3',
    'profesi': 'Profesi', 'sp-1': 'Sp-1', 'sp-2': 'Sp-2',
}


def parse_semester(label: str):
    parts = label.strip().split()
    if len(parts) != 2:
        return None, None
    tipe, yr_str = parts[0].lower(), parts[1]
    try:
        yr = int(yr_str)
    except ValueError:
        return None, None
    if tipe == 'ganjil':
        return f'{yr}/{yr + 1}', 'ganjil'
    elif tipe == 'genap':
        return f'{yr - 1}/{yr}', 'genap'
    return None, None


def safe_int(val, default=0):
    try:
        return int(str(val).replace(',', '').strip())
    except (ValueError, TypeError):
        return default


def dedup_rows(rows: list) -> list:
    """
    Deduplikasi baris berdasarkan kode_prodi dalam satu semester.
    Jika kode muncul >1x: ambil baris dengan nilai non-zero tertinggi.
    Baris dengan semua nilai == 0 dibuang jika sudah ada baris non-zero.
    """
    by_kode = defaultdict(list)
    for row in rows:
        kode = str(row.get('Kode', '')).strip()
        if kode:
            by_kode[kode].append(row)

    result = []
    for kode, candidates in by_kode.items():
        if len(candidates) == 1:
            result.append(candidates[0])
            continue
        # Pilih baris dengan skor nilai tertinggi
        def score(r):
            return (safe_int(r.get('Dosen Tetap')) +
                    safe_int(r.get('Dosen Tidak Tetap')) +
                    safe_int(r.get('Jumlah Dosen Penghitung Rasio')) +
                    safe_int(r.get('Jumlah Mahasiswa')))
        best = max(candidates, key=score)
        result.append(best)
    return result


def get_or_create_prodi(pt, kode_ps, row, prodi_cache, dry_run):
    """
    Kembalikan ProgramStudi untuk (pt, kode_ps).
    Jika belum ada: buat baru jika Status == Aktif, skip jika Tutup/Alih Bentuk.
    """
    prodi = prodi_cache.get((pt.id, kode_ps))
    if prodi:
        return prodi

    status = str(row.get('Status', '')).strip().lower()
    if status in STATUS_SKIP or status == '':
        return None  # dilewati, tidak buat NULL FK

    # Prodi Aktif belum di DB → buat baru
    nama   = str(row.get('Nama Program Studi', '')).strip()[:200]
    jenjang = JENJANG_MAP.get(str(row.get('Jenjang', '')).strip().lower(), '')

    if not dry_run:
        prodi, created = ProgramStudi.objects.get_or_create(
            perguruan_tinggi=pt,
            kode_prodi=kode_ps,
            defaults={'nama': nama, 'jenjang': jenjang},
        )
        prodi_cache[(pt.id, kode_ps)] = prodi
        if created:
            print(f'  [PRODI BARU] {pt.kode_pt} {kode_ps} {jenjang} {nama}')
    return None if dry_run else prodi


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--kode_pt', nargs='+', default=None)
    args = parser.parse_args()
    dry_run        = args.dry_run
    kode_pt_filter = set(args.kode_pt) if args.kode_pt else None

    if dry_run:
        print('[DRY-RUN] Tidak ada perubahan yang disimpan.')

    pt_cache = {pt.kode_pt: pt for pt in PerguruanTinggi.objects.all()}
    prodi_cache = {
        (ps.perguruan_tinggi_id, ps.kode_prodi): ps
        for ps in ProgramStudi.objects.all()
    }
    print(f'PT di DB    : {len(pt_cache)}')
    print(f'Prodi di DB : {len(prodi_cache)}')

    files = sorted(glob.glob(str(OUTS_DIR / '**' / '*_listprodi.json'), recursive=True))
    if kode_pt_filter:
        files = [f for f in files if Path(f).parent.name in kode_pt_filter]
    print(f'File        : {len(files)}')
    print()

    dd_created = dd_updated = mhs_created = mhs_updated = skipped = error = 0
    prodi_created = 0

    for fpath in files:
        try:
            d = json.load(open(fpath, encoding='utf-8'))
        except Exception as e:
            print(f'  [ERROR] baca {fpath}: {e}')
            error += 1
            continue

        kode_pt = str(d.get('kode_pt', '')).strip()
        if not kode_pt or kode_pt not in pt_cache:
            skipped += 1
            continue

        pt = pt_cache[kode_pt]

        for sem_data in d.get('pelaporan', []):
            sem_label = sem_data.get('semester', '')
            tahun, semester = parse_semester(sem_label)
            if not tahun:
                continue

            rows = dedup_rows(sem_data.get('program_studi', []))

            for row in rows:
                kode_ps = str(row.get('Kode', '')).strip()
                if not kode_ps:
                    continue

                prodi = get_or_create_prodi(pt, kode_ps, row, prodi_cache, dry_run)
                if prodi is None and not dry_run:
                    # Prodi Tutup/Alih Bentuk → skip
                    skipped += 1
                    continue

                tetap        = safe_int(row.get('Dosen Tetap', 0))
                tidak_tetap  = safe_int(row.get('Dosen Tidak Tetap', 0))
                dosen_rasio  = safe_int(row.get('Jumlah Dosen Penghitung Rasio', 0))
                rasio_str    = str(row.get('Rasio Dosen/Mahasiswa') or '').strip()[:10] or None
                mhs_aktif    = safe_int(row.get('Jumlah Mahasiswa', 0))

                if dry_run:
                    # Estimasi saja — tidak resolusi prodi baru
                    dd_exists = DataDosen.objects.filter(
                        perguruan_tinggi=pt, program_studi=prodi,
                        tahun_akademik=tahun, semester=semester,
                    ).exists()
                    dd_updated += 1 if dd_exists else 0
                    dd_created += 0 if dd_exists else 1

                    mhs_exists = DataMahasiswa.objects.filter(
                        perguruan_tinggi=pt, program_studi=prodi,
                        tahun_akademik=tahun, semester=semester,
                    ).exists()
                    mhs_updated += 1 if mhs_exists else 0
                    mhs_created += 0 if mhs_exists else 1
                    continue

                try:
                    _, was_created = DataDosen.objects.update_or_create(
                        perguruan_tinggi=pt,
                        program_studi=prodi,
                        tahun_akademik=tahun,
                        semester=semester,
                        defaults={
                            'dosen_tetap':       tetap,
                            'dosen_tidak_tetap': tidak_tetap,
                            'dosen_rasio':       dosen_rasio,
                            'rasio':             rasio_str,
                            'program_studi':     prodi,
                        },
                    )
                    dd_created += 1 if was_created else 0
                    dd_updated += 0 if was_created else 1
                except Exception as e:
                    print(f'  [ERROR] DataDosen {kode_pt} {kode_ps} {tahun} {semester}: {e}')
                    error += 1

                try:
                    _, was_created = DataMahasiswa.objects.update_or_create(
                        perguruan_tinggi=pt,
                        program_studi=prodi,
                        tahun_akademik=tahun,
                        semester=semester,
                        defaults={
                            'mahasiswa_aktif': mhs_aktif,
                            'program_studi':   prodi,
                        },
                    )
                    mhs_created += 1 if was_created else 0
                    mhs_updated += 0 if was_created else 1
                except Exception as e:
                    print(f'  [ERROR] DataMahasiswa {kode_pt} {kode_ps} {tahun} {semester}: {e}')
                    error += 1

    # Bersihkan DataDosen lama dengan program_studi=NULL (dari import sebelumnya)
    if not dry_run:
        null_deleted, _ = DataDosen.objects.filter(program_studi__isnull=True).delete()
        if null_deleted:
            print(f'\n  [CLEANUP] Hapus {null_deleted} DataDosen dengan program_studi=NULL')
        null_mhs_deleted, _ = DataMahasiswa.objects.filter(
            program_studi__isnull=True, mahasiswa_aktif=0
        ).delete()
        if null_mhs_deleted:
            print(f'  [CLEANUP] Hapus {null_mhs_deleted} DataMahasiswa NULL/kosong')

    print()
    print('=' * 60)
    print(f'SELESAI{"  [DRY-RUN]" if dry_run else ""}')
    print(f'  DataDosen    — baru: {dd_created:>6}  update: {dd_updated:>6}')
    print(f'  DataMahasiswa— baru: {mhs_created:>6}  update: {mhs_updated:>6}')
    print(f'  Dilewati (prodi tutup/alih bentuk): {skipped}')
    print(f'  Error        : {error}')
    print('=' * 60)


if __name__ == '__main__':
    main()
