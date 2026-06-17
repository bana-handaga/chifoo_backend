"""
Scraper PDDikti — Detail Dosen v3 (Retry dosen yang error di v2)

Perbedaan dari v2:
  v2 : cari dengan "NAMA PT" → gagal jika dosen tercatat di PT berbeda di PDDikti
  v3 : cari dengan "NAMA" saja, lalu validasi:
         1. Nama hasil scrape harus sama persis (case-insensitive, kata-per-kata)
         2. Pendidikan Tertinggi harus cocok dengan data homebase (S1/S2/S3)
       Jika cocok → simpan. Jika tidak ada yang cocok → error (belum ada di PDDikti).

Alur:
  1. Kumpulkan dosen yang belum punya file output (sama seperti v2 --resume)
  2. Untuk tiap dosen: cari di PDDikti dengan nama saja
  3. Dari semua hasil yang muncul di tab Dosen, filter nama yang sama persis
  4. Buka tiap kandidat, cek Pendidikan Tertinggi cocok
  5. Jika cocok → scrape lengkap dan simpan
  6. Jika tidak ada yang cocok → catat sebagai error

Usage:
    # Semua dosen yang belum ada file output
    python scrape_pddikti_detaildosen_v3.py --resume

    # Filter PT tertentu
    python scrape_pddikti_detaildosen_v3.py --kode_pt 011003 --resume

    # Scrape ulang meski file sudah ada
    python scrape_pddikti_detaildosen_v3.py --force

    # Batasi jumlah
    python scrape_pddikti_detaildosen_v3.py --resume --limit 20

    # Tampilkan browser (debug)
    python scrape_pddikti_detaildosen_v3.py --kode_pt 011003 --limit 3 --debug
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrape_pddikti_detaildosen_v1 import (
    BASE_URL,
    init_driver,
    wait_text_loaded,
    scrape_detail_dosen,
)
from scrape_pddikti_detaildosen_v2 import (
    dosen_out_path,
    collect_dosen,
)

OUTS_DIR = Path(__file__).resolve().parent.parent / "outs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_nama(nama):
    """Normalisasi nama: uppercase, hapus spasi berlebih, strip."""
    return " ".join(nama.upper().split())


def nama_exact_match(nama_a, nama_b):
    """True jika nama sama persis setelah normalisasi."""
    return normalize_nama(nama_a) == normalize_nama(nama_b)


def pendidikan_match(pendidikan_profil, pendidikan_homebase):
    """
    True jika pendidikan cocok.
    Toleransi: keduanya dinormalisasi uppercase strip.
    Contoh: 'S2' == 'S2', 'S3' == 'S3'
    """
    if not pendidikan_homebase:
        return True  # tidak ada data homebase → tidak bisa validasi, anggap cocok
    return pendidikan_profil.upper().strip() == pendidikan_homebase.upper().strip()


# ---------------------------------------------------------------------------
# Cari detail dosen berdasarkan nama saja
# ---------------------------------------------------------------------------

def find_candidates_by_name(driver, nama_dosen):
    """
    Cari di PDDikti dengan nama saja.
    Return list of {href, nama_card, pt_card} dari tab Dosen.
    """
    keyword = nama_dosen.replace(" ", "%20")
    url = f"{BASE_URL}/search/{keyword}"
    print(f"\n[1] Pencarian nama saja: {url}")
    driver.get(url)
    wait_text_loaded(driver, timeout=20)

    # Klik tab Dosen
    tab_dosen = None
    for el in driver.find_elements("xpath", "//*[contains(@class,'tab') or contains(@role,'tab')]"):
        if "dosen" in el.text.strip().lower():
            tab_dosen = el
            break
    if not tab_dosen:
        for tag in ["button", "li", "div", "a", "span"]:
            for el in driver.find_elements("tag name", tag):
                txt = el.text.strip()
                if re.match(r"^dosen\s*\(?\d*\)?$", txt, re.I):
                    tab_dosen = el
                    break
            if tab_dosen:
                break

    if tab_dosen:
        try:
            driver.execute_script("arguments[0].click();", tab_dosen)
            time.sleep(4)
        except Exception:
            pass

    # Kumpulkan kandidat via JS: cari <tr> ancestor terdekat per link,
    # lalu ambil teks <td> pertama (nama) dan kedua (PT)
    raw = driver.execute_script("""
        var results = [];
        var seen = {};
        var links = document.querySelectorAll('a[href*="/detail-dosen/"]');
        links.forEach(function(a) {
            var href = a.href;
            if (seen[href]) return;
            seen[href] = true;

            var nama = '', pt = '';

            // Strategi 1: cari <tr> ancestor → ambil td[0] dan td[1]
            var el = a.parentElement;
            var maxUp = 12;
            while (el && el.tagName !== 'TR' && maxUp-- > 0) {
                el = el.parentElement;
            }
            if (el && el.tagName === 'TR') {
                var tds = el.querySelectorAll('td');
                if (tds.length >= 2) {
                    nama = tds[0].innerText.trim();
                    pt   = tds[1].innerText.trim();
                }
            }

            // Strategi 2: jika bukan tabel, cari card container (div/li)
            // dengan konten ringkas (max 5 baris teks)
            if (!nama) {
                el = a.parentElement;
                maxUp = 8;
                while (el && maxUp-- > 0) {
                    var lines = (el.innerText || '').trim().split('\\n')
                                .map(function(s){ return s.trim(); })
                                .filter(function(s){ return s.length > 0; });
                    // Card individual: max 8 baris, baris pertama bukan header
                    if (lines.length >= 1 && lines.length <= 8
                        && lines[0].toLowerCase() !== 'nama'
                        && !lines[0].toLowerCase().startsWith('perguruan')) {
                        nama = lines[0];
                        pt   = lines.length > 1 ? lines[1] : '';
                        break;
                    }
                    el = el.parentElement;
                }
            }

            results.push({href: href, nama_card: nama, pt_card: pt});
        });
        return results;
    """)

    candidates = raw if raw else []

    print(f"[1] Ditemukan {len(candidates)} kandidat dosen")
    for c in candidates:
        print(f"    {c['nama_card']} | {c['pt_card']} → {c['href'][:70]}")

    return candidates, url


def scrape_one_v3(driver, dosen, full=False):
    """
    Cari dosen berdasarkan nama saja, validasi nama + pendidikan.
    Return data_dict atau raise ValueError.
    """
    nama_target       = dosen["nama"]
    pendidikan_target = dosen["pendidikan"]

    candidates, url_pencarian = find_candidates_by_name(driver, nama_target)

    if not candidates:
        raise ValueError("Tidak ada kandidat dosen ditemukan (0 link)")

    # Filter kandidat dengan nama sama persis dari card
    cocok = [c for c in candidates if nama_exact_match(c["nama_card"], nama_target)]
    n_nama_terbaca = sum(1 for c in candidates if c["nama_card"])

    if not cocok:
        if n_nama_terbaca == 0:
            # Nama card sama sekali tidak terbaca — fallback buka semua
            print(f"  [WARN] Nama card tidak terbaca (0/{len(candidates)}), buka semua satu per satu...")
            cocok = candidates
        else:
            # Nama terbaca tapi tidak ada yang cocok → tidak perlu buka satu pun
            raise ValueError(
                f"Nama tidak ditemukan di {len(candidates)} hasil pencarian "
                f"(nama terbaca: {n_nama_terbaca})"
            )

    print(f"  Kandidat nama cocok: {len(cocok)} dari {len(candidates)}")

    for c in cocok:
        print(f"  → Buka: {c['href'][:80]}")
        try:
            data = scrape_detail_dosen(
                driver,
                c["href"],
                url_pencarian    = url_pencarian,
                nuptk_input      = dosen["nuptk"],
                pendidikan_input = dosen["pendidikan"],
                status_input     = dosen["status"],
                full             = full,
            )
        except Exception as e:
            print(f"  [WARN] Gagal scrape kandidat: {e}")
            continue

        profil = data.get("profil", {})
        nama_profil = profil.get("Nama", "")
        pend_profil = profil.get("Pendidikan Tertinggi", "")

        print(f"  Nama profil  : {nama_profil}")
        print(f"  Pendidikan   : {pend_profil} (target: {pendidikan_target})")

        # Validasi nama sama persis
        if not nama_exact_match(nama_profil, nama_target):
            print(f"  ✗ Nama tidak cocok, skip.")
            continue

        # Validasi pendidikan
        if not pendidikan_match(pend_profil, pendidikan_target):
            print(f"  ✗ Pendidikan tidak cocok ({pend_profil} ≠ {pendidikan_target}), skip.")
            continue

        print(f"  ✓ Nama dan pendidikan cocok!")
        data["source"] = {
            "nidn":       dosen["nidn"],
            "nama":       dosen["nama"],
            "nama_pt":    dosen["nama_pt"],
            "kode_pt":    dosen["kode_pt"],
            "nuptk":      dosen["nuptk"],
            "pendidikan": dosen["pendidikan"],
            "status":     dosen["status"],
            "metode":     "v3_nama_saja",
        }
        return data

    raise ValueError(
        f"Tidak ada kandidat yang cocok (nama+pendidikan) dari {len(cocok)} kandidat"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Retry scrape detail dosen PDDikti — cari berdasarkan nama saja"
    )
    parser.add_argument("--kode_pt", nargs="+", default=None)
    parser.add_argument("--resume", action="store_true",
                        help="Skip dosen yang file output-nya sudah ada")
    parser.add_argument("--force",  action="store_true",
                        help="Scrape ulang meski file sudah ada")
    parser.add_argument("--full",   action="store_true",
                        help="Scrape semua section (+ mengajar, penelitian, dll.)")
    parser.add_argument("--limit",  type=int, default=None)
    parser.add_argument("--debug",  action="store_true",
                        help="Tampilkan browser (tidak headless)")
    args = parser.parse_args()

    kode_pt_set = set(args.kode_pt) if args.kode_pt else None
    all_dosen   = collect_dosen(kode_pt_filter=kode_pt_set)

    print(f"Dosen unik dari JSON homebase : {len(all_dosen)}")
    if kode_pt_set:
        print(f"Filter kode_pt               : {sorted(kode_pt_set)}")

    if not args.force:
        todo = [d for d in all_dosen if not dosen_out_path(d).exists()]
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

    done = error = 0
    driver = init_driver(headless=not args.debug)

    try:
        for i, dosen in enumerate(todo, 1):
            id_str  = dosen["nidn"] or f"nuptk:{dosen['nuptk']}"
            nama    = dosen["nama"]
            nama_pt = dosen["nama_pt"]
            out     = dosen_out_path(dosen)
            out.parent.mkdir(parents=True, exist_ok=True)

            print(f"\n[{i}/{len(todo)}] {id_str} — {nama}  ({nama_pt})")

            # Restart driver setiap 50 dosen
            if i > 1 and (i - 1) % 50 == 0:
                print("  [INFO] Restart driver...")
                try:
                    driver.quit()
                except Exception:
                    pass
                time.sleep(2)
                driver = init_driver(headless=not args.debug)

            try:
                data = scrape_one_v3(driver, dosen, full=args.full)

                with open(out, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                size_kb   = out.stat().st_size / 1024
                n_riwpend = len(data.get("riwayat_pendidikan", []))
                print(f"  ✓ Tersimpan ({size_kb:.1f} KB) — pendidikan={n_riwpend}")
                done += 1

            except Exception as e:
                print(f"  [ERROR] {id_str}: {e}")
                error += 1
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
