"""Update akreditasi prodi dari LAM-PTKes untuk prodi yang masih 'belum' di DB.

Strategi matching:
  1. Filter prodi DB yang akreditasi='belum'
  2. Bangun index LAM-PTKes: normalized_nama_pt -> list[record]
  3. Untuk setiap prodi 'belum': cari di LAM-PTKes berdasarkan nama PT (via banpt_pt.json)
     + nama prodi + jenjang (exact, lalu fuzzy)
  4. Update hanya jika exact match (nama + jenjang)
"""

import json
import html
import re
import os
from collections import defaultdict
from difflib import SequenceMatcher

import MySQLdb
from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = dotenv_values(os.path.join(BASE_DIR, ".env"))

LAMPTKES_FILE = os.path.join(BASE_DIR, "utils/ext/lamptkes_prodi.json")
BANPT_PT_FILE  = os.path.join(BASE_DIR, "utils/ext/banpt_pt.json")

FUZZY_THRESHOLD = 0.88

# ---------------------------------------------------------------------------
# Mapping jenjang
# ---------------------------------------------------------------------------

JENJANG_DB_MAP = {
    "d1": "d1", "d2": "d2", "d3": "d3", "d4": "d4",
    "s1": "s1", "profesi": "profesi",
    "s2": "s2", "s3": "s3",
    "sp-1": "spesialis", "sp-2": "subspesialis",
}

JENJANG_LAMPTKES_MAP = {
    "diploma satu":           "d1",
    "diploma dua":            "d2",
    "diploma tiga":           "d3",
    "diploma empat":          "d4",
    "diploma empat pendidik": "d4",
    "sarjana terapan":        "d4",
    "sarjana":                "s1",
    "sarjana pendidikan":     "s1",
    "profesi":                "profesi",
    "pendidikan profesi":     "profesi",
    "profesi dokter":         "profesi",
    "magister":               "s2",
    "magister terapan":       "s2",
    "doktor":                 "s3",
    "spesialis":              "spesialis",
    "sub spesialis":          "subspesialis",
}

PERINGKAT_MAP = {
    "unggul":               "unggul",
    "terakreditasi unggul": "unggul",
    "a":                    "unggul",
    "baik sekali":          "baik_sekali",
    "baik":                 "baik",
    "b":                    "baik_sekali",
    "terakreditasi":        "baik",
    "c":                    "c",
    "tidak terakreditasi":  "belum",
}


def normalize(name: str) -> str:
    name = re.sub(r"[.]", "", html.unescape(name))
    return re.sub(r"\s+", " ", name.upper().strip())

def strip_city_suffix(name: str) -> str | None:
    m = re.search(r",\s+[A-Z\s]+$", name)
    if m:
        return name[: m.start()].strip()
    return None

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def map_peringkat(raw: str) -> str:
    return PERINGKAT_MAP.get((raw or "").strip().lower(), "belum")


# ---------------------------------------------------------------------------
# Build index
# ---------------------------------------------------------------------------

def build_index(records: list[dict]) -> dict:
    idx = defaultdict(list)
    for r in records:
        key = normalize(r["nama_pt"])
        idx[key].append(r)
        stripped = strip_city_suffix(key)
        if stripped and stripped != key:
            idx[stripped].append(r)
    return idx


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------

def match_prodi(target_nama, target_jenjang_db, candidates):
    norm_target   = normalize(target_nama)
    canon_jenjang = JENJANG_DB_MAP.get(target_jenjang_db.lower())

    for rec in candidates:
        norm_cand   = normalize(rec["nama_prodi"])
        canon_cand  = JENJANG_LAMPTKES_MAP.get(rec["jenjang"].lower())
        jenjang_ok  = (canon_jenjang is not None and canon_cand == canon_jenjang)

        if norm_target == norm_cand and jenjang_ok:
            return rec, 1.0, "exact"

    # Fuzzy
    best_rec, best_score = None, 0.0
    for rec in candidates:
        norm_cand  = normalize(rec["nama_prodi"])
        canon_cand = JENJANG_LAMPTKES_MAP.get(rec["jenjang"].lower())
        jenjang_ok = (canon_jenjang is not None and canon_cand == canon_jenjang)
        score = similarity(norm_target, norm_cand) + (0.05 if jenjang_ok else 0)
        if score > best_score:
            best_score, best_rec = score, rec

    if best_score >= FUZZY_THRESHOLD and best_rec:
        return best_rec, round(min(best_score, 1.0), 4), "fuzzy"

    return None, 0.0, "not_found"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    with open(LAMPTKES_FILE, encoding="utf-8") as f:
        lamptkes = json.load(f)

    with open(BANPT_PT_FILE, encoding="utf-8") as f:
        banpt_pt = json.load(f)

    # kode_pt -> nama_banpt
    pt_map = {d["kode"]: d.get("nama_banpt") for d in banpt_pt}

    index = build_index(lamptkes)

    db = MySQLdb.connect(
        host=env["DB_HOST"], user=env["DB_USER"],
        passwd=env["DB_PASSWORD"], db=env["DB_NAME"],
        port=int(env["DB_PORT"]), charset="utf8mb4",
    )
    cur = db.cursor()

    # Ambil prodi yang belum terakreditasi
    cur.execute("""
        SELECT ps.kode_prodi, ps.nama, ps.jenjang, pt.nama
        FROM universities_programstudi ps
        JOIN universities_perguruantinggi pt ON pt.id = ps.perguruan_tinggi_id
        WHERE ps.akreditasi = 'belum'
        ORDER BY pt.nama, ps.nama
    """)
    rows = cur.fetchall()
    print(f"Prodi 'belum' di DB: {len(rows)}")

    update_rows = []   # (akreditasi, nomor_sk, tgl_expired, kode_prodi)
    exact_count = fuzzy_count = not_found = pt_skip = 0

    for kode_prodi, nama_prodi, jenjang, nama_pt in rows:
        candidates = index.get(normalize(nama_pt), [])
        if not candidates:
            not_found += 1
            continue

        rec, score, method = match_prodi(nama_prodi, jenjang, candidates)
        if rec:
            akreditasi  = map_peringkat(rec["peringkat"])
            nomor_sk    = rec.get("nomor_sk") or ""
            tgl_expired = rec.get("tgl_expired")
            update_rows.append((akreditasi, nomor_sk, tgl_expired, kode_prodi))
            if method == "exact":
                exact_count += 1
            else:
                fuzzy_count += 1
            print(f"  {'OK' if method=='exact' else '~'} ({score:.2f}) {nama_pt} / {nama_prodi} ({jenjang}) → {akreditasi}")
        else:
            not_found += 1

    # Batch update
    if update_rows:
        cur.executemany(
            """UPDATE universities_programstudi
               SET akreditasi=%s, no_sk_akreditasi=%s, tanggal_kedaluarsa_akreditasi=%s
               WHERE kode_prodi=%s""",
            update_rows,
        )
        db.commit()

    db.close()

    print(f"\n=== Selesai ===")
    print(f"Exact updated  : {exact_count}")
    print(f"Fuzzy updated  : {fuzzy_count}")
    print(f"Tidak ditemukan: {not_found}")
    print(f"PT skip (belum): {pt_skip}")
    print(f"Total diproses : {len(rows)}")


if __name__ == "__main__":
    main()
