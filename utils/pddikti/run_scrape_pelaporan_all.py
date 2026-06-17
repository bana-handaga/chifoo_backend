"""
Runner: scrape Data Pelaporan per PT untuk semua PT aktif di DB.
Output: outs/{kode_pt}/{kode_pt}_listprodi.json

Usage:
    cd /home/ubuntu/_chifoo/chifoo_backend/utils/pddikti
    conda run -n chifoo python run_scrape_pelaporan_all.py
    conda run -n chifoo python run_scrape_pelaporan_all.py --semester 12
    conda run -n chifoo python run_scrape_pelaporan_all.py --resume
    conda run -n chifoo python run_scrape_pelaporan_all.py --kode_pt 011003 051007
"""

import os, sys, time, argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ptma.settings.base')

import django
django.setup()

from apps.universities.models import PerguruanTinggi
from scrape_pddikti_pelaporan import main as scrape_main

OUT_DIR = BASE_DIR / 'utils' / 'outs'

# PT dengan nama panjang+tanda kurung yang tidak bisa dicari di PDDikti dengan nama penuh.
# Gunakan keyword pendek agar search berhasil.
KEYWORD_OVERRIDE = {
    '213388': 'staim blora',
    '213539': 'stebis sumedang',
}


def already_done(kode_pt: str) -> bool:
    return (OUT_DIR / kode_pt / f'{kode_pt}_listprodi.json').exists()


def run(n_semester: int, resume: bool, kode_pt_filter: list):
    pts = list(
        PerguruanTinggi.objects.filter(is_active=True)
        .order_by('kode_pt')
        .values('kode_pt', 'nama')
    )
    if kode_pt_filter:
        pts = [p for p in pts if p['kode_pt'] in kode_pt_filter]

    total = len(pts)
    done_count = skip_count = error_count = 0

    print(f'Total PT: {total} | Semester: {n_semester} | Resume: {resume}')
    print()

    for i, pt in enumerate(pts, 1):
        kode_pt  = pt['kode_pt']
        nama_pt  = pt['nama']
        keyword  = KEYWORD_OVERRIDE.get(kode_pt, nama_pt.lower())

        if resume and already_done(kode_pt):
            print(f'[{i}/{total}] SKIP (sudah ada): {kode_pt} {nama_pt[:40]}')
            skip_count += 1
            continue

        print(f'\n[{i}/{total}] {kode_pt} — {nama_pt}')
        try:
            scrape_main(
                keyword=keyword,
                nama_pt_target=nama_pt.upper(),
                kode_pt=kode_pt,
                n_semester=n_semester,
            )
            done_count += 1
        except Exception as e:
            print(f'  [ERROR] {kode_pt}: {e}')
            error_count += 1

        # Jeda antar PT agar tidak membebani server
        time.sleep(3)

    print()
    print('=' * 55)
    print(f'SELESAI')
    print(f'  Berhasil : {done_count}')
    print(f'  Dilewati : {skip_count}')
    print(f'  Error    : {error_count}')
    print(f'  Total    : {total}')
    print('=' * 55)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--semester', type=int, default=12,
                        help='Jumlah semester terakhir (default: 12)')
    parser.add_argument('--resume', action='store_true',
                        help='Lewati PT yang sudah punya file output')
    parser.add_argument('--kode_pt', nargs='+', default=None,
                        help='Filter kode PT tertentu saja')
    args = parser.parse_args()

    run(
        n_semester=args.semester,
        resume=args.resume,
        kode_pt_filter=set(args.kode_pt) if args.kode_pt else None,
    )
