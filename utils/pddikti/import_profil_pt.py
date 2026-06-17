#!/usr/bin/env python3
"""
Import profil PT dari file JSON ke database.

Sumber : utils/outs/{kode_pt}/{kode_pt}_profile.json
Update : universities_perguruantinggi
Logo   : salin ke public/media/logos/{kode_pt}_logo.jpg

Fields yang diupdate:
  telepon           ← parse dari profil_pddikti.Kontak
  email             ← parse dari profil_pddikti.Kontak
  website           ← parse dari profil_pddikti.Kontak
  alamat            ← profil_pddikti.Alamat
  tahun_berdiri     ← parse tahun dari profil_pddikti.Tanggal Berdiri
                       (hanya diisi jika saat ini kosong/NULL)
  akreditasi_institusi ← profil_pddikti.Akreditasi
  logo              ← salin file logo, simpan path relatif

Fields yang TIDAK diubah:
  nama, kode_pt, singkatan, jenis, organisasi_induk,
  wilayah_id, kota, provinsi, is_active

Usage:
    # Import semua PT yang sudah ada _profile.json
    python import_profil_pt.py

    # Preview tanpa tulis ke DB
    python import_profil_pt.py --dry-run

    # Hanya satu PT
    python import_profil_pt.py --kode_pt 071024

    # Batasi jumlah
    python import_profil_pt.py --limit 10

    # Skip PT yang logonya sudah terisi di DB
    python import_profil_pt.py --skip-existing-logo
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

UTILS_DIR  = Path(__file__).resolve().parent
BACKEND_DIR = UTILS_DIR.parent.parent
ENV_PATH   = BACKEND_DIR / ".env"
load_dotenv(ENV_PATH)

OUT_DIR    = str(UTILS_DIR.parent / "outs")
MEDIA_ROOT = str(BACKEND_DIR / "public" / "media")
LOGOS_DIR  = os.path.join(MEDIA_ROOT, "logos")

DB_CONFIG = {
    "host":        os.environ.get("DB_HOST", "localhost"),
    "port":        int(os.environ.get("DB_PORT", 3306)),
    "user":        os.environ.get("DB_USER", "root"),
    "password":    os.environ.get("DB_PASSWORD", ""),
    "db":          os.environ.get("DB_NAME", "ptma_db"),
    "charset":     "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "connect_timeout": 30,
}

# Mapping teks akreditasi PDDikti → value di DB
AKREDITASI_MAP = {
    "unggul":        "unggul",
    "baik sekali":   "baik_sekali",
    "baik":          "baik",
    "belum":         "belum",
    "belum terakreditasi": "belum",
    "-":             "belum",
    "":              "belum",
}


# ---------------------------------------------------------------------------
# Parsing helper
# ---------------------------------------------------------------------------

def parse_kontak(kontak_raw):
    """
    kontak_raw bisa string atau list.
    Return dict: {"telepon": ..., "email": ..., "website": ...}
    """
    items = kontak_raw if isinstance(kontak_raw, list) else [kontak_raw]
    result = {"telepon": "", "email": "", "website": ""}

    for item in items:
        item = (item or "").strip()
        if not item or item == "-":
            continue

        if "@" in item:
            # Email
            if not result["email"]:
                result["email"] = item[:254]

        elif re.match(r'^[\d\s\-\+\(\)/]+$', item) and re.search(r'\d{5,}', item):
            # Telepon: hanya digit, spasi, tanda hubung, +, ()
            if not result["telepon"]:
                result["telepon"] = item[:20]

        elif "." in item and not item.startswith("0"):
            # Website: mengandung titik, bukan nomor telepon
            if not result["website"]:
                result["website"] = item[:200]

    return result


def parse_tahun_berdiri(tgl_str):
    """
    "1 September 1964" → 1964
    "2025" → 2025
    Return int atau None.
    """
    if not tgl_str or tgl_str == "-":
        return None
    # Cari 4 digit tahun (1900-2099)
    m = re.search(r'\b(19|20)\d{2}\b', str(tgl_str))
    if m:
        return int(m.group(0))
    return None


def parse_akreditasi(nilai_str):
    """
    "Unggul" → "unggul", "Baik Sekali" → "baik_sekali", dll.
    """
    if not nilai_str:
        return "belum"
    key = str(nilai_str).strip().lower()
    return AKREDITASI_MAP.get(key, "belum")


# ---------------------------------------------------------------------------
# Baca file JSON
# ---------------------------------------------------------------------------

def load_profile_json(kode_pt):
    """Return dict dari {kode_pt}_profile.json, atau None jika tidak ada."""
    path = os.path.join(OUT_DIR, kode_pt, f"{kode_pt}_profile.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Salin logo ke media/logos/
# ---------------------------------------------------------------------------

def copy_logo(kode_pt, logo_file):
    """
    Salin logo dari utils/outs/{kode_pt}/{logo_file}
                  ke   public/media/logos/{logo_file}
    Return path relatif untuk disimpan ke DB ("logos/{logo_file}"),
    atau '' jika file tidak ada.
    """
    if not logo_file:
        return ""
    src  = os.path.join(OUT_DIR, kode_pt, logo_file)
    if not os.path.exists(src):
        print(f"  [WARN] Logo tidak ditemukan: {src}")
        return ""
    os.makedirs(LOGOS_DIR, exist_ok=True)
    dst  = os.path.join(LOGOS_DIR, logo_file)
    shutil.copy2(src, dst)
    size_kb = os.path.getsize(dst) / 1024
    print(f"  Logo disalin → {dst} ({size_kb:.1f} KB)")
    return f"logos/{logo_file}"


# ---------------------------------------------------------------------------
# Build dict update
# ---------------------------------------------------------------------------

def build_update(data):
    """
    Dari dict JSON, bangun dict field→value untuk UPDATE.
    """
    profil = data.get("profil_pddikti", {})

    kontak = parse_kontak(profil.get("Kontak", ""))
    tahun  = parse_tahun_berdiri(profil.get("Tanggal Berdiri", ""))
    akred  = parse_akreditasi(profil.get("Akreditasi", ""))
    alamat = (profil.get("Alamat") or "").strip()

    return {
        "telepon":            kontak["telepon"],
        "email":              kontak["email"],
        "website":            kontak["website"],
        "alamat":             alamat,
        "akreditasi_institusi": akred,
        "tahun_berdiri_parsed": tahun,   # ditangani khusus (only-if-empty)
    }


# ---------------------------------------------------------------------------
# Update DB
# ---------------------------------------------------------------------------

def update_db(conn, kode_pt, fields, logo_path, dry_run=False):
    """
    UPDATE universities_perguruantinggi untuk satu PT.
    tahun_berdiri hanya diisi jika saat ini NULL/0.
    logo hanya diupdate jika logo_path tidak kosong.
    """
    with conn.cursor() as cur:
        # Ambil data saat ini
        cur.execute(
            "SELECT id, nama, tahun_berdiri, logo, akreditasi_institusi "
            "FROM universities_perguruantinggi WHERE kode_pt = %s",
            (kode_pt,)
        )
        row = cur.fetchone()

    if not row:
        print(f"  [ERROR] kode_pt '{kode_pt}' tidak ditemukan di DB")
        return False

    pt_id         = row["id"]
    nama          = row["nama"]
    tahun_db      = row["tahun_berdiri"]
    logo_db       = row["logo"] or ""
    akred_db      = row["akreditasi_institusi"]
    tahun_parsed  = fields.pop("tahun_berdiri_parsed")

    # Tentukan nilai final
    set_clauses  = []
    params       = []
    changes      = []

    for col in ["telepon", "email", "website", "alamat", "akreditasi_institusi"]:
        val = fields.get(col, "")
        if val:
            set_clauses.append(f"{col} = %s")
            params.append(val)
            changes.append(f"{col}={val!r}")

    # tahun_berdiri: hanya update jika belum terisi
    if tahun_parsed and not tahun_db:
        set_clauses.append("tahun_berdiri = %s")
        params.append(tahun_parsed)
        changes.append(f"tahun_berdiri={tahun_parsed}")

    # logo: update jika ada file baru
    if logo_path:
        set_clauses.append("logo = %s")
        params.append(logo_path)
        changes.append(f"logo={logo_path!r}")

    if not set_clauses:
        print(f"  [SKIP] {kode_pt} — tidak ada field yang perlu diupdate")
        return False

    print(f"  Update: {', '.join(changes)}")

    if dry_run:
        print(f"  [DRY-RUN] SQL tidak dieksekusi")
        return True

    params.append(pt_id)
    sql = f"UPDATE universities_perguruantinggi SET {', '.join(set_clauses)} WHERE id = %s"
    with conn.cursor() as cur:
        cur.execute(sql, params)
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Proses satu PT
# ---------------------------------------------------------------------------

def process_pt(conn, kode_pt, dry_run=False, skip_existing_logo=False):
    # Cek skip_existing_logo
    if skip_existing_logo:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT logo FROM universities_perguruantinggi WHERE kode_pt = %s",
                (kode_pt,)
            )
            row = cur.fetchone()
        if row and row.get("logo"):
            print(f"  [SKIP] Logo sudah ada: {row['logo']}")
            return "skip"

    # Baca JSON
    data = load_profile_json(kode_pt)
    if not data:
        print(f"  [SKIP] File profile.json tidak ditemukan")
        return "skip"

    # Salin logo
    logo_path = ""
    logo_file = data.get("logo_file", "")
    if logo_file and not dry_run:
        logo_path = copy_logo(kode_pt, logo_file)
    elif logo_file:
        logo_path = f"logos/{logo_file}"
        print(f"  [DRY-RUN] Logo akan disalin → {logo_path}")

    # Build update fields
    fields = build_update(data)

    # Update DB
    ok = update_db(conn, kode_pt, fields, logo_path, dry_run=dry_run)
    return "ok" if ok else "skip"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Import profil PT dari JSON ke database"
    )
    parser.add_argument("--kode_pt", default=None,
                        help="Hanya import satu PT")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview perubahan tanpa menulis ke DB")
    parser.add_argument("--limit", type=int, default=None,
                        help="Batasi jumlah PT yang diproses")
    parser.add_argument("--skip-existing-logo", action="store_true",
                        help="Skip PT yang sudah punya logo di DB")
    args = parser.parse_args()

    conn = pymysql.connect(**DB_CONFIG)

    # Tentukan daftar kode_pt yang akan diproses
    if args.kode_pt:
        kode_list = [args.kode_pt]
    else:
        # Semua subfolder di OUT_DIR yang punya _profile.json
        kode_list = sorted([
            d for d in os.listdir(OUT_DIR)
            if os.path.isdir(os.path.join(OUT_DIR, d))
            and os.path.exists(os.path.join(OUT_DIR, d, f"{d}_profile.json"))
        ])

    total = len(kode_list)
    if args.limit:
        kode_list = kode_list[:args.limit]

    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Total file JSON ditemukan : {total}")
    print(f"Akan diproses             : {len(kode_list)} PT")
    print(f"MEDIA_ROOT                : {MEDIA_ROOT}")
    print()

    ok = skip = error = 0

    for i, kode_pt in enumerate(kode_list, 1):
        print(f"[{i}/{len(kode_list)}] {kode_pt}")
        try:
            status = process_pt(
                conn, kode_pt,
                dry_run=args.dry_run,
                skip_existing_logo=args.skip_existing_logo,
            )
            if status == "ok":
                ok += 1
            else:
                skip += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            error += 1
            conn.rollback()

    conn.close()

    print(f"\n{'='*60}")
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}SELESAI")
    print(f"  Berhasil diupdate : {ok}")
    print(f"  Dilewati          : {skip}")
    print(f"  Error             : {error}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
