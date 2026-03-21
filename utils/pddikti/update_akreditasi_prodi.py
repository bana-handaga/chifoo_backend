"""Update akreditasi program studi di tabel universities_programstudi
- match_method == 'exact'  → update dari data BAN-PT
- semua lainnya            → set akreditasi = 'belum'
"""

import json
import os
import MySQLdb
from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = dotenv_values(os.path.join(BASE_DIR, ".env"))

INPUT_FILE = os.path.join(BASE_DIR, "utils/outs/banpt_prodi.json")

PERINGKAT_MAP = {
    "unggul":               "unggul",
    "terakreditasi unggul": "unggul",
    "a":                    "unggul",
    "baik sekali":          "baik_sekali",
    "baik":                 "baik",
    "b":                    "baik_sekali",
    "terakreditasi":        "baik",
    "terakreditasi pertama":"baik",
    "terakreditasi sementara": "baik",
    "c":                    "c",
    "tidak terakreditasi":  "belum",
}

def map_peringkat(raw: str) -> str:
    if not raw:
        return "belum"
    return PERINGKAT_MAP.get(raw.strip().lower(), "belum")


def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    db = MySQLdb.connect(
        host=env["DB_HOST"], user=env["DB_USER"],
        passwd=env["DB_PASSWORD"], db=env["DB_NAME"],
        port=int(env["DB_PORT"]), charset="utf8mb4",
    )
    cur = db.cursor()

    # Ambil mapping kode_pt -> perguruan_tinggi_id
    cur.execute("SELECT kode_pt, id FROM universities_perguruantinggi")
    pt_id_map = {r[0]: r[1] for r in cur.fetchall()}

    # Ambil set (perguruan_tinggi_id, kode_prodi) yang valid
    cur.execute("SELECT perguruan_tinggi_id, kode_prodi FROM universities_programstudi")
    valid_pairs = {(r[0], r[1]) for r in cur.fetchall()}

    # (akreditasi, nomor_sk, tgl_expired, pt_id, kode_prodi)
    exact_rows = []
    # (pt_id, kode_prodi)
    belum_rows = []
    not_in_db  = 0

    for item in data:
        kode_prodi = item["kode_prodi"]
        kode_pt    = item.get("kode_pt", "")
        pt_id      = pt_id_map.get(kode_pt)

        if not pt_id or (pt_id, kode_prodi) not in valid_pairs:
            not_in_db += 1
            continue

        if item["match_method"] == "exact":
            exact_rows.append((
                map_peringkat(item.get("peringkat") or ""),
                item.get("nomor_sk") or "",
                item.get("tgl_expired"),
                pt_id,
                kode_prodi,
            ))
        else:
            belum_rows.append((pt_id, kode_prodi))

    if exact_rows:
        cur.executemany(
            """UPDATE universities_programstudi
               SET akreditasi=%s, no_sk_akreditasi=%s, tanggal_kedaluarsa_akreditasi=%s
               WHERE perguruan_tinggi_id=%s AND kode_prodi=%s""",
            exact_rows,
        )

    if belum_rows:
        cur.executemany(
            """UPDATE universities_programstudi
               SET akreditasi='belum', no_sk_akreditasi='', tanggal_kedaluarsa_akreditasi=NULL
               WHERE perguruan_tinggi_id=%s AND kode_prodi=%s""",
            belum_rows,
        )

    db.commit()
    db.close()

    print(f"Updated exact  : {len(exact_rows)}")
    print(f"Set belum      : {len(belum_rows)}")
    print(f"Not in DB      : {not_in_db}")
    print(f"Total          : {len(data)}")


if __name__ == "__main__":
    main()
