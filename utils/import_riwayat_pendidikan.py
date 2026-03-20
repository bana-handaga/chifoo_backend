"""
Import riwayat pendidikan dosen dari ept_itdd.json ke tabel RiwayatPendidikanDosen.

Sumber: field `sekolah` di setiap record ept_itdd.json
  [{"pt": "...", "gelar": "...", "tahun": "...", "jenjang": "..."}, ...]

Strategi:
  - Match ProfilDosen by NIDN
  - Hapus riwayat lama milik dosen tersebut, lalu insert ulang (upsert by nidn)
  - Record dengan NIDN tidak ditemukan di DB dilewati

Usage:
    python utils/import_riwayat_pendidikan.py
    python utils/import_riwayat_pendidikan.py --dry-run
    python utils/import_riwayat_pendidikan.py --batch-size 500
"""

import os, sys, json, argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ptma.settings.base')

import django
django.setup()

from apps.universities.models import ProfilDosen, RiwayatPendidikanDosen
from apps.universities.utils import flag_luar_negeri

JENJANG_VALID = {'S1', 'S2', 'S2 Terapan', 'S3', 'S3 Terapan', 'D3', 'D4', 'Profesi', 'Sp-1', 'Sp-2', 'D1', 'D2'}


def clean_str(v):
    return (v or '').strip()


def clean_gelar(v):
    v = clean_str(v)
    return '' if v == '-' else v


def clean_tahun(v):
    v = clean_str(v)
    return v if v.isdigit() and len(v) == 4 else ''


def main(dry_run: bool, batch_size: int):
    ept_path = BASE_DIR / 'utils' / 'ept' / 'ept_itdd.json'
    print(f'Membaca {ept_path} ...')
    with open(ept_path, encoding='utf-8') as f:
        raw = json.load(f)

    # Build nidn → ProfilDosen.id index
    print('Membangun index ProfilDosen ...')
    nidn_to_id = {
        nidn: pk
        for nidn, pk in ProfilDosen.objects.exclude(nidn__isnull=True).exclude(nidn='')
                                            .values_list('nidn', 'id')
    }
    print(f'  ProfilDosen dengan NIDN: {len(nidn_to_id)}')

    # Kumpulkan data per nidn (ambil record pertama per nidn)
    ept_by_nidn: dict[str, list] = {}
    for rec in raw:
        ef = rec['fields']
        nidn = clean_str(ef.get('nidn'))
        sekolah = ef.get('sekolah') or []
        if nidn and nidn not in ept_by_nidn and sekolah:
            ept_by_nidn[nidn] = sekolah

    print(f'Record ept dengan NIDN unik & punya sekolah: {len(ept_by_nidn)}')

    matched   = 0
    skipped   = 0
    ins_total = 0
    batch     = []

    # Kumpulkan nidn yang akan diproses dan hapus riwayat lama sekaligus
    nidn_found = [nidn for nidn in ept_by_nidn if nidn in nidn_to_id]
    skipped    = len(ept_by_nidn) - len(nidn_found)

    if not dry_run:
        dosen_ids = [nidn_to_id[n] for n in nidn_found]
        deleted, _ = RiwayatPendidikanDosen.objects.filter(profil_dosen_id__in=dosen_ids).delete()
        print(f'Hapus riwayat lama: {deleted} baris')

    for nidn in nidn_found:
        pd_id  = nidn_to_id[nidn]
        sekolah = ept_by_nidn[nidn]
        matched += 1

        for s in sekolah:
            jenjang = clean_str(s.get('jenjang'))
            pt_asal = clean_str(s.get('pt'))
            gelar   = clean_gelar(s.get('gelar'))
            tahun   = clean_tahun(s.get('tahun'))

            # Lewati baris tanpa PT dan jenjang
            if not pt_asal and not jenjang:
                continue
            # Normalisasi jenjang terapan
            if jenjang == 'S3 Terapan':
                jenjang = 'S3'
            if jenjang == 'S2 Terapan':
                jenjang = 'S2'

            batch.append(RiwayatPendidikanDosen(
                profil_dosen_id       = pd_id,
                perguruan_tinggi_asal = pt_asal,
                gelar                 = gelar,
                jenjang               = jenjang,
                tahun_lulus           = tahun,
                is_luar_negeri        = flag_luar_negeri(pt_asal),
            ))
            ins_total += 1

        if not dry_run and len(batch) >= batch_size:
            RiwayatPendidikanDosen.objects.bulk_create(batch, ignore_conflicts=True)
            print(f'  [INSERT] {ins_total} baris (flush per batch)...')
            batch.clear()

    if not dry_run and batch:
        RiwayatPendidikanDosen.objects.bulk_create(batch, ignore_conflicts=True)
        print(f'  [INSERT] flush sisa {len(batch)} baris')

    print()
    print('=' * 55)
    print('Selesai.')
    print(f'  Dosen diproses : {matched}')
    print(f'  Dosen dilewati : {skipped} (NIDN tidak ditemukan di DB)')
    print(f'  Baris riwayat  : {ins_total}')
    if not dry_run:
        total_db = RiwayatPendidikanDosen.objects.count()
        print(f'  Total di DB    : {total_db}')
    if dry_run:
        print('  [DRY RUN] Tidak ada yang disimpan.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run',    action='store_true')
    parser.add_argument('--batch-size', type=int, default=500)
    args = parser.parse_args()
    main(dry_run=args.dry_run, batch_size=args.batch_size)
