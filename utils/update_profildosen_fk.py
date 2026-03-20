"""
Upsert ProfilDosen dari ept_itdd.json:
  - UPDATE  : record yang sudah ada (match by NIDN) → koreksi FK + semua field detail
  - INSERT  : record baru (NIDN belum ada di DB) → buat ProfilDosen baru

Resolusi FK:
  kodept  → perguruan_tinggi_id  (kode_pt di PerguruanTinggi)
  kodeps  → program_studi_id     (kode_prodi dalam PT, kombinasi pt_id+kodeps)

Field yang diisi/diupdate:
  nidn, nama, jenis_kelamin, perguruan_tinggi_id, program_studi_id,
  program_studi_nama, jabatan_fungsional, pendidikan_tertinggi,
  ikatan_kerja, status, url_pencarian

Field yang diabaikan: sekolah, tempat_lahir, idsinta, kolom semester

Usage:
    python utils/update_profildosen_fk.py
    python utils/update_profildosen_fk.py --dry-run
    python utils/update_profildosen_fk.py --report-only
    python utils/update_profildosen_fk.py --batch-size 500
"""

import os, sys, json, argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")

import django
django.setup()

from apps.universities.models import PerguruanTinggi, ProgramStudi, ProfilDosen


# ─── Mapping nilai ept → nilai DB ────────────────────────────────────────────

JABATAN_MAP = {
    'Profesor':      'Profesor',
    'Lektor Kepala': 'Lektor Kepala',
    'Lektor':        'Lektor',
    'Asisten Ahli':  'Asisten Ahli',
    '-':             '',
}

IKATAN_MAP = {
    'Dosen Tetap':                              'tetap',
    'Dosen Tidak Tetap':                        'tidak_tetap',
    'Dosen Tetap Perjanjian Kerja Waktu Terte': 'dtpk',
    '-':                                        '',
    'Pengajar nondosen':                        '',
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
}

STATUS_REMAP = {'TUGAS DI INSTANSI LA': 'TUGAS DI INSTANSI LAIN'}


def _jab(v):   return JABATAN_MAP.get(v or '', v or '')
def _ik(v):    return IKATAN_MAP.get(v or '', '')
def _pend(v):  return PEND_MAP.get(v or '', 'lainnya' if v else '')
def _jk(v):    return v if v in ('L', 'P') else ''
def _sts(v):   v = (v or '').strip(); return STATUS_REMAP.get(v, v)
def _str(v):   return (v or '').strip()


# ─── Build lookup indexes dari DB ────────────────────────────────────────────

def build_indexes():
    pt_idx = {
        kode: pk
        for kode, pk in PerguruanTinggi.objects.values_list('kode_pt', 'id')
        if kode
    }
    ps_idx = {
        (pt_id, kode): pk
        for kode, pk, pt_id in ProgramStudi.objects.values_list('kode_prodi', 'id', 'perguruan_tinggi_id')
        if kode
    }
    return pt_idx, ps_idx


# ─── Main ─────────────────────────────────────────────────────────────────────

UPDATE_FIELDS = [
    'perguruan_tinggi_id', 'program_studi_id', 'program_studi_nama',
    'jenis_kelamin', 'jabatan_fungsional', 'pendidikan_tertinggi',
    'ikatan_kerja', 'status', 'url_pencarian',
]


def main(dry_run: bool, report_only: bool, batch_size: int):
    ept_path = BASE_DIR / 'utils' / 'ept' / 'ept_itdd.json'
    print(f'Membaca {ept_path} ...')
    with open(ept_path, encoding='utf-8') as f:
        raw = json.load(f)

    print('Membangun index PT dan ProgramStudi dari DB ...')
    pt_idx, ps_idx = build_indexes()
    print(f'  PT index   : {len(pt_idx)} entri')
    print(f'  Prodi index: {len(ps_idx)} entri')

    # Index ept: nidn → fields (ambil record pertama per NIDN)
    ept_by_nidn: dict[str, dict] = {}
    for rec in raw:
        ef = rec['fields']
        nidn = _str(ef.get('nidn'))
        if nidn and nidn not in ept_by_nidn:
            ept_by_nidn[nidn] = ef

    print(f'Record ept dengan NIDN unik: {len(ept_by_nidn)}')

    # Resolve FK untuk setiap NIDN di ept
    resolved: dict[str, tuple] = {}   # nidn → (pt_id, prodi_id|None, ef)
    skip_no_pt = []

    for nidn, ef in ept_by_nidn.items():
        kodept = _str(ef.get('kodept'))
        kodeps = _str(ef.get('kodeps'))
        pt_id  = pt_idx.get(kodept)
        if pt_id is None:
            skip_no_pt.append((nidn, kodept, ef.get('namapt')))
            continue
        prodi_id = ps_idx.get((pt_id, kodeps))
        resolved[nidn] = (pt_id, prodi_id, ef)

    print(f'\nResolusi FK:')
    print(f'  Resolve PT+prodi : {sum(1 for _, (_, ps, _) in resolved.items() if ps)}')
    print(f'  Resolve PT saja  : {sum(1 for _, (_, ps, _) in resolved.items() if not ps)}')
    print(f'  Gagal resolve PT : {len(skip_no_pt)}')
    for nidn, kode, nama in skip_no_pt[:5]:
        print(f'    nidn={nidn} kodept={kode} namapt={nama}')

    # Pisahkan: NIDN yang sudah ada di DB vs yang baru
    existing_nidn = set(
        ProfilDosen.objects.filter(nidn__in=set(resolved.keys()))
        .values_list('nidn', flat=True)
    )
    new_nidn = set(resolved.keys()) - existing_nidn

    print(f'\nProfilDosen existing (akan diupdate): {len(existing_nidn)}')
    print(f'ProfilDosen baru    (akan diinsert) : {len(new_nidn)}')

    if report_only:
        print('\n[REPORT ONLY] Selesai.')
        return

    if dry_run:
        print('\n[DRY RUN] Tidak ada perubahan yang disimpan.')

    # ── 1. UPDATE existing ──────────────────────────────────────────────────
    upd_count  = 0
    skip_count = 0
    err_count  = 0
    batch      = []

    for obj in ProfilDosen.objects.filter(nidn__in=existing_nidn).iterator(chunk_size=batch_size):
        res = resolved.get(obj.nidn)
        if not res:
            skip_count += 1
            continue
        pt_id, prodi_id, ef = res
        try:
            new_vals = {
                'perguruan_tinggi_id': pt_id,
                'program_studi_id':    prodi_id,
                'program_studi_nama':  _str(ef.get('namaps')),
                'jenis_kelamin':       _jk(ef.get('jk')),
                'jabatan_fungsional':  _jab(ef.get('fungsional')),
                'pendidikan_tertinggi': _pend(ef.get('pendidikan')),
                'ikatan_kerja':        _ik(ef.get('ikatankerja')),
                'status':              _sts(ef.get('statuskeaktifan')),
                'url_pencarian':       _str(ef.get('linkdosen')),
            }
            changed = any(getattr(obj, k) != v for k, v in new_vals.items() if v is not None)
            if not changed:
                skip_count += 1
                continue
            for k, v in new_vals.items():
                if v is not None:
                    setattr(obj, k, v)
            batch.append(obj)
            upd_count += 1
            if not dry_run and len(batch) >= batch_size:
                ProfilDosen.objects.bulk_update(batch, UPDATE_FIELDS)
                print(f'  [UPDATE] bulk_update {len(batch)} rows ... (total: {upd_count})')
                batch.clear()
        except Exception as e:
            err_count += 1
            print(f'  ERROR update nidn={obj.nidn}: {e}')

    if not dry_run and batch:
        ProfilDosen.objects.bulk_update(batch, UPDATE_FIELDS)
        print(f'  [UPDATE] bulk_update {len(batch)} rows (flush)')

    # ── 2. INSERT baru ──────────────────────────────────────────────────────
    ins_count  = 0
    ins_errors = 0
    ins_batch  = []

    for nidn in new_nidn:
        res = resolved.get(nidn)
        if not res:
            continue
        pt_id, prodi_id, ef = res
        try:
            ins_batch.append(ProfilDosen(
                nidn                 = nidn,
                nuptk                = '',
                nama                 = _str(ef.get('nama')),
                jenis_kelamin        = _jk(ef.get('jk')),
                perguruan_tinggi_id  = pt_id,
                program_studi_id     = prodi_id,
                program_studi_nama   = _str(ef.get('namaps')),
                jabatan_fungsional   = _jab(ef.get('fungsional')),
                pendidikan_tertinggi = _pend(ef.get('pendidikan')),
                ikatan_kerja         = _ik(ef.get('ikatankerja')),
                status               = _sts(ef.get('statuskeaktifan')),
                url_pencarian        = _str(ef.get('linkdosen')),
            ))
            ins_count += 1
            if not dry_run and len(ins_batch) >= batch_size:
                ProfilDosen.objects.bulk_create(ins_batch, ignore_conflicts=True)
                print(f'  [INSERT] bulk_create {len(ins_batch)} rows ... (total: {ins_count})')
                ins_batch.clear()
        except Exception as e:
            ins_errors += 1
            print(f'  ERROR insert nidn={nidn}: {e}')

    if not dry_run and ins_batch:
        ProfilDosen.objects.bulk_create(ins_batch, ignore_conflicts=True)
        print(f'  [INSERT] bulk_create {len(ins_batch)} rows (flush)')

    print()
    print('=' * 55)
    print('Selesai.')
    print(f'  Updated  : {upd_count}  (skip tidak berubah: {skip_count})')
    print(f'  Inserted : {ins_count}')
    print(f'  Errors   : {err_count + ins_errors}')
    print(f'  Total ProfilDosen setelah ini: '
          f'{ProfilDosen.objects.count() if not dry_run else "—"}')
    if dry_run:
        print('  [DRY RUN] Tidak ada yang benar-benar disimpan.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run',     action='store_true')
    parser.add_argument('--report-only', action='store_true')
    parser.add_argument('--batch-size',  type=int, default=500)
    args = parser.parse_args()
    main(dry_run=args.dry_run, report_only=args.report_only, batch_size=args.batch_size)
