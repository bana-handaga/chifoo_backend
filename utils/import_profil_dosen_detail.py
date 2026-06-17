"""
Import ProfilDosen dan RiwayatPendidikanDosen dari file JSON
di folder utils/outs/dosen/{kode_pt}/*.json

Format file: {nidn}_{nama}.json (hasil scrape scrape_pddikti_detaildosen*.py)
Struktur JSON:
  - profil      : dict → ProfilDosen
  - riwayat_pendidikan : list → RiwayatPendidikanDosen
  - input       : dict (nidn, nuptk, pt_kode, dll)
  - url_pencarian: str

Upsert ProfilDosen: (perguruan_tinggi, nidn) untuk dosen ber-NIDN;
                    (perguruan_tinggi, nuptk) untuk dosen tanpa NIDN.
RiwayatPendidikanDosen: hapus lama lalu insert ulang (tidak ada unique key).

Usage:
    cd /home/ubuntu/_chifoo/chifoo_backend
    conda run -n chifoo python utils/import_profil_dosen_detail.py
    conda run -n chifoo python utils/import_profil_dosen_detail.py --dry-run
    conda run -n chifoo python utils/import_profil_dosen_detail.py --kode_pt 213388 213539
"""

import os, sys, json, glob, argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ptma.settings.base')

import django
django.setup()

from apps.universities.models import (
    PerguruanTinggi, ProgramStudi, ProfilDosen, RiwayatPendidikanDosen
)

DOSEN_DIR = BASE_DIR / 'utils' / 'outs' / 'dosen'

# ── Mapping ──────────────────────────────────────────────────────────────────
JK_MAP = {
    'laki-laki': 'L', 'laki': 'L', 'l': 'L',
    'perempuan': 'P', 'wanita': 'P', 'p': 'P',
}
PEND_MAP = {
    's3': 's3', 's3 terapan': 's3', 'sp-2': 's3',
    's2': 's2', 's2 terapan': 's2', 'sp-1': 's2',
    's1': 's1', 'd4': 's1',
    'profesi': 'profesi',
}
IK_MAP = {
    'dosen tetap': 'tetap',
    'dosen tetap perjanjian kerja waktu tertentu': 'tidak_tetap',
    'dosen tidak tetap': 'tidak_tetap',
}

# Kata kunci PT Indonesia — jika nama PT mengandung salah satu ini → dalam negeri
_ID_KEYWORDS = {
    'universitas', 'institut', 'sekolah tinggi', 'politeknik', 'akademi',
    'stai', 'stie', 'stikes', 'stkip', 'stmik', 'stiab', 'stit',
    'uin', 'iain', 'uii', 'itb', 'ugm', 'ui', 'ipb',
    'muhammadiyah', 'aisyiyah', 'nahdlatul', 'indonesia',
}


def map_jk(raw: str) -> str:
    return JK_MAP.get(str(raw).strip().lower(), '')


def map_pend(raw: str) -> str:
    return PEND_MAP.get(str(raw).strip().lower(), 'lainnya')


def map_ik(raw: str) -> str:
    return IK_MAP.get(str(raw).strip().lower(), '')


def is_luar_negeri(pt_name: str) -> bool:
    low = pt_name.strip().lower()
    return not any(kw in low for kw in _ID_KEYWORDS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--kode_pt', nargs='+', default=None)
    args = parser.parse_args()
    dry_run        = args.dry_run
    kode_pt_filter = set(args.kode_pt) if args.kode_pt else None

    if dry_run:
        print('[DRY-RUN] Tidak ada perubahan yang disimpan.')

    # ── Cache ──────────────────────────────────────────────────────────────
    pt_cache = {pt.kode_pt: pt for pt in PerguruanTinggi.objects.all()}
    prodi_cache: dict[tuple, ProgramStudi] = {}
    for ps in ProgramStudi.objects.all():
        prodi_cache[(ps.perguruan_tinggi_id, ps.nama.strip().lower())] = ps

    nuptk_cache: dict[tuple, int] = {
        (pd.perguruan_tinggi_id, pd.nuptk): pd.id
        for pd in ProfilDosen.objects.exclude(nuptk='').filter(nidn__isnull=True)
    }

    print(f'PT di DB    : {len(pt_cache)}')
    print(f'Prodi di DB : {len(prodi_cache)}')

    # ── Kumpulkan file ─────────────────────────────────────────────────────
    folders = sorted(p for p in DOSEN_DIR.iterdir() if p.is_dir())
    if kode_pt_filter:
        folders = [f for f in folders if f.name in kode_pt_filter]

    files = []
    for folder in folders:
        files.extend(sorted(folder.glob('*.json')))

    print(f'Folder PT   : {len(folders)}')
    print(f'File JSON   : {len(files)}')
    print()

    pd_created = pd_updated = rp_created = skipped = error = 0
    pt_missing = set()

    for fpath in files:
        try:
            d = json.load(open(fpath, encoding='utf-8'))
        except Exception as e:
            print(f'  [ERROR] baca {fpath.name}: {e}')
            error += 1
            continue

        inp    = d.get('input', {})
        profil = d.get('profil', {})

        kode_pt = str(inp.get('pt_kode') or fpath.parent.name).strip()
        nidn    = str(inp.get('nidn') or '').strip() or None
        nuptk   = str(inp.get('nuptk') or profil.get('NUPTK') or '').strip()

        if kode_pt not in pt_cache:
            pt_missing.add(kode_pt)
            skipped += 1
            continue

        pt = pt_cache[kode_pt]

        # Resolve program studi FK
        prodi_nama_raw = str(profil.get('Program Studi') or '').strip()
        prodi_obj = prodi_cache.get((pt.id, prodi_nama_raw.lower()))

        # Nama dosen
        _nm = str(profil.get('Nama') or '').strip()
        nama = (_nm if _nm and _nm != '...' else str(inp.get('nama') or _nm)).strip()[:200]

        defaults = {
            'nuptk':               nuptk,
            'nama':                nama,
            'jenis_kelamin':       map_jk(profil.get('Jenis Kelamin', '')),
            'jabatan_fungsional':  str(profil.get('Jabatan Fungsional') or '').strip()[:50],
            'pendidikan_tertinggi': map_pend(
                profil.get('Pendidikan Tertinggi') or inp.get('pendidikan', '')
            ),
            'ikatan_kerja':        map_ik(profil.get('Ikatan Kerja', '')),
            'status':              str(profil.get('Status Aktif') or inp.get('status') or '').strip()[:30],
            'program_studi_nama':  prodi_nama_raw,
            'program_studi':       prodi_obj,
            'url_pencarian':       str(d.get('url_pencarian') or '').strip()[:500],
        }

        if dry_run:
            if nidn:
                exists = ProfilDosen.objects.filter(perguruan_tinggi=pt, nidn=nidn).exists()
            elif nuptk:
                exists = ProfilDosen.objects.filter(
                    perguruan_tinggi=pt, nidn__isnull=True, nuptk=nuptk
                ).exists()
            else:
                exists = False
            pd_updated += 1 if exists else 0
            pd_created += 0 if exists else 1
            rp_created += len(d.get('riwayat_pendidikan') or [])
            continue

        # ── Upsert ProfilDosen ────────────────────────────────────────────
        try:
            if nidn:
                profil_obj, was_created = ProfilDosen.objects.update_or_create(
                    perguruan_tinggi=pt, nidn=nidn, defaults=defaults
                )
            elif nuptk:
                key = (pt.id, nuptk)
                if key in nuptk_cache:
                    ProfilDosen.objects.filter(id=nuptk_cache[key]).update(**defaults)
                    profil_obj = ProfilDosen.objects.get(id=nuptk_cache[key])
                    was_created = False
                else:
                    profil_obj = ProfilDosen.objects.create(
                        perguruan_tinggi=pt, nidn=None, **defaults
                    )
                    nuptk_cache[key] = profil_obj.id
                    was_created = True
            else:
                profil_obj = ProfilDosen.objects.create(
                    perguruan_tinggi=pt, nidn=None, **defaults
                )
                was_created = True

            pd_created += 1 if was_created else 0
            pd_updated += 0 if was_created else 1

        except Exception as e:
            print(f'  [ERROR] ProfilDosen {fpath.name}: {e}')
            error += 1
            continue

        # ── Import RiwayatPendidikanDosen ─────────────────────────────────
        riwayat_list = d.get('riwayat_pendidikan') or []
        if isinstance(riwayat_list, list) and riwayat_list:
            profil_obj.riwayat_pendidikan.all().delete()
            objs = []
            for rw in riwayat_list:
                if not isinstance(rw, dict):
                    continue
                pt_asal = str(rw.get('Perguruan Tinggi') or '').strip()[:300]
                gelar   = str(rw.get('Gelar Akademik') or '').strip()[:150]
                jenjang = str(rw.get('Jenjang') or '').strip()[:20]
                tahun   = str(rw.get('Tahun') or '').strip()[:4]
                luar_neg = is_luar_negeri(pt_asal) if pt_asal else False
                objs.append(RiwayatPendidikanDosen(
                    profil_dosen=profil_obj,
                    perguruan_tinggi_asal=pt_asal,
                    gelar=gelar,
                    jenjang=jenjang,
                    tahun_lulus=tahun,
                    is_luar_negeri=luar_neg,
                ))
            if objs:
                RiwayatPendidikanDosen.objects.bulk_create(objs)
                rp_created += len(objs)

    print()
    print('=' * 55)
    print(f'SELESAI{"  [DRY-RUN]" if dry_run else ""}')
    print(f'  ProfilDosen baru      : {pd_created}')
    print(f'  ProfilDosen update    : {pd_updated}')
    print(f'  RiwayatPendidikan baru: {rp_created}')
    print(f'  Dilewati              : {skipped}')
    print(f'  Error                 : {error}')
    if pt_missing:
        print(f'  PT tidak ada di DB    : {sorted(pt_missing)}')
    print('=' * 55)


if __name__ == '__main__':
    main()
