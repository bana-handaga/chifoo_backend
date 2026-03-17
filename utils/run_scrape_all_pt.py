"""
Jalankan scrape_pddikti_detailprodi.py secara berurutan untuk setiap PT
yang ada di namapt_list.json.

Usage:
    python3 utils/run_scrape_all_pt.py
    python3 utils/run_scrape_all_pt.py --resume
    python3 utils/run_scrape_all_pt.py --force
    python3 utils/run_scrape_all_pt.py --start 5
    python3 utils/run_scrape_all_pt.py --start 5 --end 10
    python3 utils/run_scrape_all_pt.py --resume --start 3 --end 20
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path

UTILS_DIR   = Path(__file__).parent
NAMAPT_FILE = UTILS_DIR / "ept" / "namapt_list.json"
SCRAPER     = UTILS_DIR / "scrape_pddikti_detailprodi.py"


def main():
    parser = argparse.ArgumentParser(
        description="Scrape detail prodi semua PT dari namapt_list.json"
    )
    parser.add_argument("--resume", action="store_true",
                        help="Skip prodi yang file output-nya sudah ada")
    parser.add_argument("--force",  action="store_true",
                        help="Paksa update semua prodi meskipun file sudah ada")
    parser.add_argument("--start",  type=int, default=1,
                        help="Nomor urut PT awal dalam daftar (1-based, default: 1)")
    parser.add_argument("--end",    type=int, default=None,
                        help="Nomor urut PT akhir inklusif (1-based, default: sampai akhir)")
    args = parser.parse_args()

    with open(NAMAPT_FILE, encoding="utf-8") as f:
        pt_list = json.load(f)

    total = len(pt_list)

    start_idx = max(0, args.start - 1)
    end_idx   = total if args.end is None else min(args.end, total)

    if start_idx >= total:
        print(f"--start {args.start} melebihi jumlah PT ({total}).")
        sys.exit(1)
    if end_idx <= start_idx:
        print(f"--end {args.end} harus lebih besar dari --start {args.start}.")
        sys.exit(1)

    target_list = pt_list[start_idx:end_idx]

    print("=" * 70)
    print(f"PDDikti Batch Scraper — {len(target_list)} PT (#{args.start} s/d #{end_idx} dari {total})")
    print(f"Mode  : {'force' if args.force else 'resume' if args.resume else 'fresh'}")
    print("=" * 70)

    done = errors = 0

    for i, pt in enumerate(target_list, start=args.start):
        kode    = pt["kode"]
        keyword = pt["keyword"]
        target  = pt["target"]

        print(f"\n{'='*70}")
        print(f"[{i}/{total}] {kode} — {target}")
        print(f"{'='*70}")

        cmd = [
            sys.executable, str(SCRAPER),
            "--keyword", keyword,
            "--nama",    target,
            "--kode",    kode,
        ]
        if args.resume:
            cmd.append("--resume")
        if args.force:
            cmd.append("--force")

        result = subprocess.run(cmd, cwd=str(UTILS_DIR))

        if result.returncode == 0:
            done += 1
        else:
            print(f"  [ERROR] PT {kode} selesai dengan return code {result.returncode}")
            errors += 1

    print(f"\n{'='*70}")
    print(f"Selesai — berhasil: {done}, gagal: {errors}, total diproses: {len(target_list)}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
