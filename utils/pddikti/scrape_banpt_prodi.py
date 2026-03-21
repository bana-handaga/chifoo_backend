"""
Script untuk mengambil data akreditasi program studi dari BAN-PT
Sumber: https://www.banpt.or.id/direktori/prodi/pencarian_prodi.php
API:    https://www.banpt.or.id/direktori/model/dir_prodi/get_hasil_pencariannew.php

Input:
  - outs/banpt_pt.json   → mapping kode_pt -> nama_banpt PT
  - DB table universities_programstudi (via MySQL)

Output: outs/banpt_prodi.json
"""

import json
import html
import re
import os
import urllib.request
from difflib import SequenceMatcher
from collections import defaultdict

import MySQLdb
from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = dotenv_values(os.path.join(BASE_DIR, ".env"))

API_URL       = "https://www.banpt.or.id/direktori/model/dir_prodi/get_hasil_pencariannew.php"
BANPT_PT_FILE = os.path.join(BASE_DIR, "utils/outs/banpt_pt.json")
OUTPUT_FILE   = os.path.join(BASE_DIR, "utils/outs/banpt_prodi.json")

FUZZY_THRESHOLD      = 0.82   # skor minimum untuk match nama prodi
JENJANG_FUZZY_BONUS  = 0.05   # bonus jika jenjang cocok


# ---------------------------------------------------------------------------
# Normalisasi
# ---------------------------------------------------------------------------

# Mapping jenjang DB -> canonical form
JENJANG_DB_MAP = {
    "d1":      "d1",
    "d2":      "d2",
    "d3":      "d3",
    "d4":      "d4",
    "s1":      "s1",
    "profesi": "profesi",
    "s2":      "s2",
    "s3":      "s3",
    "sp-1":    "spesialis",
    "sp-2":    "subspesialis",
}

# Mapping jenjang BAN-PT -> canonical form
JENJANG_BANPT_MAP = {
    "d-i":              "d1",
    "d1":               "d1",
    "d-ii":             "d2",
    "d2":               "d2",
    "d-iii":            "d3",
    "d3":               "d3",
    "diploma-iii":      "d3",
    "d-iv":             "d4",
    "d4":               "d4",
    "s1 terapan":       "d4",
    "sarjana terapan":  "d4",
    "sarjana terapan":  "d4",
    "s1 terapan":       "d4",
    "sarjana terapan":  "d4",
    "s1 terapan":       "d4",
    "sarjana terapan":  "d4",
    "sarjana terapan":  "d4",
    "s1 terapan":       "d4",
    "s1":               "s1",
    "sarjana":          "s1",
    "sarjana":          "s1",
    "pro.":             "profesi",
    "profesi":          "profesi",
    "s2":               "s2",
    "magister":         "s2",
    "s2 terapan":       "s2",
    "s3":               "s3",
    "s3 terapan":       "s3",
    "spesialis":        "spesialis",
    "subspesialis":     "subspesialis",
    "-":                None,
}

def normalize_jenjang_banpt(raw: str) -> str | None:
    return JENJANG_BANPT_MAP.get(raw.strip().lower())

def normalize_jenjang_db(raw: str) -> str | None:
    return JENJANG_DB_MAP.get(raw.strip().lower())

def normalize_name(name: str) -> str:
    name = html.unescape(name)
    name = name.upper().strip()
    name = re.sub(r"\s+", " ", name)
    return name

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Fetch BAN-PT prodi
# ---------------------------------------------------------------------------

def fetch_banpt_prodi() -> list[dict]:
    print(f"Fetching data prodi dari BAN-PT ...")
    req = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.banpt.or.id/direktori/prodi/pencarian_prodi.php",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    # Kolom: [nama_pt, nama_prodi, jenjang, wilayah, nomor_sk, tahun, peringkat, tgl_expired, status]
    records = []
    for row in raw.get("data", []):
        tgl_expired = row[7] if row[7] not in ("-", "", None) else None
        records.append({
            "nama_pt":      html.unescape(row[0]).strip(),
            "nama_prodi":   html.unescape(row[1]).strip(),
            "jenjang":      row[2],
            "wilayah":      row[3],
            "nomor_sk":     row[4],
            "tahun":        row[5],
            "peringkat":    row[6].strip(),
            "tgl_expired":  tgl_expired,
            "status":       row[8],
        })
    print(f"Total prodi BAN-PT: {len(records)}")
    return records


def strip_city_suffix(name: str) -> str | None:
    """
    Beberapa nama PT di data prodi BAN-PT memakai format 'NAMA PT, KOTA'.
    Fungsi ini mengembalikan bagian sebelum ', KOTA' jika suffix-nya
    hanya satu token (tanpa spasi) — misal 'SURAKARTA', 'JAKARTA', dsb.
    Jika tidak ada suffix kota, kembalikan None.
    """
    m = re.search(r",\s+([A-Z]+)$", name)
    if m:
        return name[: m.start()].strip()
    return None


def build_prodi_index(records: list[dict]) -> dict:
    """
    Index: normalized_nama_pt -> list[record]
    Setiap PT diindeks dengan dua kunci:
      1. Nama asli (ternormalisasi)
      2. Nama tanpa suffix kota (jika ada format 'NAMA, KOTA')
    """
    idx = defaultdict(list)
    for r in records:
        key = normalize_name(r["nama_pt"])
        idx[key].append(r)
        stripped = strip_city_suffix(key)
        if stripped and stripped != key:
            idx[stripped].append(r)
    return idx


# ---------------------------------------------------------------------------
# Load data DB
# ---------------------------------------------------------------------------

def load_db_prodi() -> list[dict]:
    db = MySQLdb.connect(
        host=env["DB_HOST"], user=env["DB_USER"],
        passwd=env["DB_PASSWORD"], db=env["DB_NAME"],
        port=int(env["DB_PORT"]), charset="utf8mb4",
    )
    cur = db.cursor()
    cur.execute("""
        SELECT ps.kode_prodi, ps.nama, ps.jenjang, pt.nama, pt.kode_pt
        FROM universities_programstudi ps
        JOIN universities_perguruantinggi pt ON pt.id = ps.perguruan_tinggi_id
        ORDER BY pt.kode_pt, ps.nama
    """)
    rows = cur.fetchall()
    db.close()
    return [
        {
            "kode_prodi": r[0],
            "nama":       r[1],
            "jenjang":    r[2],
            "nama_pt":    r[3],
            "kode_pt":    r[4],
        }
        for r in rows
    ]


def load_pt_mapping() -> dict[str, str | None]:
    """kode_pt -> nama_banpt (dari banpt_pt.json)"""
    with open(BANPT_PT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {d["kode"]: d.get("nama_banpt") for d in data}


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def match_prodi(
    target_nama: str,
    target_jenjang_db: str,
    candidates: list[dict],
    threshold: float = FUZZY_THRESHOLD,
):
    """
    Cari prodi terbaik dari candidates (sudah difilter per PT).
    Strategi:
      1. Exact nama + jenjang cocok
      2. Exact nama (jenjang apapun)
      3. Fuzzy nama + jenjang cocok (score >= threshold)
      4. Fuzzy nama terbaik (jenjang apapun, score >= threshold - bonus)
    """
    norm_target = normalize_name(target_nama)
    canon_jenjang = normalize_jenjang_db(target_jenjang_db)

    best_record = None
    best_score  = 0.0
    best_method = "not_found"

    for rec in candidates:
        norm_cand  = normalize_name(rec["nama_prodi"])
        canon_cand = normalize_jenjang_banpt(rec["jenjang"])
        jenjang_match = (canon_jenjang is not None and canon_cand == canon_jenjang)

        score = similarity(norm_target, norm_cand)

        # Bonus jika jenjang cocok
        effective = score + (JENJANG_FUZZY_BONUS if jenjang_match else 0)

        if score == 1.0 and jenjang_match:
            return rec, 1.0, "exact"

        if score == 1.0 and effective > best_score:
            best_score  = effective
            best_record = rec
            best_method = "exact_nama"

        elif effective > best_score and effective >= threshold:
            best_score  = effective
            best_record = rec
            best_method = "fuzzy"

    if best_record:
        return best_record, round(min(best_score, 1.0), 4), best_method

    return None, round(best_score, 4), "not_found"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    banpt_records = fetch_banpt_prodi()
    prodi_index   = build_prodi_index(banpt_records)

    db_prodi  = load_db_prodi()
    pt_map    = load_pt_mapping()        # kode_pt -> nama_banpt

    print(f"Total prodi DB   : {len(db_prodi)}")

    results   = []
    stats     = {"exact": 0, "exact_nama": 0, "fuzzy": 0, "not_found": 0}

    for i, prodi in enumerate(db_prodi, 1):
        kode_pt  = prodi["kode_pt"]
        nama_banpt_pt = pt_map.get(kode_pt)  # nama PT di BAN-PT

        if not nama_banpt_pt:
            # PT tidak terakreditasi / tidak ditemukan → prodi pun skip
            entry = _entry_not_found(prodi, 0.0, "pt_not_found")
            results.append(entry)
            stats["not_found"] += 1
            print(f"[{i:>4}] PT SKIP  {prodi['nama_pt']} / {prodi['nama']}")
            continue

        norm_pt_key = normalize_name(nama_banpt_pt)
        candidates  = prodi_index.get(norm_pt_key, [])

        record, score, method = match_prodi(
            prodi["nama"], prodi["jenjang"], candidates
        )

        if record:
            entry = {
                "kode_pt":       kode_pt,
                "kode_prodi":    prodi["kode_prodi"],
                "nama_pt":       prodi["nama_pt"],
                "nama_prodi":    prodi["nama"],
                "jenjang":       prodi["jenjang"],
                "nama_banpt_pt": nama_banpt_pt,
                "nama_banpt_prodi": record["nama_prodi"],
                "jenjang_banpt": record["jenjang"],
                "peringkat":     record["peringkat"],
                "nomor_sk":      record["nomor_sk"],
                "tahun":         record["tahun"],
                "tgl_expired":   record["tgl_expired"],
                "status":        record["status"],
                "match_score":   score,
                "match_method":  method,
            }
            stats[method if method in stats else "fuzzy"] += 1
            marker = " " if method == "exact" else "~"
            print(f"[{i:>4}]{marker} ({method}, {score:.2f}) {prodi['nama_pt']} / {prodi['nama']} ({prodi['jenjang']})")
        else:
            entry = _entry_not_found(prodi, score, "not_found")
            stats["not_found"] += 1
            print(f"[{i:>4}]! TIDAK DITEMUKAN (best={score:.2f}) {prodi['nama_pt']} / {prodi['nama']} ({prodi['jenjang']})")

        results.append(entry)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n=== Selesai ===")
    print(f"Total          : {len(results)}")
    print(f"Exact          : {stats['exact']}")
    print(f"Exact (nama)   : {stats['exact_nama']}")
    print(f"Fuzzy          : {stats['fuzzy']}")
    print(f"Tidak ditemukan: {stats['not_found']}")
    print(f"\nOutput: {OUTPUT_FILE}")


def _entry_not_found(prodi: dict, score: float, method: str) -> dict:
    return {
        "kode_pt":          prodi["kode_pt"],
        "kode_prodi":       prodi["kode_prodi"],
        "nama_pt":          prodi["nama_pt"],
        "nama_prodi":       prodi["nama"],
        "jenjang":          prodi["jenjang"],
        "nama_banpt_pt":    None,
        "nama_banpt_prodi": None,
        "jenjang_banpt":    None,
        "peringkat":        None,
        "nomor_sk":         None,
        "tahun":            None,
        "tgl_expired":      None,
        "status":           None,
        "match_score":      score,
        "match_method":     method,
    }


if __name__ == "__main__":
    main()
