"""
Scraper PDDikti — Detail Dosen v2 (Batch dari data homebase)

Perbedaan dari v1:
  v1 : scrape satu dosen per run, nama+PT diberikan via argumen CLI
  v2 : batch-scrape semua dosen dari file *_detailprodi.json di outs/
       NIDN, nama, PT, NUPTK, pendidikan, status sudah tersedia di JSON homebase
       sehingga tidak perlu input manual per dosen

Alur:
  1. Baca semua outs/{kode_pt}/*_detailprodi.json
  2. Kumpulkan dosen unik (dedup by NIDN) beserta nama_pt, nuptk, dll.
  3. Filter berdasarkan --kode_pt jika diberikan
  4. Skip dosen yang file output-nya sudah ada (--resume default)
  5. Untuk tiap dosen: buka halaman pencarian PDDikti, klik tab Dosen,
     klik Lihat Detail, scrape semua section yang diminta
  6. Simpan ke outs/{kode_pt}/dosen/{nuptk}_{nidn}_detaildosen.json
     Jika NIDN kosong, gunakan NUPTK sebagai identifier pencarian.
     Identifier file: {nuptk}_{nidn} — salah satu boleh "x" jika tidak ada.

Section yang di-scrape:
  Default (tanpa --full) : profil detail + riwayat pendidikan
  --full                 : profil detail + riwayat pendidikan
                           + riwayat mengajar + penelitian
                           + pengabdian + publikasi + HKI

Usage:
    # Semua dosen, resume (default) — profil + riwayat pendidikan
    python scrape_pddikti_detaildosen_v2.py --resume

    # Hanya dosen dari PT tertentu
    python scrape_pddikti_detaildosen_v2.py --kode_pt 081010 --resume

    # Beberapa PT sekaligus
    python scrape_pddikti_detaildosen_v2.py --kode_pt 081010 071024 --resume

    # Scrape ulang semua (abaikan file yang sudah ada)
    python scrape_pddikti_detaildosen_v2.py --force

    # Scrape semua section (+ mengajar, penelitian, pengabdian, publikasi, HKI)
    python scrape_pddikti_detaildosen_v2.py --resume --full

    # Batasi jumlah dosen yang diproses
    python scrape_pddikti_detaildosen_v2.py --resume --limit 100

    # Tampilkan browser (tidak headless, untuk debug)
    python scrape_pddikti_detaildosen_v2.py --kode_pt 081010 --limit 1 --debug
"""

import os
import re
import sys
import json
import glob
import time
import argparse
import traceback
from pathlib import Path

# Tambahkan direktori ini ke path agar bisa import dari v1
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrape_pddikti_detaildosen_v1 import (
    init_driver,
    find_dosen_detail_url,
    scrape_detail_dosen,
)

OUTS_DIR   = Path(__file__).resolve().parent.parent / "outs"


# ---------------------------------------------------------------------------
# Kumpulkan dosen unik dari semua file detailprodi
# ---------------------------------------------------------------------------

def dosen_out_path(dosen):
    """
    Path output: outs/{kode_pt}/dosen/{nuptk}_{nidn}_detaildosen.json
    Jika NIDN kosong → identifier = nuptk_x
    Jika NUPTK kosong → identifier = x_{nidn}
    """
    nidn  = dosen["nidn"]  or "x"
    nuptk = dosen["nuptk"] or "x"
    fname = f"{nuptk}_{nidn}_detaildosen.json"
    return OUTS_DIR / dosen["kode_pt"] / "dosen" / fname


def collect_dosen(kode_pt_filter=None):
    """
    Baca semua *_detailprodi.json, kumpulkan dosen unik.
    Dedup key: NIDN jika ada, fallback ke NUPTK.
    Return list of dict: {nidn, nuptk, nama, nama_pt, kode_pt, pendidikan, status}
    """
    seen = set()
    dosen_list = []

    pattern = str(OUTS_DIR / "**" / "*_detailprodi.json")
    files = sorted(glob.glob(pattern, recursive=True))

    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue

        kode_pt = d.get("kode_pt", "")
        if kode_pt_filter and kode_pt not in kode_pt_filter:
            continue

        nama_pt = d.get("nama_pt", "")

        for sem, rows in d.get("dosen_homebase", {}).items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                nidn  = str(row.get("NIDN",  "")).strip()
                nuptk = str(row.get("NUPTK", "")).strip()

                # Abaikan jika keduanya kosong
                if (not nidn or nidn == "0") and (not nuptk or nuptk == "0"):
                    continue

                # Dedup: utamakan NIDN, fallback NUPTK
                dedup_key = nidn if (nidn and nidn != "0") else f"nuptk:{nuptk}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                dosen_list.append({
                    "nidn":       nidn  if nidn  != "0" else "",
                    "nuptk":      nuptk if nuptk != "0" else "",
                    "nama":       row.get("Nama", "").strip(),
                    "nama_pt":    nama_pt,
                    "kode_pt":    kode_pt,
                    "pendidikan": row.get("Pendidikan", "").strip(),
                    "status":     row.get("Status", "").strip(),
                })

    return dosen_list


# ---------------------------------------------------------------------------
# Scrape satu dosen
# ---------------------------------------------------------------------------

def scrape_one(driver, dosen, full=False):
    """
    Scrape detail satu dosen. Return data_dict atau raise exception.
    Jika NIDN kosong, gunakan NUPTK sebagai nidn_target untuk disambiguasi.
    """
    detail_url, url_pencarian = find_dosen_detail_url(
        driver,
        nama_dosen  = dosen["nama"],
        nama_pt     = dosen["nama_pt"],
        nidn_target = dosen["nidn"] or dosen["nuptk"] or None,
    )

    if not detail_url:
        raise ValueError("URL detail dosen tidak ditemukan")

    data = scrape_detail_dosen(
        driver,
        detail_url,
        url_pencarian    = url_pencarian or "",
        nuptk_input      = dosen["nuptk"],
        pendidikan_input = dosen["pendidikan"],
        status_input     = dosen["status"],
        full             = full,
    )
    data["source"] = {
        "nidn":       dosen["nidn"],
        "nama":       dosen["nama"],
        "nama_pt":    dosen["nama_pt"],
        "kode_pt":    dosen["kode_pt"],
        "nuptk":      dosen["nuptk"],
        "pendidikan": dosen["pendidikan"],
        "status":     dosen["status"],
    }
    return data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Batch scrape detail dosen PDDikti dari data homebase"
    )
    parser.add_argument("--kode_pt",  nargs="+", default=None,
                        help="Filter kode PT (boleh lebih dari satu, pisah spasi)")
    parser.add_argument("--resume",  action="store_true",
                        help="Skip dosen yang file output-nya sudah ada")
    parser.add_argument("--force",   action="store_true",
                        help="Scrape ulang meski file sudah ada")
    parser.add_argument("--full",    action="store_true",
                        help="Tambah section: mengajar, penelitian, pengabdian, publikasi, HKI "
                             "(default sudah include profil + riwayat_pendidikan)")
    parser.add_argument("--limit",   type=int, default=None,
                        help="Batasi jumlah dosen yang diproses")
    parser.add_argument("--debug",   action="store_true",
                        help="Tampilkan browser (tidak headless)")
    args = parser.parse_args()

    # ── Kumpulkan dosen ──────────────────────────────────────────────
    kode_pt_set = set(args.kode_pt) if args.kode_pt else None
    all_dosen   = collect_dosen(kode_pt_filter=kode_pt_set)

    print(f"Dosen unik dari JSON homebase : {len(all_dosen)}")
    if kode_pt_set:
        print(f"Filter kode_pt               : {sorted(kode_pt_set)}")

    # ── Filter resume/force ──────────────────────────────────────────
    if not args.force:
        todo = []
        for d in all_dosen:
            out = dosen_out_path(d)
            if args.resume and out.exists():
                continue
            todo.append(d)
    else:
        todo = all_dosen

    print(f"Akan diproses                 : {len(todo)} dosen"
          f"  (skip {len(all_dosen) - len(todo)} sudah ada)")

    if args.limit:
        todo = todo[:args.limit]
        print(f"Mode --limit                  : proses {args.limit} dosen pertama")

    if not todo:
        print("Tidak ada dosen yang perlu diproses.")
        return

    # ── Loop scraping ────────────────────────────────────────────────
    done = skip = error = 0
    driver = init_driver(headless=not args.debug)

    try:
        for i, dosen in enumerate(todo, 1):
            nidn    = dosen["nidn"]
            nuptk   = dosen["nuptk"]
            nama    = dosen["nama"]
            nama_pt = dosen["nama_pt"]
            out     = dosen_out_path(dosen)
            out.parent.mkdir(parents=True, exist_ok=True)

            id_str = nidn or f"nuptk:{nuptk}"
            print(f"\n[{i}/{len(todo)}] {id_str} — {nama}  ({nama_pt})")

            # Restart driver setiap 50 dosen agar tidak memory leak
            if i > 1 and (i - 1) % 50 == 0:
                print("  [INFO] Restart driver untuk menjaga stabilitas...")
                try:
                    driver.quit()
                except Exception:
                    pass
                time.sleep(2)
                driver = init_driver(headless=not args.debug)

            try:
                data = scrape_one(driver, dosen, full=args.full)

                with open(out, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                size_kb = out.stat().st_size / 1024
                n_riwpend = len(data.get("riwayat_pendidikan", []))
                n_mengajar = sum(len(v) for v in data.get("riwayat_mengajar", {}).values())
                print(f"  ✓ Tersimpan ({size_kb:.1f} KB) — "
                      f"pendidikan={n_riwpend}, mengajar={n_mengajar} matkul")
                done += 1

            except Exception as e:
                print(f"  [ERROR] {id_str}: {e}")
                traceback.print_exc()
                error += 1
                # Jika koneksi error, restart driver
                err_str = str(e).lower()
                if any(k in err_str for k in ["connection", "neterror", "timeout", "unreachable"]):
                    print("  [INFO] Koneksi error — restart driver...")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    time.sleep(5)
                    driver = init_driver(headless=not args.debug)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    print(f"\n{'='*60}")
    print(f"SELESAI")
    print(f"  Berhasil : {done}")
    print(f"  Error    : {error}")
    print(f"  Total    : {done + error}")
    print(f"  Output   : {OUTS_DIR}/<kode_pt>/dosen/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
