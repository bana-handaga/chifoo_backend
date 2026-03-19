"""
Import profil dosen dari file JSON hasil scrape ke tabel universities_profildosen.

Fitur:
- Resumable: upsert berdasarkan (perguruan_tinggi, nidn) atau (perguruan_tinggi, nuptk)
- Match program_studi FK berdasarkan nama prodi + PT
- Laporan ringkasan: created, updated, skip, error

Usage:
    # Import semua
    python utils/import_profildosen.py

    # Import satu PT saja
    python utils/import_profildosen.py --pt-kode 061008

    # Dry run
    python utils/import_profildosen.py --dry-run
"""

import os
import sys
import json
import glob
import argparse
import django
from datetime import datetime, timezone
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")
django.setup()

from apps.universities.models import PerguruanTinggi, ProgramStudi, ProfilDosen

OUTS_DIR = BASE_DIR / "utils" / "outs" / "dosen"

# ---------------------------------------------------------------------------
# Mapping jabatan fungsional ke nilai bersih
# ---------------------------------------------------------------------------
JABATAN_MAP = {
    '-': '',
    'asisten ahli': 'Asisten Ahli',
    'lektor': 'Lektor',
    'lektor kepala': 'Lektor Kepala',
    'profesor': 'Profesor',
    'guru besar': 'Profesor',
}

PENDIDIKAN_MAP = {
    's1': 's1', 'd4': 's1', 'd3': 'lainnya', 'd2': 'lainnya', 'd1': 'lainnya',
    's2': 's2', 's3': 's3', 'profesi': 'profesi',
    'sp-1': 'profesi', 'sp-2': 's3',
}

IKATAN_MAP = {
    'dosen tetap': 'tetap',
    'tetap': 'tetap',
    'dosen tidak tetap': 'tidak_tetap',
    'tidak tetap': 'tidak_tetap',
}

JENIS_KELAMIN_MAP = {
    'laki-laki': 'L',
    'laki laki': 'L',
    'perempuan': 'P',
    'wanita': 'P',
}


def normalize_jabatan(val):
    return JABATAN_MAP.get(val.strip().lower(), val.strip())


def normalize_pendidikan(val):
    return PENDIDIKAN_MAP.get(val.strip().lower(), 'lainnya')


def normalize_ikatan(val):
    return IKATAN_MAP.get(val.strip().lower(), 'tetap')


def normalize_jk(val):
    return JENIS_KELAMIN_MAP.get(val.strip().lower(), '')


# ---------------------------------------------------------------------------
# Cache PT dan Prodi agar tidak query berulang
# ---------------------------------------------------------------------------
def build_cache():
    pt_cache = {pt.kode_pt: pt for pt in PerguruanTinggi.objects.all()}

    # prodi_cache: key = (kode_pt, nama_lower) -> ProgramStudi
    prodi_cache = {}
    for ps in ProgramStudi.objects.select_related('perguruan_tinggi').all():
        key = (ps.perguruan_tinggi.kode_pt, ps.nama.lower().strip())
        prodi_cache[key] = ps

    return pt_cache, prodi_cache


def match_prodi(prodi_cache, kode_pt, nama_prodi_pddikti):
    """Cari FK ProgramStudi berdasarkan nama prodi dari PDDikti."""
    if not nama_prodi_pddikti:
        return None
    return prodi_cache.get((kode_pt, nama_prodi_pddikti.lower().strip()))


# ---------------------------------------------------------------------------
# Import satu file JSON
# ---------------------------------------------------------------------------
def import_file(fpath, pt_cache, prodi_cache, dry_run=False):
    try:
        with open(fpath, encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return 'error', str(e)

    profil = data.get('profil', {})
    inp    = data.get('input', {})

    # Ambil NIDN/NUPTK dari input (lebih reliable dari profil)
    nidn  = inp.get('nidn', '').strip() or None   # None jika kosong
    nuptk = inp.get('nuptk', '') or profil.get('NUPTK', '')
    if isinstance(nuptk, str):
        nuptk = nuptk.strip()
    kode_pt = inp.get('pt_kode', '').strip()

    if not kode_pt:
        return 'skip', 'pt_kode kosong'

    pt = pt_cache.get(kode_pt)
    if not pt:
        return 'skip', f'PT {kode_pt} tidak ditemukan di DB'

    nama = profil.get('Nama', inp.get('nama', '')).strip()
    if not nama:
        return 'skip', 'nama kosong'

    # Cari prodi FK
    nama_prodi_pddikti = profil.get('Program Studi', '').strip()
    ps = match_prodi(prodi_cache, kode_pt, nama_prodi_pddikti)

    # Normalize fields
    jk          = normalize_jk(profil.get('Jenis Kelamin', ''))
    jabatan     = normalize_jabatan(profil.get('Jabatan Fungsional', ''))
    pendidikan  = normalize_pendidikan(
        profil.get('Pendidikan Tertinggi', inp.get('pendidikan', ''))
    )
    ikatan      = normalize_ikatan(inp.get('ikatan_kerja', ''))
    status      = profil.get('Status', inp.get('status', '')).strip()
    url         = data.get('url_pencarian', '').strip()
    scraped_at  = datetime.now(tz=timezone.utc)

    defaults = {
        'nuptk':               nuptk,
        'nama':                nama,
        'jenis_kelamin':       jk,
        'program_studi':       ps,
        'program_studi_nama':  nama_prodi_pddikti,
        'jabatan_fungsional':  jabatan,
        'pendidikan_tertinggi': pendidikan,
        'ikatan_kerja':        ikatan,
        'status':              status,
        'url_pencarian':       url,
        'scraped_at':          scraped_at,
    }

    if dry_run:
        return 'dry', f'{nama} | {nidn or nuptk} | {kode_pt}'

    try:
        if nidn:
            obj, created = ProfilDosen.objects.update_or_create(
                perguruan_tinggi=pt,
                nidn=nidn,
                defaults=defaults,
            )
        elif nuptk:
            # Dosen tanpa NIDN — nidn=None, lookup by (pt, nuptk)
            try:
                obj = ProfilDosen.objects.get(perguruan_tinggi=pt, nuptk=nuptk, nidn=None)
                for k, v in defaults.items():
                    setattr(obj, k, v)
                obj.save()
                created = False
            except ProfilDosen.DoesNotExist:
                obj = ProfilDosen.objects.create(perguruan_tinggi=pt, nidn=None, **defaults)
                created = True
        else:
            return 'skip', 'tidak ada NIDN maupun NUPTK'
        return 'created' if created else 'updated', None
    except Exception as e:
        return 'error', str(e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Import profil dosen ke DB")
    parser.add_argument("--pt-kode",  default="", help="Filter PT tertentu, e.g. 061008")
    parser.add_argument("--dry-run",  action="store_true", help="Tampilkan tanpa menyimpan ke DB")
    args = parser.parse_args()

    print("Membangun cache PT dan Prodi...")
    pt_cache, prodi_cache = build_cache()
    print(f"  {len(pt_cache)} PT | {len(prodi_cache)} Prodi di cache")

    # Kumpulkan file
    if args.pt_kode:
        pattern = str(OUTS_DIR / args.pt_kode / "*.json")
    else:
        pattern = str(OUTS_DIR / "**" / "*.json")

    files = sorted(glob.glob(pattern, recursive=True))
    files = [f for f in files if not os.path.basename(f).startswith('_')]

    print(f"Ditemukan {len(files)} file JSON")
    if args.dry_run:
        print("Mode: DRY RUN (tidak ada yang disimpan)\n")

    counts = {'created': 0, 'updated': 0, 'skip': 0, 'error': 0, 'dry': 0}
    errors = []

    for i, fpath in enumerate(files, 1):
        status, msg = import_file(fpath, pt_cache, prodi_cache, dry_run=args.dry_run)
        counts[status] += 1

        if status == 'error':
            errors.append(f"{fpath}: {msg}")
            print(f"  [ERROR] {os.path.basename(fpath)}: {msg}")
        elif status == 'dry':
            print(f"  [DRY] {msg}")
        elif i % 500 == 0 or i == len(files):
            pct = i / len(files) * 100
            print(f"  [{i}/{len(files)} {pct:.1f}%] "
                  f"created:{counts['created']} updated:{counts['updated']} "
                  f"skip:{counts['skip']} error:{counts['error']}")

    print("\n" + "="*50)
    print(f"  Selesai")
    print(f"  Created : {counts['created']}")
    print(f"  Updated : {counts['updated']}")
    print(f"  Skip    : {counts['skip']}")
    print(f"  Error   : {counts['error']}")
    print("="*50)

    if errors:
        print("\nDetail error:")
        for e in errors[:20]:
            print(f"  {e}")


if __name__ == "__main__":
    main()
