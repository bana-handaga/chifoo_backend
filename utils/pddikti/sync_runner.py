#!/usr/bin/env python3
"""
Orkestrator sinkronisasi PDDikti berdasarkan SinkronisasiJadwal.

Dijalankan oleh backend (subprocess) atau manual:
    python sync_runner.py --jadwal_id 1
    python sync_runner.py --jadwal_id 1 --dry-run

Alur:
  1. Baca jadwal dari DB
  2. Tentukan daftar PT (semua / pilihan)
  3. Jalankan sync_prodi_dosen atau sync_detail_dosen untuk tiap PT
  4. Update status di DB sepanjang proses
"""

import argparse
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pymysql
from dotenv import load_dotenv

# ── Env & DB ──────────────────────────────────────────────────
UTILS_DIR = Path(__file__).resolve().parent
ENV_PATH  = UTILS_DIR.parent.parent / ".env"
load_dotenv(ENV_PATH)

sys.path.insert(0, str(UTILS_DIR))
from sync_db_helper import update_jadwal_status, ensure_connection

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

LOG_LINES = []


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_LINES.append(line)


def get_pt_list(conn, jadwal):
    """Kembalikan list {'kode_pt', 'nama'} sesuai mode_pt jadwal."""
    with conn.cursor() as cur:
        if jadwal["mode_pt"] == "semua":
            cur.execute(
                "SELECT kode_pt, nama FROM universities_perguruantinggi "
                "WHERE kode_pt IS NOT NULL AND kode_pt != '' ORDER BY nama"
            )
            return cur.fetchall()
        else:
            cur.execute(
                """
                SELECT pt.kode_pt, pt.nama
                FROM universities_perguruantinggi pt
                JOIN universities_sinkronisasijadwal_pt_list sl
                  ON pt.id = sl.perguruantinggi_id
                WHERE sl.sinkronisasijadwal_id = %s
                ORDER BY pt.nama
                """,
                (jadwal["id"],),
            )
            return cur.fetchall()


def run(jadwal_id, dry_run=False):
    conn = pymysql.connect(**DB_CONFIG)

    # Tandai berjalan
    update_jadwal_status(conn, jadwal_id, "berjalan", "Memulai proses...", pid=os.getpid())
    log(f"Jadwal ID={jadwal_id} dimulai (PID={os.getpid()}, dry_run={dry_run})")

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM universities_sinkronisasijadwal WHERE id=%s", (jadwal_id,)
            )
            jadwal = cur.fetchone()
        if not jadwal:
            raise ValueError(f"Jadwal ID {jadwal_id} tidak ditemukan di DB.")

        pt_list = get_pt_list(conn, jadwal)
        total   = len(pt_list)
        log(f"Mode PT: {jadwal['mode_pt']} — total {total} PT")

        if total == 0:
            update_jadwal_status(conn, jadwal_id, "selesai", "Tidak ada PT yang perlu di-sync.", pid=None)
            return

        tipe = jadwal["tipe_sync"]
        errors = []

        if tipe == "prodi_dosen":
            from sync_prodi_dosen import sync as sync_pd
            for i, pt in enumerate(pt_list, 1):
                pesan = f"[{i}/{total}] Sync prodi+dosen: {pt['kode_pt']} — {pt['nama']}"
                update_jadwal_status(conn, jadwal_id, "berjalan", pesan, pid=os.getpid())
                log(pesan)
                try:
                    sync_pd(pt["kode_pt"], pt["nama"], dry_run)
                    log(f"  ✓ {pt['kode_pt']} selesai")
                except Exception as e:
                    msg = f"{pt['kode_pt']}: {e}"
                    log(f"  ✗ {msg}")
                    errors.append(msg)

        elif tipe == "detail_dosen":
            from sync_detail_dosen import sync as sync_dd
            for i, pt in enumerate(pt_list, 1):
                pesan = f"[{i}/{total}] Sync detail dosen: {pt['kode_pt']} — {pt['nama']}"
                update_jadwal_status(conn, jadwal_id, "berjalan", pesan, pid=os.getpid())
                log(pesan)
                try:
                    sync_dd(kode_pt=pt["kode_pt"], dry_run=dry_run)
                    log(f"  ✓ {pt['kode_pt']} selesai")
                except Exception as e:
                    msg = f"{pt['kode_pt']}: {e}"
                    log(f"  ✗ {msg}")
                    errors.append(msg)

        else:
            raise ValueError(f"Tipe sync tidak dikenal: {tipe}")

        # Ringkasan akhir
        if errors:
            ringkasan = f"Selesai dengan {len(errors)} error dari {total} PT:\n" + "\n".join(errors[:20])
            update_jadwal_status(conn, jadwal_id, "error", ringkasan, pid=None)
            log(f"Selesai dengan {len(errors)} error.")
        else:
            ringkasan = f"Berhasil sync {total} PT — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            update_jadwal_status(conn, jadwal_id, "selesai", ringkasan, pid=None)
            log("Semua PT berhasil di-sync.")

    except Exception as e:
        tb = traceback.format_exc()
        log(f"ERROR: {e}")
        update_jadwal_status(conn, jadwal_id, "error", f"Error: {e}\n{tb[:500]}", pid=None)
        sys.exit(1)

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Jalankan sinkronisasi PDDikti berdasarkan jadwal_id"
    )
    parser.add_argument("--jadwal_id", type=int, required=True, help="ID SinkronisasiJadwal")
    parser.add_argument("--dry-run", action="store_true", help="Preview tanpa menulis ke DB")
    args = parser.parse_args()
    run(args.jadwal_id, args.dry_run)


if __name__ == "__main__":
    main()
