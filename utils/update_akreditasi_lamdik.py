"""Update akreditasi program studi dari data LAMDIK
- Hanya memproses prodi yang masih akreditasi='belum'
- Match berdasarkan: nama PT (via banpt_pt mapping) + nama prodi + jenjang
- Source: utils/ext/lamdik_prodi.json
"""

import html as html_module
import json
import os
import re
from collections import defaultdict
from difflib import SequenceMatcher

import MySQLdb
from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = dotenv_values(os.path.join(BASE_DIR, ".env"))

LAMDIK_FILE  = os.path.join(BASE_DIR, "utils/ext/lamdik_prodi.json")

PERINGKAT_MAP = {
    "unggul":                "unggul",
    "a":                     "unggul",
    "terakreditasi unggul":  "unggul",
    "baik sekali":           "baik_sekali",
    "b":                     "baik_sekali",
    "baik":                  "baik",
    "terakreditasi":         "baik",
    "terakreditasi pertama": "baik",
    "terakreditasi sementara": "baik",
    "c":                     "c",
    "tmsp":                  "belum",
    "tidak terakreditasi":   "belum",
}

JENJANG_LAMDIK_MAP = {
    "s1": "s1", "s2": "s2", "s3": "s3",
    "profesi": "profesi",
    "d4": "d4",
}


def norm(s):
    s = re.sub(r"[.]", "", html_module.unescape(s))
    return re.sub(r"\s+", " ", s.upper().strip())


def strip_city(name):
    m = re.search(r",\s+[A-Z][A-Z\s]+$", name)
    return name[: m.start()].strip() if m else name


def map_peringkat(raw):
    return PERINGKAT_MAP.get((raw or "").strip().lower(), "belum")


def build_index(lamdik_data):
    """Index: nama_pt_norm → list of records."""
    idx = defaultdict(list)
    for r in lamdik_data:
        key = norm(r["nama_pt"])
        idx[key].append(r)
        alt = strip_city(key)
        if alt != key:
            idx[alt].append(r)
    return idx


def find_match(nama_prodi_db, jenjang_db, candidates):
    """Cari exact match (nama + jenjang), return record atau None."""
    norm_target = norm(nama_prodi_db)
    jenjang_db_norm = jenjang_db.lower()

    for rec in candidates:
        jenjang_rec = JENJANG_LAMDIK_MAP.get(rec["jenjang"].lower())
        if norm(rec["nama_prodi"]) == norm_target and jenjang_rec == jenjang_db_norm:
            return rec
    return None


def main():
    with open(LAMDIK_FILE, encoding="utf-8") as f:
        lamdik = json.load(f)

    idx = build_index(lamdik)

    db = MySQLdb.connect(
        host=env["DB_HOST"], user=env["DB_USER"],
        passwd=env["DB_PASSWORD"], db=env["DB_NAME"],
        port=int(env["DB_PORT"]), charset="utf8mb4",
    )
    cur = db.cursor()

    cur.execute("""
        SELECT ps.id, ps.nama, ps.jenjang, pt.nama
        FROM universities_programstudi ps
        JOIN universities_perguruantinggi pt ON pt.id = ps.perguruan_tinggi_id
        WHERE ps.akreditasi = 'belum'
        ORDER BY pt.nama, ps.nama
    """)
    rows = cur.fetchall()
    print(f"Prodi belum: {len(rows)}")

    update_rows = []
    exact = pt_skip = not_found = 0

    for ps_id, nama, jenjang, nama_pt_db in rows:
        candidates = idx.get(norm(nama_pt_db), [])
        if not candidates:
            not_found += 1
            continue

        rec = find_match(nama, jenjang, candidates)
        if rec:
            ak = map_peringkat(rec["peringkat"])
            update_rows.append((ak, rec["nomor_sk"], rec["tgl_expired"], ps_id))
            exact += 1
        else:
            not_found += 1

    if update_rows:
        cur.executemany(
            """UPDATE universities_programstudi
               SET akreditasi=%s, no_sk_akreditasi=%s, tanggal_kedaluarsa_akreditasi=%s
               WHERE id=%s""",
            update_rows,
        )
    db.commit()
    db.close()

    print(f"=== Selesai ===")
    print(f"Exact updated  : {exact}")
    print(f"Tidak ditemukan: {not_found}")
    print(f"PT skip        : {pt_skip}")
    print(f"Total diproses : {len(rows)}")


if __name__ == "__main__":
    main()
