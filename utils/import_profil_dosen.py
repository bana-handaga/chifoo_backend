"""
Import / Update ProfilDosen dari file *_detaildosen.json di folder outs/
ke tabel universities_profildosen.

Kunci upsert:
  - Dosen ber-NIDN  : update_or_create(perguruan_tinggi, nidn)
  - Dosen tanpa NIDN: coba match via (perguruan_tinggi, nuptk),
                      jika tidak ada → insert baru

Usage:
    cd /home/ubuntu/_chifoo/chifoo_backend
    conda run -n chifoo python utils/import_profil_dosen.py
    conda run -n chifoo python utils/import_profil_dosen.py --dry-run
    conda run -n chifoo python utils/import_profil_dosen.py --kode_pt 011003
"""

import os, sys, json, glob, argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ptma.settings.base')

import django
django.setup()

from apps.universities.models import PerguruanTinggi, ProgramStudi, ProfilDosen

OUTS_DIR = BASE_DIR / 'utils' / 'outs'

# ── Mapping nilai ───────────────────────────────────────────────────────────
JK_MAP = {
    'laki-laki': 'L',
    'laki':      'L',
    'l':         'L',
    'perempuan': 'P',
    'wanita':    'P',
    'p':         'P',
}

PEND_MAP = {
    's3':         's3',
    's3 terapan': 's3',
    'sp-2':       's3',
    's2':         's2',
    's2 terapan': 's2',
    'sp-1':       's2',
    's1':         's1',
    'd4':         's1',
    'profesi':    'profesi',
}

IK_MAP = {
    'dosen tetap': 'tetap',
    'dosen tetap perjanjian kerja waktu tertentu': 'tidak_tetap',
    'dosen tidak tetap': 'tidak_tetap',
}


def map_jk(raw: str) -> str:
    return JK_MAP.get(str(raw).strip().lower(), '')


def map_pend(raw: str) -> str:
    return PEND_MAP.get(str(raw).strip().lower(), 'lainnya')


def map_ik(raw: str) -> str:
    return IK_MAP.get(str(raw).strip().lower(), '')


def build_defaults(profil: dict, source: dict, top: dict, prodi_obj) -> dict:
    nama  = (profil.get('Nama') or source.get('nama') or '').strip()[:200]
    nuptk = (profil.get('NUPTK') or source.get('nuptk') or '').strip()[:20]
    jk    = map_jk(profil.get('Jenis Kelamin', ''))
    jabat = str(profil.get('Jabatan Fungsional') or '').strip()[:50]
    pend  = map_pend(profil.get('Pendidikan Tertinggi') or source.get('pendidikan', ''))
    ik    = map_ik(profil.get('Ikatan Kerja', ''))
    stat  = str(profil.get('Status Aktif') or source.get('status') or '').strip()[:30]
    prodi_nama = str(profil.get('Program Studi') or '').strip()[:200]
    url   = str(top.get('url_pencarian') or '').strip()[:500]

    return {
        'nuptk':               nuptk,
        'nama':                nama,
        'jenis_kelamin':       jk,
        'jabatan_fungsional':  jabat,
        'pendidikan_tertinggi': pend,
        'ikatan_kerja':        ik,
        'status':              stat,
        'program_studi_nama':  prodi_nama,
        'program_studi':       prodi_obj,
        'url_pencarian':       url,
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

    # Cache PT dan Prodi
    pt_cache    = {pt.kode_pt: pt for pt in PerguruanTinggi.objects.all()}
    # prodi cache: (pt_id, nama_lower) → ProgramStudi
    prodi_cache: dict[tuple, ProgramStudi] = {}
    for ps in ProgramStudi.objects.all():
        prodi_cache[(ps.perguruan_tinggi_id, ps.nama.strip().lower())] = ps

    # Cache NUPTK yang sudah ada (untuk dosen tanpa NIDN)
    nuptk_cache: dict[tuple, int] = {
        (pd.perguruan_tinggi_id, pd.nuptk): pd.id
        for pd in ProfilDosen.objects.exclude(nuptk='').filter(nidn__isnull=True)
    }

    print(f'PT di DB         : {len(pt_cache)}')
    print(f'Prodi di DB      : {len(prodi_cache)}')

    files = sorted(glob.glob(str(OUTS_DIR / '**' / '*_detaildosen.json'), recursive=True))
    if kode_pt_filter:
        files = [f for f in files if Path(f).parent.parent.name in kode_pt_filter]
    print(f'File detaildosen : {len(files)}')
    print()

    created = updated = skipped = error = 0
    pt_missing = set()

    for i, fpath in enumerate(files, 1):
        try:
            d = json.load(open(fpath, encoding='utf-8'))
        except Exception as e:
            print(f'  [ERROR] baca {fpath}: {e}')
            error += 1
            continue

        source  = d.get('source', {})
        profil  = d.get('profil', {})
        kode_pt = str(source.get('kode_pt', '')).strip()
        nidn    = str(source.get('nidn') or '').strip() or None
        nuptk   = str(source.get('nuptk') or profil.get('NUPTK') or '').strip()

        if not kode_pt:
            skipped += 1
            continue

        if kode_pt not in pt_cache:
            pt_missing.add(kode_pt)
            skipped += 1
            continue

        pt = pt_cache[kode_pt]

        # Cari prodi FK via nama prodi di profil
        prodi_nama_raw = str(profil.get('Program Studi') or '').strip()
        prodi_obj = prodi_cache.get((pt.id, prodi_nama_raw.lower()))

        defaults = build_defaults(profil, source, d, prodi_obj)

        if dry_run:
            if nidn:
                exists = ProfilDosen.objects.filter(perguruan_tinggi=pt, nidn=nidn).exists()
            elif nuptk:
                exists = ProfilDosen.objects.filter(
                    perguruan_tinggi=pt, nidn__isnull=True, nuptk=nuptk
                ).exists()
            else:
                exists = False
            updated += 1 if exists else 0
            created += 0 if exists else 1
            continue

        try:
            if nidn:
                _, was_created = ProfilDosen.objects.update_or_create(
                    perguruan_tinggi=pt,
                    nidn=nidn,
                    defaults=defaults,
                )
            elif nuptk:
                # Coba match via NUPTK untuk dosen tanpa NIDN
                key = (pt.id, nuptk)
                if key in nuptk_cache:
                    ProfilDosen.objects.filter(id=nuptk_cache[key]).update(**defaults)
                    was_created = False
                else:
                    obj = ProfilDosen.objects.create(
                        perguruan_tinggi=pt,
                        nidn=None,
                        **defaults,
                    )
                    nuptk_cache[key] = obj.id
                    was_created = True
            else:
                # Tidak ada NIDN maupun NUPTK — insert baru
                ProfilDosen.objects.create(perguruan_tinggi=pt, nidn=None, **defaults)
                was_created = True

            if was_created:
                created += 1
            else:
                updated += 1

        except Exception as e:
            print(f'  [ERROR] simpan {fpath}: {e}')
            error += 1

        if i % 2000 == 0:
            print(f'  [{i}/{len(files)}] created={created} updated={updated} error={error}')

    print()
    print('=' * 55)
    print(f'SELESAI{"  [DRY-RUN]" if dry_run else ""}')
    print(f'  Dibuat baru  : {created}')
    print(f'  Diupdate     : {updated}')
    print(f'  Dilewati     : {skipped}')
    print(f'  Error        : {error}')
    print(f'  Total file   : {len(files)}')
    if pt_missing:
        print(f'  PT tidak ada di DB ({len(pt_missing)}): {sorted(pt_missing)}')
    print('=' * 55)


if __name__ == '__main__':
    main()
