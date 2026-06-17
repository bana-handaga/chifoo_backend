"""
Import DosenSemester dari file *_detailprodi.json.

Sumber: utils/outs/{kode_pt}/*_detailprodi.json
Field:  dosen_homebase → { "Gasal 2025": [...], "Genap 2025": [...], ... }
        Tiap row: { "NIDN", "NUPTK", "Nama", "Status", "Ikatan Kerja", ... }

Mapping label → (tahun_akademik, semester):
  "Gasal YYYY"  → (YYYY/YYYY+1, ganjil)
  "Ganjil YYYY" → (YYYY/YYYY+1, ganjil)
  "Genap YYYY"  → (YYYY/YYYY+1, genap)

Usage:
    cd /home/ubuntu/_chifoo/chifoo_backend
    conda run -n chifoo python utils/import_dosen_semester.py
    conda run -n chifoo python utils/import_dosen_semester.py --dry-run
    conda run -n chifoo python utils/import_dosen_semester.py --label "Gasal 2025"
    conda run -n chifoo python utils/import_dosen_semester.py --kode_pt 011003 032023
"""

import os, sys, json, argparse
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ptma.settings.production')

import django
django.setup()

from django.db import transaction
from apps.universities.models import PerguruanTinggi, ProfilDosen, DosenSemester

OUTS_DIR = BASE_DIR / 'utils' / 'outs'

IK_MAP = {
    'dosen tetap': 'tetap',
    'dosen tetap perjanjian kerja waktu tertentu': 'tetap',
    'dosen tidak tetap': 'tidak_tetap',
}


def parse_label(label: str):
    """'Gasal 2025' → ('2025/2026', 'ganjil')  |  'Genap 2024' → ('2024/2025', 'genap')"""
    parts = label.strip().split()
    if len(parts) < 2:
        return None, None
    tipe, yr_str = parts[0].lower(), parts[1]
    try:
        yr = int(yr_str)
    except ValueError:
        return None, None
    if tipe in ('gasal', 'ganjil'):
        return f'{yr}/{yr + 1}', 'ganjil'
    elif tipe == 'genap':
        return f'{yr}/{yr + 1}', 'genap'
    return None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run',  action='store_true')
    parser.add_argument('--label',    nargs='+', default=None,
                        help='Filter label semester, mis: "Gasal 2025" "Genap 2025"')
    parser.add_argument('--kode_pt',  nargs='+', default=None)
    args = parser.parse_args()

    dry_run       = args.dry_run
    label_filter  = {l.strip() for l in args.label} if args.label else None
    kode_pt_filter = set(args.kode_pt) if args.kode_pt else None

    if dry_run:
        print('[DRY-RUN] Tidak ada perubahan yang disimpan.')

    # Cache PT dan ProfilDosen
    pt_cache    = {pt.kode_pt: pt for pt in PerguruanTinggi.objects.all()}
    # nidn → profil_dosen_id
    nidn_cache  = {
        pd.nidn: pd.id
        for pd in ProfilDosen.objects.exclude(nidn__isnull=True).exclude(nidn='')
    }
    # (pt_id, nuptk) → profil_dosen_id  (untuk dosen tanpa NIDN)
    nuptk_cache = {
        (pd.perguruan_tinggi_id, pd.nuptk): pd.id
        for pd in ProfilDosen.objects.filter(nidn__isnull=True).exclude(nuptk='')
    }

    # Kumpulkan file detailprodi
    pt_dirs = sorted(p for p in OUTS_DIR.iterdir() if p.is_dir())
    if kode_pt_filter:
        pt_dirs = [d for d in pt_dirs if d.name in kode_pt_filter]

    files = []
    for pt_dir in pt_dirs:
        files.extend(sorted(pt_dir.glob('*_detailprodi.json')))

    print(f'PT dirs : {len(pt_dirs)}')
    print(f'Files   : {len(files)}')

    # Kumpulkan semua (profil_dosen_id, tahun_akademik, semester) yang akan di-upsert
    # key: (pd_id, tahun, sem)  value: {ikatan_kerja, status}
    to_upsert: dict[tuple, dict] = {}
    pt_missing = set()
    pd_missing = 0

    for fpath in files:
        try:
            d = json.load(open(fpath, encoding='utf-8'))
        except Exception as e:
            print(f'  [ERROR] baca {fpath.name}: {e}')
            continue

        kode_pt = str(d.get('kode_pt') or fpath.parent.name).strip()
        if kode_pt not in pt_cache:
            pt_missing.add(kode_pt)
            continue
        pt = pt_cache[kode_pt]

        hb = d.get('dosen_homebase', {})
        for label, rows in hb.items():
            if label_filter and label not in label_filter:
                continue
            tahun, sem = parse_label(label)
            if not tahun:
                continue
            if not isinstance(rows, list):
                continue

            for row in rows:
                nidn  = str(row.get('NIDN',  '') or '').strip()
                nuptk = str(row.get('NUPTK', '') or '').strip()
                if nidn in ('', '0'):
                    nidn = None

                # Resolve profil_dosen_id
                pd_id = None
                if nidn:
                    pd_id = nidn_cache.get(nidn)
                if pd_id is None and nuptk and nuptk != '0':
                    pd_id = nuptk_cache.get((pt.id, nuptk))

                if pd_id is None:
                    pd_missing += 1
                    continue

                ik_raw = str(row.get('Ikatan Kerja', '') or '').strip().lower()
                ik     = IK_MAP.get(ik_raw, '')
                status = str(row.get('Status', '') or '').strip()

                key = (pd_id, tahun, sem)
                to_upsert[key] = {'ikatan_kerja': ik, 'status': status}

    print(f'Record upsert : {len(to_upsert):,}')
    print(f'Dosen not found : {pd_missing:,}')
    if pt_missing:
        print(f'PT missing  : {sorted(pt_missing)}')

    if dry_run:
        # Hitung existing untuk laporan
        existing = DosenSemester.objects.count()
        print(f'DosenSemester saat ini : {existing:,}')
        print('[DRY-RUN] Selesai.')
        return

    # Bulk upsert dalam batch
    BATCH = 2000
    keys_list = list(to_upsert.keys())

    # Ambil existing untuk split create/update
    existing_set = set(
        DosenSemester.objects
        .values_list('profil_dosen_id', 'tahun_akademik', 'semester')
    )

    to_create = [k for k in keys_list if k not in existing_set]
    to_update = [k for k in keys_list if k in existing_set]

    created = updated = 0

    # Bulk create
    for i in range(0, len(to_create), BATCH):
        batch = to_create[i:i + BATCH]
        objs  = [
            DosenSemester(
                profil_dosen_id=k[0],
                tahun_akademik=k[1],
                semester=k[2],
                ikatan_kerja=to_upsert[k]['ikatan_kerja'],
                status=to_upsert[k]['status'],
            )
            for k in batch
        ]
        with transaction.atomic():
            DosenSemester.objects.bulk_create(objs, ignore_conflicts=True)
        created += len(objs)
        print(f'  create {created}/{len(to_create)}', end='\r')
    print()

    # Bulk update (per batch menggunakan update)
    for i in range(0, len(to_update), BATCH):
        batch = to_update[i:i + BATCH]
        with transaction.atomic():
            for k in batch:
                DosenSemester.objects.filter(
                    profil_dosen_id=k[0],
                    tahun_akademik=k[1],
                    semester=k[2],
                ).update(**to_upsert[k])
        updated += len(batch)
        print(f'  update {updated}/{len(to_update)}', end='\r')
    print()

    total = DosenSemester.objects.count()
    print()
    print('=' * 50)
    print('SELESAI')
    print(f'  Dibuat  : {created:,}')
    print(f'  Diupdate: {updated:,}')
    print(f'  Total DB: {total:,}')
    print('=' * 50)


if __name__ == '__main__':
    main()
