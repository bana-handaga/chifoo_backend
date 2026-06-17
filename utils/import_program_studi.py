"""
Import / Update data ProgramStudi dari file *_detailprodi.json di folder outs/
ke tabel universities_programstudi di DB.

Logika:
  - update_or_create berdasarkan (perguruan_tinggi, kode_prodi)
  - Field yang diupdate: nama, jenjang, akreditasi, no_sk_akreditasi,
    tanggal_berdiri, telepon
  - Field yang TIDAK diubah jika sudah ada: email, website, informasi_umum,
    ilmu_dipelajari, kompetensi (tidak tersedia di JSON scrape)

Usage:
    cd /home/ubuntu/_chifoo/chifoo_backend
    conda run -n chifoo python utils/import_program_studi.py
    conda run -n chifoo python utils/import_program_studi.py --dry-run
    conda run -n chifoo python utils/import_program_studi.py --kode_pt 011003
"""

import os, sys, json, glob, argparse
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ptma.settings.base')

import django
django.setup()

from apps.universities.models import PerguruanTinggi, ProgramStudi

OUTS_DIR = BASE_DIR / 'utils' / 'outs'

# ── Mapping akreditasi ──────────────────────────────────────────────────────
AK_MAP = {
    'unggul':                 'unggul',
    'terakreditasi unggul':   'unggul',
    'a':                      'unggul',
    'baik sekali':            'baik_sekali',
    'baik':                   'baik',
    'b':                      'baik',
    'terakreditasi':          'baik',
    'c':                      'c',
}

def map_akreditasi(raw: str) -> str:
    key = raw.strip().lower()
    return AK_MAP.get(key, 'belum')


# ── Mapping jenjang ─────────────────────────────────────────────────────────
JENJANG_MAP = {
    's1':      's1',
    's2':      's2',
    's3':      's3',
    'd1':      'd1',
    'd2':      'd2',
    'd3':      'd3',
    'd4':      'd4',
    'profesi': 'profesi',
    'sp-1':    'profesi',
    'sp-2':    'profesi',
}

def extract_jenjang(nama_prodi: str) -> str:
    """Ekstrak jenjang dari prefix nama_prodi (mis. 'S2 Ilmu Biomedis' → 's2')."""
    if not nama_prodi:
        return 's1'
    prefix = nama_prodi.strip().split()[0].lower()
    return JENJANG_MAP.get(prefix, 's1')


# ── Ekstrak telepon dari Kontak ─────────────────────────────────────────────
def extract_telepon(kontak) -> str:
    """Ambil nomor telepon pertama saja (field DB max_length=20)."""
    if not kontak or kontak == '-':
        return ''
    if isinstance(kontak, list):
        items = [str(k).strip() for k in kontak if k and str(k).strip() not in ('', '-')]
        return items[0][:20] if items else ''
    val = str(kontak).strip()
    return val[:20]


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Simulasi tanpa menyimpan ke DB')
    parser.add_argument('--kode_pt', nargs='+', default=None, help='Filter kode PT tertentu')
    args = parser.parse_args()

    dry_run = args.dry_run
    kode_pt_filter = set(args.kode_pt) if args.kode_pt else None

    if dry_run:
        print('[DRY-RUN] Tidak ada perubahan yang disimpan.')

    # Cache PT: kode_pt → PerguruanTinggi object
    pt_cache = {pt.kode_pt: pt for pt in PerguruanTinggi.objects.all()}
    print(f'PT di DB         : {len(pt_cache)}')

    # Kumpulkan semua file
    files = sorted(glob.glob(str(OUTS_DIR / '**' / '*_detailprodi.json'), recursive=True))
    if kode_pt_filter:
        files = [f for f in files if Path(f).parent.name in kode_pt_filter]
    print(f'File detailprodi : {len(files)}')
    print()

    created = updated = skipped = error = 0
    pt_missing = set()

    for i, fpath in enumerate(files, 1):
        try:
            d = json.load(open(fpath, encoding='utf-8'))
        except Exception as e:
            print(f'  [ERROR] baca file {fpath}: {e}')
            error += 1
            continue

        kode_pt  = str(d.get('kode_pt', '')).strip()
        kode_ps  = str(d.get('kode_ps', '')).strip()
        nama_ps  = str(d.get('nama_ps', '')).strip()
        profil   = d.get('profil', {})

        if not kode_pt or not kode_ps:
            skipped += 1
            continue

        if kode_pt not in pt_cache:
            pt_missing.add(kode_pt)
            skipped += 1
            continue

        pt = pt_cache[kode_pt]

        # Field mapping
        nama_prodi_full = profil.get('nama_prodi', '')
        jenjang         = extract_jenjang(nama_prodi_full)
        akreditasi_raw  = profil.get('Akreditasi', '')
        akreditasi      = map_akreditasi(akreditasi_raw)
        no_sk           = str(profil.get('SK Selenggara', '') or '').strip()
        tanggal_berdiri = str(profil.get('Tanggal Berdiri', '') or '').strip()
        telepon         = extract_telepon(profil.get('Kontak'))

        defaults = {
            'nama':           nama_ps or nama_prodi_full,
            'jenjang':        jenjang,
            'akreditasi':     akreditasi,
            'no_sk_akreditasi': no_sk,
            'tanggal_berdiri':  tanggal_berdiri,
            'is_active':      True,
        }
        if telepon:
            defaults['telepon'] = telepon

        if dry_run:
            # Cek apakah record sudah ada
            exists = ProgramStudi.objects.filter(
                perguruan_tinggi=pt, kode_prodi=kode_ps
            ).exists()
            if exists:
                updated += 1
            else:
                created += 1
            continue

        try:
            obj, was_created = ProgramStudi.objects.update_or_create(
                perguruan_tinggi=pt,
                kode_prodi=kode_ps,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as e:
            print(f'  [ERROR] simpan {kode_pt}/{kode_ps}: {e}')
            error += 1

        if i % 500 == 0:
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
