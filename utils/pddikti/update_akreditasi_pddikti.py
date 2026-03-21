"""Update akreditasi prodi dari data PDDIKTI (utils/outs/*_detailprodi.json).
- Cocokkan via kode_pt (folder) + kode_ps (file) ke DB
- Akreditasi '-' → skip (belum / perlu cari ke sumber lain)
- Hanya update prodi yang masih akreditasi='belum' di DB
"""

import glob
import json
import os

import MySQLdb
from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = dotenv_values(os.path.join(BASE_DIR, ".env"))
OUTS_DIR = os.path.join(BASE_DIR, "utils/outs")

PERINGKAT_MAP = {
    "unggul":                  "unggul",
    "terakreditasi unggul":    "unggul",
    "a":                       "unggul",
    "baik sekali":             "baik_sekali",
    "b":                       "baik_sekali",
    "baik":                    "baik",
    "terakreditasi":           "baik",
    "terakreditasi pertama":   "baik",
    "terakreditasi sementara": "baik",
    "c":                       "c",
}


def main():
    db = MySQLdb.connect(
        host=env["DB_HOST"], user=env["DB_USER"],
        passwd=env["DB_PASSWORD"], db=env["DB_NAME"],
        port=int(env["DB_PORT"]), charset="utf8mb4",
    )
    cur = db.cursor()

    # Buat index DB: (kode_pt, kode_prodi) → ps.id
    cur.execute("""
        SELECT ps.id, pt.kode_pt, ps.kode_prodi, ps.akreditasi
        FROM universities_programstudi ps
        JOIN universities_perguruantinggi pt ON pt.id = ps.perguruan_tinggi_id
    """)
    db_index = {}
    for ps_id, kode_pt, kode_prodi, akreditasi in cur.fetchall():
        db_index[(kode_pt, kode_prodi)] = (ps_id, akreditasi)

    print(f"DB prodi total: {len(db_index)}")

    files = glob.glob(os.path.join(OUTS_DIR, "**", "*_detailprodi.json"), recursive=True)
    print(f"PDDIKTI files : {len(files)}")

    update_rows = []
    skipped_dash = skipped_already = not_in_db = unknown_peringkat = 0

    for fpath in files:
        try:
            data = json.load(open(fpath, encoding="utf-8"))
        except Exception:
            continue

        kode_pt = str(data.get("kode_pt", "")).strip()
        kode_ps = str(data.get("kode_ps", "")).strip()
        ak_raw  = data.get("profil", {}).get("Akreditasi", "-") or "-"

        if ak_raw.strip() == "-":
            skipped_dash += 1
            continue

        ak = PERINGKAT_MAP.get(ak_raw.strip().lower())
        if ak is None:
            unknown_peringkat += 1
            continue

        key = (kode_pt, kode_ps)
        if key not in db_index:
            not_in_db += 1
            continue

        ps_id, current_ak = db_index[key]
        if current_ak != "belum":
            skipped_already += 1
            continue

        update_rows.append((ak, ps_id))

    print(f"\nAkan diupdate   : {len(update_rows)}")
    print(f"Skip '-'        : {skipped_dash}")
    print(f"Skip sudah ada  : {skipped_already}")
    print(f"Tidak di DB     : {not_in_db}")
    print(f"Peringkat ???   : {unknown_peringkat}")

    if update_rows:
        cur.executemany(
            "UPDATE universities_programstudi SET akreditasi=%s WHERE id=%s",
            update_rows,
        )
    db.commit()
    db.close()

    print(f"\n=== Selesai: {len(update_rows)} prodi diupdate ===")


if __name__ == "__main__":
    main()
