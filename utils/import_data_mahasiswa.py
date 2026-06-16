"""
Import / Update DataMahasiswa dari field 'mahasiswa' di *_detailprodi.json
untuk 5 semester terakhir ke tabel universities_datamahasiswa.

Sumber data: jumlah_mahasiswa → disimpan ke mahasiswa_aktif
             (data scrape hanya punya total aktif, bukan breakdown baru/lulus/dropout/pria/wanita)

Kunci upsert: (perguruan_tinggi, program_studi, tahun_akademik, semester)
DataMahasiswa tidak punya unique_together — script ini menangani duplikat dengan:
  - 1 baris ditemukan → update
  - 0 baris → create
  - >1 baris → update yang pertama, hapus sisanya

Usage:
    cd /home/ubuntu/_chifoo/chifoo_backend
    conda run -n chifoo python utils/import_data_mahasiswa.py
    conda run -n chifoo python utils/import_data_mahasiswa.py --dry-run
    conda run -n chifoo python utils/import_data_mahasiswa.py --kode_pt 011003
"""

import os, sys, json, glob, argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ptma.settings.base')

import django
django.setup()

from apps.universities.models import PerguruanTinggi, ProgramStudi, DataMahasiswa

OUTS_DIR = BASE_DIR / 'utils' / 'outs'

# 5 semester terakhir yang akan diimport (format di JSON)
TARGET_SEMESTERS = {
    '2025/2026 Genap':  ('2025/2026', 'genap'),
    '2025/2026 Ganjil': ('2025/2026', 'ganjil'),
    '2024/2025 Genap':  ('2024/2025', 'genap'),
    '2024/2025 Ganjil': ('2024/2025', 'ganjil'),
    '2023/2024 Genap':  ('2023/2024', 'genap'),
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

    pt_cache = {pt.kode_pt: pt for pt in PerguruanTinggi.objects.all()}
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
    print(f'Semester     : {list(TARGET_SEMESTERS.keys())}')
    print()

    created = updated = skipped = cleaned = error = 0
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

        pt    = pt_cache[kode_pt]
        prodi = prodi_cache.get((pt.id, kode_ps))

        rows = d.get('mahasiswa', [])
        if not rows:
            skipped += 1
            continue

        # Index berdasarkan semester label
        mhs_by_sem = {r.get('semester', ''): r for r in rows}

        for sem_label, (tahun, sem) in TARGET_SEMESTERS.items():
            row = mhs_by_sem.get(sem_label)
            if row is None:
                continue

            try:
                jumlah = int(row.get('jumlah_mahasiswa', 0) or 0)
            except (ValueError, TypeError):
                jumlah = 0

            defaults = {'mahasiswa_aktif': jumlah}

            try:
                _, was_created = DataMahasiswa.objects.update_or_create(
                    perguruan_tinggi=pt,
                    program_studi=prodi,
                    tahun_akademik=tahun,
                    semester=sem,
                    defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                print(f'  [ERROR] {kode_pt}/{kode_ps} {tahun} {sem}: {e}')
                error += 1

        if i % 500 == 0:
            print(f'  [{i}/{len(files)}] created={created} updated={updated} cleaned={cleaned} error={error}')

    print()
    print('=' * 55)
    print(f'SELESAI{"  [DRY-RUN]" if dry_run else ""}')
    print(f'  Dibuat baru    : {created}')
    print(f'  Diupdate       : {updated}')
    print(f'  Duplikat hapus : {cleaned}')
    print(f'  Dilewati       : {skipped}')
    print(f'  Error          : {error}')
    print(f'  Total file     : {len(files)}')
    if pt_missing:
        print(f'  PT tidak ada di DB ({len(pt_missing)}): {sorted(pt_missing)}')
    print('=' * 55)


if __name__ == '__main__':
    main()
