"""
Update detail ProfilDosen dari file ept_itdd.json.

Match utama: NIDN
Field yang diupdate:
  - jenis_kelamin       (ept: jk)
  - jabatan_fungsional  (ept: fungsional)
  - ikatan_kerja        (ept: ikatankerja)
  - status              (ept: statuskeaktifan)
  - pendidikan_tertinggi(ept: pendidikan)
  - url_pencarian       (ept: linkdosen)

Field yang diabaikan: sekolah, tempat_lahir, idsinta, semester-cols

Usage:
    python utils/update_profildosen_ept.py
    python utils/update_profildosen_ept.py --dry-run
    python utils/update_profildosen_ept.py --batch-size 500
"""

import os
import sys
import json
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")

import django
django.setup()

from apps.universities.models import ProfilDosen

# ─── Mapping nilai ept → nilai DB ────────────────────────────────────────────

JABATAN_MAP = {
    'Profesor':      'Profesor',
    'Lektor Kepala': 'Lektor Kepala',
    'Lektor':        'Lektor',
    'Asisten Ahli':  'Asisten Ahli',
    '-':             '',
    '':              '',
}

IKATAN_MAP = {
    'Dosen Tetap':                                  'tetap',
    'Dosen Tidak Tetap':                            'tidak_tetap',
    'Dosen Tetap Perjanjian Kerja Waktu Terte':     'dtpk',
    '-':                                            '',
    'Pengajar nondosen':                            '',
    '':                                             '',
}

PEND_MAP = {
    'S3':         's3',
    'S3 Terapan': 's3',
    'S2':         's2',
    'S2 Terapan': 's2',
    'S1':         's1',
    'D4':         'lainnya',
    'Profesi':    'profesi',
    'Sp-1':       'profesi',
    'Sp-2':       'lainnya',
    '-':          '',
    '':           '',
}

STATUS_MAP = {
    'TUGAS DI INSTANSI LA': 'TUGAS DI INSTANSI LAIN',   # truncated value di ept
}


def map_jabatan(val):
    return JABATAN_MAP.get(val or '', val or '')


def map_ikatan(val):
    return IKATAN_MAP.get(val or '', '')


def map_pend(val):
    return PEND_MAP.get(val or '', 'lainnya' if val else '')


def map_jk(val):
    if val in ('L', 'P'):
        return val
    return ''


def map_status(val):
    v = (val or '').strip()
    return STATUS_MAP.get(v, v)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(dry_run: bool, batch_size: int):
    ept_path = BASE_DIR / 'utils' / 'ept' / 'ept_itdd.json'
    print(f'Membaca {ept_path} ...')
    with open(ept_path, encoding='utf-8') as f:
        raw = json.load(f)

    # Buat index ept: nidn → fields
    ept_by_nidn: dict = {}
    for rec in raw:
        fields = rec['fields']
        nidn = (fields.get('nidn') or '').strip()
        if nidn:
            ept_by_nidn[nidn] = fields

    print(f'Record ept dengan NIDN: {len(ept_by_nidn)}')

    # Ambil semua ProfilDosen yang punya NIDN & ada di ept
    nidn_set = set(ept_by_nidn.keys())
    qs = ProfilDosen.objects.filter(nidn__in=nidn_set)
    total = qs.count()
    print(f'ProfilDosen yang akan diupdate: {total}')

    if dry_run:
        print('[DRY RUN] Tidak ada perubahan yang disimpan.')

    updated = 0
    skipped = 0
    errors  = 0

    UPDATE_FIELDS = [
        'jenis_kelamin', 'jabatan_fungsional', 'ikatan_kerja',
        'status', 'pendidikan_tertinggi', 'url_pencarian',
    ]

    batch = []
    for obj in qs.iterator(chunk_size=batch_size):
        ef = ept_by_nidn.get(obj.nidn)
        if not ef:
            skipped += 1
            continue

        try:
            new_jk    = map_jk(ef.get('jk'))
            new_jab   = map_jabatan(ef.get('fungsional'))
            new_ik    = map_ikatan(ef.get('ikatankerja'))
            new_sts   = map_status(ef.get('statuskeaktifan'))
            new_pend  = map_pend(ef.get('pendidikan'))
            new_url   = (ef.get('linkdosen') or '').strip()

            changed = (
                obj.jenis_kelamin        != new_jk   or
                obj.jabatan_fungsional   != new_jab  or
                obj.ikatan_kerja         != new_ik   or
                obj.status               != new_sts  or
                obj.pendidikan_tertinggi != new_pend or
                obj.url_pencarian        != new_url
            )

            if not changed:
                skipped += 1
                continue

            obj.jenis_kelamin        = new_jk
            obj.jabatan_fungsional   = new_jab
            obj.ikatan_kerja         = new_ik
            obj.status               = new_sts
            obj.pendidikan_tertinggi = new_pend
            obj.url_pencarian        = new_url

            batch.append(obj)
            updated += 1

            if not dry_run and len(batch) >= batch_size:
                ProfilDosen.objects.bulk_update(batch, UPDATE_FIELDS)
                print(f'  bulk_update {len(batch)} rows ... (total updated: {updated})')
                batch.clear()

        except Exception as e:
            errors += 1
            print(f'  ERROR nidn={obj.nidn}: {e}')

    # Flush sisa batch
    if not dry_run and batch:
        ProfilDosen.objects.bulk_update(batch, UPDATE_FIELDS)
        print(f'  bulk_update {len(batch)} rows (flush terakhir)')

    print()
    print('=' * 50)
    print(f'Selesai.')
    print(f'  Updated : {updated}')
    print(f'  Skipped : {skipped}  (tidak berubah / tidak ada di ept)')
    print(f'  Error   : {errors}')
    if dry_run:
        print('  [DRY RUN] Tidak ada yang benar-benar disimpan.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run',    action='store_true', help='Simulasi tanpa menyimpan')
    parser.add_argument('--batch-size', type=int, default=500, help='Ukuran batch bulk_update (default 500)')
    args = parser.parse_args()
    main(dry_run=args.dry_run, batch_size=args.batch_size)
