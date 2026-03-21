"""
Script untuk mengambil data akreditasi institusi dari BAN-PT
Sumber: https://www.banpt.or.id/direktori/institusi/pencarian_institusi.php
API:    https://www.banpt.or.id/direktori/model/dir_aipt/get_data_institusi.php

Input:  outs/namapt_list.json
Output: outs/banpt_pt.json
"""

import json
import html
import re
import time
import urllib.request
from difflib import SequenceMatcher

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_URL = "https://www.banpt.or.id/direktori/model/dir_aipt/get_data_institusi.php"
INPUT_FILE = "outs/namapt_list.json"
OUTPUT_FILE = "outs/banpt_pt.json"

# Skor minimum kesamaan nama untuk fuzzy matching (0.0 - 1.0)
FUZZY_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def normalize(name: str) -> str:
    """Normalisasi nama: uppercase, strip, hapus karakter ekstra."""
    name = html.unescape(name)
    name = name.upper().strip()
    name = re.sub(r"\s+", " ", name)
    return name


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def fetch_all_banpt() -> list[dict]:
    """Ambil semua data institusi dari API BAN-PT."""
    print(f"Fetching data dari: {API_URL}")
    req = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.banpt.or.id/direktori/institusi/pencarian_institusi.php",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    # Setiap baris: [nama_pt, peringkat, nomor_sk, tahun, wilayah, tgl_exp, status]
    records = []
    for row in raw.get("data", []):
        records.append(
            {
                "nama_pt":     html.unescape(row[0]).strip(),
                "peringkat":   row[1],
                "nomor_sk":    row[2],
                "tahun":       row[3],
                "wilayah":     row[4],
                "tgl_expired": row[5],
                "status":      row[6],
            }
        )
    print(f"Total institusi dari BAN-PT: {len(records)}")
    return records


def build_index(records: list[dict]) -> dict[str, dict]:
    """Buat index nama ternormalisasi -> record."""
    return {normalize(r["nama_pt"]): r for r in records}


def match_pt(target: str, index: dict, threshold: float = FUZZY_THRESHOLD):
    """
    Cari PT di index:
    1. Exact match (setelah normalisasi)
    2. Fuzzy match dengan skor tertinggi >= threshold
    Kembalikan (record | None, skor, metode)
    """
    norm_target = normalize(target)

    # 1. Exact
    if norm_target in index:
        return index[norm_target], 1.0, "exact"

    # 2. Fuzzy
    best_score = 0.0
    best_key = None
    for key in index:
        score = similarity(norm_target, key)
        if score > best_score:
            best_score = score
            best_key = key

    if best_score >= threshold and best_key:
        return index[best_key], best_score, "fuzzy"

    return None, best_score, "not_found"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Load daftar PT
    with open(INPUT_FILE, encoding="utf-8") as f:
        pt_list = json.load(f)
    print(f"Jumlah PT dicari: {len(pt_list)}")

    # Fetch semua data BAN-PT
    banpt_records = fetch_all_banpt()
    index = build_index(banpt_records)

    results = []
    not_found = []

    for i, pt in enumerate(pt_list, 1):
        target = pt["target"]
        kode = pt.get("kode", "")

        record, score, method = match_pt(target, index)

        if record:
            entry = {
                "kode":        kode,
                "target":      target,
                "nama_banpt":  record["nama_pt"],
                "peringkat":   record["peringkat"],
                "nomor_sk":    record["nomor_sk"],
                "tahun":       record["tahun"],
                "wilayah":     record["wilayah"],
                "tgl_expired": record["tgl_expired"],
                "status":      record["status"],
                "match_score": round(score, 4),
                "match_method": method,
            }
            print(f"[{i:>3}] OK ({method}, {score:.2f}) {target}")
        else:
            entry = {
                "kode":         kode,
                "target":       target,
                "nama_banpt":   None,
                "peringkat":    None,
                "nomor_sk":     None,
                "tahun":        None,
                "wilayah":      None,
                "tgl_expired":  None,
                "status":       None,
                "match_score":  round(score, 4),
                "match_method": method,
            }
            not_found.append(target)
            print(f"[{i:>3}] TIDAK DITEMUKAN (best={score:.2f}) {target}")

        results.append(entry)

    # Simpan output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n=== Selesai ===")
    print(f"Total    : {len(results)}")
    print(f"Ditemukan: {len(results) - len(not_found)}")
    print(f"Tidak    : {len(not_found)}")
    if not_found:
        print("\nTidak ditemukan:")
        for name in not_found:
            print(f"  - {name}")
    print(f"\nOutput disimpan ke: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
