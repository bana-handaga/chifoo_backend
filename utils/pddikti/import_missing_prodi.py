#!/usr/bin/env python3
"""
Tambahkan program studi yang ada di ept_itps.json tapi belum ada di DB.

Usage:
    python3 utils/import_missing_prodi.py [--dry-run]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", 3306)),
    "user":     os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "db":       os.environ.get("DB_NAME", "ptma_db"),
    "charset":  "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

JENJANG_MAP = {
    "D1": "d1", "D2": "d2", "D3": "d3", "D4": "d4",
    "S1": "s1", "S2": "s2", "S3": "s3",
    "PROFESI": "profesi", "SPESIALIS": "profesi",
    "SP-1": "profesi", "SP-2": "profesi",
}

AKREDITASI_MAP = {
    "UNGGUL":      "unggul",
    "BAIK SEKALI": "baik_sekali",
    "BAIK":        "baik",
    "C":           "c",
    "B":           "baik",
    "A":           "unggul",
}

SRC_PATH = Path(__file__).resolve().parent / "ept" / "ept_itps.json"


def map_jenjang(raw: str) -> str:
    return JENJANG_MAP.get(raw.strip().upper(), "s1")


def map_akreditasi(raw: str) -> str:
    return AKREDITASI_MAP.get(raw.strip().upper(), "belum")


def run(dry_run: bool) -> None:
    # ── Baca sumber JSON ─────────────────────────────────────────
    with open(SRC_PATH, encoding="utf-8") as f:
        records = json.load(f)

    prodi_json: list[dict] = []
    for rec in records:
        ps = rec["fields"]["ps"]
        if isinstance(ps, str):
            ps = json.loads(ps)
        prodi_json.append({
            "kodept":  ps.get("kodept", "").strip(),
            "pskode":  ps.get("pskode", "").strip(),
            "nama":    ps.get("ps", "").strip(),
            "jenjang": map_jenjang(ps.get("jenjang", "")),
            "akr":     map_akreditasi(ps.get("akreditasi", "")),
            "aktif":   ps.get("status", "Aktif") == "Aktif",
        })

    print(f"Total prodi di JSON  : {len(prodi_json)}")

    # ── Koneksi DB ───────────────────────────────────────────────
    conn = pymysql.connect(**DB_CONFIG)
    cur  = conn.cursor()

    # Ambil semua PT (kode_pt → id)
    cur.execute("SELECT id, kode_pt FROM universities_perguruantinggi")
    pt_map = {row["kode_pt"]: row["id"] for row in cur.fetchall()}

    # Ambil semua prodi yang sudah ada (pt_id, kode_prodi)
    cur.execute("SELECT perguruan_tinggi_id, kode_prodi FROM universities_programstudi")
    existing = {(row["perguruan_tinggi_id"], row["kode_prodi"]) for row in cur.fetchall()}

    print(f"PT di DB             : {len(pt_map)}")
    print(f"Prodi di DB          : {len(existing)}")

    # ── Cari yang hilang ─────────────────────────────────────────
    to_insert: list[dict] = []
    skipped_no_pt: list[tuple] = []

    for p in prodi_json:
        pt_id = pt_map.get(p["kodept"])
        if pt_id is None:
            skipped_no_pt.append((p["kodept"], p["pskode"], p["nama"]))
            continue
        if (pt_id, p["pskode"]) not in existing:
            to_insert.append({**p, "pt_id": pt_id})

    print(f"Prodi hilang (tambah): {len(to_insert)}")
    if skipped_no_pt:
        print(f"Dilewati (PT tdk ada): {len(skipped_no_pt)}")
        for kodept, pskode, nama in skipped_no_pt:
            print(f"  PT {kodept} tidak ditemukan → [{pskode}] {nama}")

    if not to_insert:
        print("\nTidak ada prodi yang perlu ditambahkan.")
        cur.close(); conn.close()
        return

    print("\nProdi yang akan ditambahkan:")
    for p in to_insert:
        print(f"  PT {p['kodept']}  [{p['pskode']}] [{p['jenjang']:>6}] {p['nama']}")

    if dry_run:
        print("\n[DRY-RUN] Tidak ada perubahan disimpan.")
        cur.close(); conn.close()
        return

    # ── Insert ───────────────────────────────────────────────────
    sql = """
        INSERT INTO universities_programstudi
            (perguruan_tinggi_id, kode_prodi, nama, jenjang, akreditasi,
             no_sk_akreditasi, tanggal_kedaluarsa_akreditasi, is_active,
             created_at, updated_at)
        VALUES
            (%s, %s, %s, %s, %s, '', NULL, %s, NOW(), NOW())
    """
    inserted = 0
    errors   = 0
    for p in to_insert:
        try:
            cur.execute(sql, (
                p["pt_id"], p["pskode"], p["nama"],
                p["jenjang"], p["akr"], p["aktif"],
            ))
            inserted += 1
        except Exception as e:
            print(f"  [ERROR] {p['kodept']} [{p['pskode']}] {p['nama']}: {e}")
            errors += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nSelesai: {inserted} ditambahkan, {errors} error.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import prodi yang hilang dari ept_itps.json")
    parser.add_argument("--dry-run", action="store_true", help="Preview tanpa menulis ke DB")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
