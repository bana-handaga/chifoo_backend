"""Update akreditasi prodi dari LAM-PTKes menggunakan TF-IDF cosine similarity.
- Hanya prodi akreditasi='belum'
- Match: nama PT exact + (nama prodi + jenjang) via TF-IDF cosine similarity
- Threshold 0.70 — konfirmasi manual disarankan untuk score < 0.90
"""

import html as html_module
import json
import os
import re
from collections import defaultdict

import MySQLdb
import numpy as np
from dotenv import dotenv_values
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = dotenv_values(os.path.join(BASE_DIR, ".env"))

LAMPTKES_FILE = os.path.join(BASE_DIR, "utils/ext/lamptkes_prodi.json")

THRESHOLD_EXACT  = 0.90   # update langsung
THRESHOLD_REVIEW = 0.70   # update tapi catat untuk review

PERINGKAT_MAP = {
    "unggul":                "unggul",
    "a":                     "unggul",
    "baik sekali":           "baik_sekali",
    "b":                     "baik_sekali",
    "baik":                  "baik",
    "terakreditasi":         "baik",
    "terakreditasi pertama": "baik",
    "c":                     "c",
    "tidak terakreditasi":   "belum",
}

JENJANG_LAMPTKES_MAP = {
    "diploma satu": "d1", "diploma dua": "d2", "diploma tiga": "d3",
    "diploma empat": "d4", "diploma empat pendidik": "d4", "sarjana terapan": "d4",
    "sarjana": "s1", "sarjana pendidikan": "s1",
    "profesi": "profesi", "pendidikan profesi": "profesi", "profesi dokter": "profesi",
    "magister": "s2", "magister terapan": "s2", "doktor": "s3",
    "spesialis": "spesialis", "sub spesialis": "subspesialis",
}


def norm(s):
    s = re.sub(r"[.]", "", html_module.unescape(s))
    return re.sub(r"\s+", " ", s.upper().strip())


def strip_city(name):
    m = re.search(r",\s+[A-Z][A-Z\s]+$", name)
    return name[: m.start()].strip() if m else name


def build_pt_index(lamptkes):
    """Index: nama_pt_norm → list of records."""
    idx = defaultdict(list)
    for r in lamptkes:
        key = norm(r["nama_pt"])
        idx[key].append(r)
        alt = strip_city(key)
        if alt != key:
            idx[alt].append(r)
    return idx


def best_match_tfidf(nama_db, jenjang_db, candidates, vectorizer):
    """Cari best match dari candidates menggunakan cosine similarity.
    Hanya kandidat dengan jenjang cocok yang dipertimbangkan.
    """
    jdb = jenjang_db.lower()

    # Filter kandidat dengan jenjang cocok
    filtered = [
        rec for rec in candidates
        if JENJANG_LAMPTKES_MAP.get(rec["jenjang"].lower()) == jdb
    ]
    if not filtered:
        return None, 0.0

    lam_names = [norm(r["nama_prodi"]).lower() for r in filtered]
    query = norm(nama_db).lower()

    try:
        # Transform query dan candidates menggunakan vectorizer yang sudah di-fit
        all_vecs = vectorizer.transform([query] + lam_names)
        q_vec   = all_vecs[0]
        c_vecs  = all_vecs[1:]
        scores  = cosine_similarity(q_vec, c_vecs)[0]
        best_i  = int(np.argmax(scores))
        best_rec = filtered[best_i]
        best_score = float(scores[best_i])

        # Sanity check: penalti jika nama DB jauh lebih panjang dari nama LAM
        # (mencegah "KEDOKTERAN" match ke "KEDOKTERAN GIGI" di DB)
        lam_words = norm(best_rec["nama_prodi"]).split()
        db_words  = norm(nama_db).split()
        if len(db_words) > 0 and len(lam_words) > 0:
            len_ratio = len(lam_words) / len(db_words)
            if len_ratio < 0.6:  # LAM name jauh lebih pendek
                best_score *= len_ratio

        return best_rec, best_score
    except Exception:
        return None, 0.0


def main():
    with open(LAMPTKES_FILE, encoding="utf-8") as f:
        lamptkes = json.load(f)

    pt_idx = build_pt_index(lamptkes)

    # Fit TF-IDF pada semua nama prodi LAM-PTKes
    all_lam_names = [norm(r["nama_prodi"]).lower() for r in lamptkes]
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    vectorizer.fit(all_lam_names)

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
    review_rows = []
    not_found = low_score = 0

    for ps_id, nama, jenjang, nama_pt_db in rows:
        candidates = pt_idx.get(norm(nama_pt_db), [])
        if not candidates:
            not_found += 1
            continue

        rec, score = best_match_tfidf(nama, jenjang, candidates, vectorizer)

        if rec is None or score < THRESHOLD_REVIEW:
            low_score += 1
            continue

        ak = PERINGKAT_MAP.get(rec["peringkat"].strip().lower(), "belum")
        row = (ak, rec["nomor_sk"], rec["tgl_expired"], ps_id)

        if score >= THRESHOLD_EXACT:
            update_rows.append(row)
        else:
            review_rows.append((score, nama, jenjang, nama_pt_db, rec["nama_prodi"], rec["jenjang"], ak, row))

    # Update high-confidence
    if update_rows:
        cur.executemany(
            """UPDATE universities_programstudi
               SET akreditasi=%s, no_sk_akreditasi=%s, tanggal_kedaluarsa_akreditasi=%s
               WHERE id=%s""",
            update_rows,
        )

    # Update review (score 0.70–0.89) — tampilkan dulu
    print(f"\n=== High confidence (>= {THRESHOLD_EXACT}) — langsung update ===")
    print(f"  {len(update_rows)} prodi")

    print(f"\n=== Perlu review ({THRESHOLD_REVIEW}–{THRESHOLD_EXACT}) ===")
    for score, nama_db, jenjang_db, nama_pt, nama_lam, jenjang_lam, ak, row in sorted(review_rows, reverse=True):
        print(f"  {score:.4f}  {nama_pt[:35]:<35}  {nama_db:<35} ({jenjang_db}) -> {nama_lam} ({jenjang_lam}) [{ak}]")

    # Tanya apakah update review juga — untuk script ini langsung update semua
    if review_rows:
        review_db_rows = [r[-1] for r in review_rows]
        cur.executemany(
            """UPDATE universities_programstudi
               SET akreditasi=%s, no_sk_akreditasi=%s, tanggal_kedaluarsa_akreditasi=%s
               WHERE id=%s""",
            review_db_rows,
        )

    db.commit()
    db.close()

    print(f"\n=== Selesai ===")
    print(f"High-conf updated : {len(update_rows)}")
    print(f"Review updated    : {len(review_rows)}")
    print(f"Score terlalu rendah: {low_score}")
    print(f"PT tidak ditemukan: {not_found}")
    print(f"Total diproses    : {len(rows)}")


if __name__ == "__main__":
    main()
