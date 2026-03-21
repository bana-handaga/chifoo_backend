"""
Batch Scraper PDDikti — Detail Dosen (semua PT)

Alur:
  1. Baca semua file outs/[kode_pt]/*_detailprodi.json
  2. Kumpulkan dosen unik per NIDN (ambil PT dari semester terbaru)
  3. Skip dosen yang sudah ada di outs/dosen/[NIDN].json
  4. Scrape satu per satu menggunakan scrape_pddikti_detaildosen
  5. Catat gagal ke outs/dosen/_failed.json (bisa di-retry)

Usage:
    # Scrape semua dosen (resumable — skip yg sudah ada)
    python utils/scrape_pddikti_batch_dosen.py

    # Filter satu PT saja
    python utils/scrape_pddikti_batch_dosen.py --pt-kode 061008

    # Retry dosen yang sebelumnya gagal
    python utils/scrape_pddikti_batch_dosen.py --retry-failed

    # Dry run — tampilkan daftar tanpa scrape
    python utils/scrape_pddikti_batch_dosen.py --dry-run

    # Batasi jumlah (untuk testing)
    python utils/scrape_pddikti_batch_dosen.py --limit 5

    # Tampilkan ringkasan progress saja
    python utils/scrape_pddikti_batch_dosen.py --status
"""

import os
import re
import sys
import json
import time
import glob
import argparse
import traceback
from pathlib import Path
from datetime import datetime

# Tambahkan root project ke path agar bisa import scraper dosen
sys.path.insert(0, str(Path(__file__).parent))

from scrape_pddikti_detaildosen import (
    init_driver,
    find_dosen_detail_url,
    scrape_detail_dosen,
)

OUTS_ROOT  = Path("/home/ubuntu/_chifoo/chifoo_backend/utils/outs")
DOSEN_DIR  = OUTS_ROOT / "dosen"
FAILED_FILE = DOSEN_DIR / "_failed.json"
LOG_FILE    = DOSEN_DIR / "_batch.log"


# ---------------------------------------------------------------------------
# Collect dosen dari semua file detailprodi
# ---------------------------------------------------------------------------

def collect_dosen(pt_kode_filter=None):
    """
    Baca semua file detailprodi, kembalikan list dosen unik.
    Tiap entry: {nidn, nama, pt_nama, pt_kode, nuptk, pendidikan, status, ikatan_kerja}
    Jika NIDN sama muncul di banyak prodi → pakai data dari semester paling baru.
    """
    pattern = str(OUTS_ROOT / "*/  *_detailprodi.json")
    if pt_kode_filter:
        pattern = str(OUTS_ROOT / pt_kode_filter / f"{pt_kode_filter}_*_detailprodi.json")
    else:
        pattern = str(OUTS_ROOT / "*" / "*_detailprodi.json")

    files = glob.glob(pattern)
    print(f"[collect] Membaca {len(files)} file detailprodi...")

    # key -> dict terbaik (semester terbaru berdasarkan tahun akademik tertinggi)
    # key = NIDN jika ada, fallback ke NUPTK
    dosen_map  = {}  # key -> entry
    truly_skip = []  # dosen tanpa NIDN & tanpa NUPTK (tidak bisa diidentifikasi)

    for fpath in sorted(files):
        try:
            with open(fpath, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue

        pt_kode = d.get("kode_pt", "")
        pt_nama = d.get("nama_pt", "")

        # Iterasi semester, ambil tahun akademik terbesar
        for sem_label, dosen_list in d.get("dosen_homebase", {}).items():
            # Ekstrak tahun dari label, misal "Genap 2025" → 2025
            tahun_match = re.search(r"\d{4}", sem_label)
            tahun = int(tahun_match.group()) if tahun_match else 0

            for dosen in dosen_list:
                nidn  = dosen.get("NIDN",  "").strip()
                nuptk = dosen.get("NUPTK", "").strip()
                nama  = dosen.get("Nama",  "").strip()

                if not nama:
                    continue

                # Tentukan identifier unik: NIDN prioritas, NUPTK sebagai fallback
                if nidn:
                    uid      = nidn
                    uid_type = "nidn"
                elif nuptk:
                    uid      = nuptk
                    uid_type = "nuptk"
                else:
                    truly_skip.append({"nama": nama, "pt_kode": pt_kode})
                    continue

                entry = {
                    "uid":         uid,        # NIDN atau NUPTK
                    "uid_type":    uid_type,   # "nidn" | "nuptk"
                    "nidn":        nidn,
                    "nuptk":       nuptk,
                    "nama":        nama,
                    "pt_kode":     pt_kode,
                    "pt_nama":     pt_nama,
                    "pendidikan":  dosen.get("Pendidikan",   "").strip(),
                    "status":      dosen.get("Status",       "").strip(),
                    "ikatan_kerja":dosen.get("Ikatan Kerja", "").strip(),
                    "_tahun":      tahun,
                }

                # Update jika identifier sudah ada tapi semester ini lebih baru
                if uid not in dosen_map or tahun > dosen_map[uid]["_tahun"]:
                    dosen_map[uid] = entry

    all_entries   = list(dosen_map.values())
    nidn_count    = sum(1 for e in all_entries if e["uid_type"] == "nidn")
    nuptk_count   = sum(1 for e in all_entries if e["uid_type"] == "nuptk")
    dosen_list_unique = all_entries

    print(f"[collect] Dosen unik — NIDN    : {nidn_count}")
    print(f"[collect] Dosen unik — NUPTK   : {nuptk_count}  (tidak punya NIDN)")
    print(f"[collect] Skip (no NIDN+NUPTK) : {len(truly_skip)}")
    return dosen_list_unique


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def out_path(uid, pt_kode="", nama=""):
    """outs/dosen/[kode_pt]/[uid]_[nama].json  (uid = NIDN atau NUPTK)"""
    safe_nama = re.sub(r"[^\w]", "_", nama.upper()) if nama else "UNKNOWN"
    subdir = DOSEN_DIR / (pt_kode if pt_kode else "_no_pt")
    subdir.mkdir(parents=True, exist_ok=True)
    return subdir / f"{uid}_{safe_nama}.json"


def already_done(uid, pt_kode="", nama=""):
    return out_path(uid, pt_kode, nama).exists()


def load_failed():
    if FAILED_FILE.exists():
        with open(FAILED_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_failed(failed_list):
    with open(FAILED_FILE, "w", encoding="utf-8") as f:
        json.dump(failed_list, f, ensure_ascii=False, indent=2)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# Status report
# ---------------------------------------------------------------------------

def print_status():
    all_files = list(DOSEN_DIR.glob("*.json"))
    done_files = [f for f in all_files if not f.name.startswith("_")]
    failed = load_failed()
    print(f"\n{'='*50}")
    print(f"  Dosen terscrape : {len(done_files)}")
    print(f"  Gagal (failed)  : {len(failed)}")
    print(f"  Output dir      : {DOSEN_DIR}")
    if failed:
        print(f"\n  Contoh gagal:")
        for e in failed[:5]:
            print(f"    {e.get('nidn','-')} | {e.get('nama','-')} | {e.get('error','')[:60]}")
    print(f"{'='*50}\n")


# ---------------------------------------------------------------------------
# Main batch loop
# ---------------------------------------------------------------------------

def run_batch(dosen_list, args):
    DOSEN_DIR.mkdir(parents=True, exist_ok=True)

    # Hitung yang perlu discrape
    todo = [d for d in dosen_list if not already_done(d["uid"], d.get("pt_kode",""), d.get("nama",""))]
    skipped = len(dosen_list) - len(todo)

    if args.limit:
        todo = todo[:args.limit]

    log(f"Total dosen   : {len(dosen_list)}")
    log(f"Sudah ada     : {skipped}")
    log(f"Akan discrape : {len(todo)}")

    if not todo:
        log("Semua dosen sudah terscrape. Gunakan --retry-failed untuk retry yang gagal.")
        return

    failed_existing = load_failed()
    failed_nidn_set = {e.get("uid", e.get("nidn","")) for e in failed_existing}

    max_consecutive_fail = getattr(args, 'max_fail', 10)
    consecutive_fail = 0
    aborted = False

    driver = init_driver(headless=True)
    newly_failed = []
    success_count = 0

    try:
        for i, dosen in enumerate(todo, 1):
            uid     = dosen["uid"]
            nidn    = dosen["nidn"]
            nama    = dosen["nama"]
            pt_nama = dosen["pt_nama"]
            uid_lbl = f"NIDN:{nidn}" if nidn else f"NUPTK:{uid}"

            log(f"[{i}/{len(todo)}] {nama} | {uid_lbl} | {pt_nama}")

            # Skip check (file mungkin dibuat oleh proses lain saat batch berjalan)
            if already_done(uid, dosen.get("pt_kode",""), nama):
                log(f"  → skip (sudah ada)")
                skipped += 1
                continue

            try:
                detail_url, url_pencarian = find_dosen_detail_url(
                    driver, nama, pt_nama, nidn_target=nidn or None
                )

                if not detail_url:
                    raise ValueError("URL detail tidak ditemukan")

                data = scrape_detail_dosen(
                    driver, detail_url,
                    url_pencarian    = url_pencarian,
                    nuptk_input      = dosen.get("nuptk", ""),
                    pendidikan_input = dosen.get("pendidikan", ""),
                    status_input     = dosen.get("status", ""),
                    full             = getattr(args, 'full', False),
                )
                data["input"] = {
                    "nama":        nama,
                    "pt":          pt_nama,
                    "pt_kode":     dosen.get("pt_kode", ""),
                    "nidn":        nidn,
                    "nuptk":       dosen.get("nuptk", ""),
                    "pendidikan":  dosen.get("pendidikan", ""),
                    "status":      dosen.get("status", ""),
                    "ikatan_kerja":dosen.get("ikatan_kerja", ""),
                }

                fout = out_path(uid, dosen.get("pt_kode",""), nama)
                with open(fout, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                size_kb = fout.stat().st_size / 1024
                log(f"  → OK ({size_kb:.1f} KB) | pend:{len(data['riwayat_pendidikan'])} "
                    f"mengajar:{len(data['riwayat_mengajar'])} "
                    f"penelitian:{len(data['penelitian'])} "
                    f"pengabdian:{len(data['pengabdian'])} "
                    f"publikasi:{len(data['publikasi'])} "
                    f"hki:{len(data['hki_paten'])}")
                success_count += 1
                consecutive_fail = 0  # reset counter setelah sukses

                # Hapus dari failed list jika sebelumnya gagal
                if uid in failed_nidn_set:
                    failed_existing = [e for e in failed_existing if e.get("uid") != uid]
                    failed_nidn_set.discard(uid)

                # Jeda antar request agar tidak terlalu agresif
                time.sleep(2)

            except Exception as e:
                err_msg = str(e)
                consecutive_fail += 1
                log(f"  → GAGAL [{consecutive_fail}/{max_consecutive_fail} berturut]: {err_msg[:120]}")
                newly_failed.append({
                    "uid":       uid,
                    "uid_type":  dosen.get("uid_type", ""),
                    "nidn":      nidn,
                    "nuptk":     dosen.get("nuptk", ""),
                    "nama":      nama,
                    "pt_nama":   pt_nama,
                    "pt_kode":   dosen.get("pt_kode", ""),
                    "pendidikan":dosen.get("pendidikan", ""),
                    "status":    dosen.get("status", ""),
                    "error":     err_msg[:200],
                    "ts":        datetime.now().isoformat(),
                })

                # Batalkan seluruh proses jika gagal berturut-turut melebihi batas
                if consecutive_fail >= max_consecutive_fail:
                    log(f"\n[ABORT] {consecutive_fail} kegagalan berturut-turut — proses dihentikan.")
                    aborted = True
                    break

                # Restart driver jika browser crash
                if "session" in err_msg.lower() or "webdriver" in err_msg.lower():
                    log("  → Restart browser...")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    time.sleep(3)
                    driver = init_driver(headless=True)
                else:
                    time.sleep(2)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

        # Simpan failed list gabungan
        all_failed = failed_existing + newly_failed
        if all_failed:
            save_failed(all_failed)
            log(f"Failed list disimpan: {len(all_failed)} entri → {FAILED_FILE}")

        status_label = "DIBATALKAN" if aborted else "Selesai"
        log(f"\n{status_label}. Berhasil: {success_count} | Gagal baru: {len(newly_failed)} | Skip: {skipped}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Batch scraper detail dosen PDDikti")
    parser.add_argument("--pt-kode",      default="",    help="Filter PT tertentu, e.g. 061008")
    parser.add_argument("--retry-failed", action="store_true", help="Retry dosen yang sebelumnya gagal")
    parser.add_argument("--dry-run",      action="store_true", help="Tampilkan daftar tanpa scrape")
    parser.add_argument("--limit",        type=int, default=0, help="Batasi jumlah scrape (untuk testing)")
    parser.add_argument("--full",     action="store_true", help="Scrape semua data (mengajar, penelitian, pengabdian, publikasi, HKI). Default: hanya profil + riwayat pendidikan")
    parser.add_argument("--max-fail", type=int, default=10, dest="max_fail", help="Batalkan proses jika gagal berturut-turut sebanyak N kali (default: 10)")
    parser.add_argument("--shard",        type=int, default=0, help="Index shard (0-based), untuk paralel. e.g. 0")
    parser.add_argument("--total-shards", type=int, default=1, help="Total shard, e.g. 2 untuk 2 proses paralel")
    parser.add_argument("--status",       action="store_true", help="Tampilkan ringkasan progress lalu keluar")
    args = parser.parse_args()

    args.profile_only = False  # tidak dipakai lagi, dihapus dari detaildosen

    DOSEN_DIR.mkdir(parents=True, exist_ok=True)

    if args.status:
        print_status()
        return

    log_suffix = " [full]" if args.full else " [default: profil+pendidikan]"

    if args.retry_failed:
        failed = load_failed()
        if not failed:
            print("Tidak ada entri di failed list.")
            return
        print(f"Retry {len(failed)} dosen yang gagal...")
        # Hapus file failed agar tidak double-count
        save_failed([])
        dosen_list = [{
            "uid":         e.get("uid", e.get("nidn", e.get("nuptk",""))),
            "uid_type":    e.get("uid_type", "nidn" if e.get("nidn") else "nuptk"),
            "nidn":        e.get("nidn", ""),
            "nuptk":       e.get("nuptk", ""),
            "nama":        e["nama"],
            "pt_nama":     e["pt_nama"],
            "pt_kode":     e.get("pt_kode", ""),
            "pendidikan":  e.get("pendidikan", ""),
            "status":      e.get("status", ""),
            "ikatan_kerja":e.get("ikatan_kerja", ""),
        } for e in failed]
    else:
        dosen_list = collect_dosen(pt_kode_filter=args.pt_kode or None)

    # Shard filtering — bagi dosen list berdasarkan index
    if args.total_shards > 1:
        dosen_list = [d for i, d in enumerate(dosen_list) if i % args.total_shards == args.shard]
        print(f"[shard] {args.shard+1}/{args.total_shards} — {len(dosen_list)} dosen di shard ini")

    if args.dry_run:
        todo = [d for d in dosen_list if not already_done(d["nidn"])]
        print(f"\nDry run — {len(todo)} dosen akan discrape (dari {len(dosen_list)} total):\n")
        for d in todo[:20]:
            print(f"  {d['nidn']:12s} | {d['nama'][:35]:35s} | {d['pt_nama'][:40]}")
        if len(todo) > 20:
            print(f"  ... dan {len(todo)-20} lainnya")
        return

    run_batch(dosen_list, args)


if __name__ == "__main__":
    main()
