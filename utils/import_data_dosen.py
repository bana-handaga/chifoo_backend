"""
Import / Update DataDosen (aggregate per prodi) dari dosen_homebase['Genap 2025']
di setiap *_detailprodi.json ke tabel universities_datadosen.

Usage:
    cd /home/ubuntu/_chifoo/chifoo_backend
    conda run -n chifoo python utils/import_data_dosen.py
    conda run -n chifoo python utils/import_data_dosen.py --dry-run
    conda run -n chifoo python utils/import_data_dosen.py --kode_pt 011003
"""

import os, sys, json, glob, argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ptma.settings.base')

import django
django.setup()

from apps.universities.models import PerguruanTinggi, ProgramStudi, DataDosen

OUTS_DIR = BASE_DIR / 'utils' / 'outs'
TAHUN    = '2025/2026'
SEMESTER = 'genap'
KUNCI_HB = 'Genap 2025'

S3_PEND  = {'S3', 'S3 Terapan', 'Sp-2'}
S2_PEND  = {'S2', 'S2 Terapan', 'Sp-1'}
TETAP_IK = {'Dosen Tetap'}


def aggregate(rows: list) -> dict:
    tetap = tidak_tetap = s3 = s2 = s1 = 0
    for r in rows:
        ik   = r.get('Ikatan Kerja', '')
        pend = r.get('Pendidikan', '')
        if ik in TETAP_IK:
            tetap += 1
        else:
            tidak_tetap += 1
        if pend in S3_PEND:
            s3 += 1
        elif pend in S2_PEND:
            s2 += 1
        else:
            s1 += 1
    return {
        'dosen_tetap':         tetap,
        'dosen_tidak_tetap':   tidak_tetap,
        'dosen_s3':            s3,
        'dosen_s2':            s2,
        'dosen_s1':            s1,
        'dosen_guru_besar':    0,
        'dosen_lektor_kepala': 0,
        'dosen_lektor':        0,
        'dosen_asisten_ahli':  0,
        'dosen_bersertifikat': 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--kode_pt', nargs='+', default=None)
    args = parser.parse_args()
    dry_run        = args.dry_run
    kode_pt_filter = set(args.kode_pt) if args.kode_pt else None

    if dry_run:
        print('[DRY-RUN] Tidak ada perubahan yang disimpan.')

    pt_cache    = {pt.kode_pt: pt for pt in PerguruanTinggi.objects.all()}
    prodi_cache = {
        (ps.perguruan_tinggi_id, ps.kode_prodi): ps
        for ps in ProgramStudi.objects.all()
    }
    print(f'PT di DB     : {len(pt_cache)}')
    print(f'Prodi di DB  : {len(prodi_cache)}')

    files = sorted(glob.glob(str(OUTS_DIR / '**' / '*_detailprodi.json'), recursive=True))
    if kode_pt_filter:
        files = [f for f in files if Path(f).parent.name in kode_pt_filter]
    print(f'File         : {len(files)}')
    print()

    created = updated = skipped = error = no_hb = 0
    pt_missing = set()

    for i, fpath in enumerate(files, 1):
        try:
            d = json.load(open(fpath, encoding='utf-8'))
        except Exception as e:
            print(f'  [ERROR] baca {fpath}: {e}')
            error += 1
            continue

        kode_pt = str(d.get('kode_pt', '')).strip()
        kode_ps = str(d.get('kode_ps', '')).strip()
        if not kode_pt or not kode_ps:
            skipped += 1
            continue

        if kode_pt not in pt_cache:
            pt_missing.add(kode_pt)
            skipped += 1
            continue

        pt   = pt_cache[kode_pt]
        rows = d.get('dosen_homebase', {}).get(KUNCI_HB, [])
        if not rows:
            no_hb += 1
            continue

        prodi  = prodi_cache.get((pt.id, kode_ps))
        counts = aggregate(rows)

        if dry_run:
            exists = DataDosen.objects.filter(
                perguruan_tinggi=pt, program_studi=prodi,
                tahun_akademik=TAHUN, semester=SEMESTER,
            ).exists()
            updated += 1 if exists else 0
            created += 0 if exists else 1
            continue

        try:
            _, was_created = DataDosen.objects.update_or_create(
                perguruan_tinggi=pt,
                program_studi=prodi,
                tahun_akademik=TAHUN,
                semester=SEMESTER,
                defaults=counts,
            )
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as e:
            print(f'  [ERROR] simpan {kode_pt}/{kode_ps}: {e}')
            error += 1

        if i % 500 == 0:
            print(f'  [{i}/{len(files)}] created={created} updated={updated} no_hb={no_hb} error={error}')

    print()
    print('=' * 55)
    print(f'SELESAI{"  [DRY-RUN]" if dry_run else ""}')
    print(f'  Dibuat baru   : {created}')
    print(f'  Diupdate      : {updated}')
    print(f'  Tanpa data HB : {no_hb}')
    print(f'  Dilewati      : {skipped}')
    print(f'  Error         : {error}')
    print(f'  Total file    : {len(files)}')
    if pt_missing:
        print(f'  PT tidak ada di DB ({len(pt_missing)}): {sorted(pt_missing)}')
    print('=' * 55)


if __name__ == '__main__':
    main()
