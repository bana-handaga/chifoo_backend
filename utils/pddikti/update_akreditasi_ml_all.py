"""Update akreditasi prodi menggunakan TF-IDF cosine similarity dari semua sumber LAM + BAN-PT.
- Hanya prodi akreditasi='belum'
- Match: nama PT (exact/strip-city) + nama prodi TF-IDF + jenjang exact
- Sources: lamdik, lamptkes, laminfokom, lamsama, lamspak, lamteknik, lamemba, banpt_prodi
- Threshold >= 0.90 → update langsung; 0.70-0.89 → tampilkan untuk review
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

THRESHOLD_AUTO   = 0.90
THRESHOLD_REVIEW = 0.70

# ─── Jenjang normalization ────────────────────────────────────────────────────

JENJANG_NORM = {
    # short codes
    "s1": "s1", "s2": "s2", "s3": "s3",
    "d1": "d1", "d2": "d2", "d3": "d3", "d4": "d4",
    "profesi": "profesi",
    # long Indonesian forms (LAM-PTKes, LAM Teknik)
    "sarjana": "s1", "sarjana pendidikan": "s1",
    "sarjana terapan": "d4", "diploma empat": "d4", "diploma empat pendidik": "d4",
    "diploma satu": "d1", "diploma dua": "d2", "diploma tiga": "d3",
    "magister": "s2", "magister terapan": "s2",
    "doktor": "s3", "doktor terapan": "s3",
    "pendidikan profesi": "profesi", "profesi dokter": "profesi",
    "spesialis": "Sp-1", "sub spesialis": "Sp-1", "subspesialis": "Sp-1",
    # BAN-PT variants
    "d-i": "d1", "d-ii": "d2", "d-iii": "d3", "d-iv": "d4",
    "diploma-iii": "d3",
    "s1 terapan": "d4", "s2 terapan": "s2", "s3 terapan": "s3",
    "pro.": "profesi",
}

PERINGKAT_MAP = {
    "unggul": "unggul", "terakreditasi unggul": "unggul", "a": "unggul",
    "baik sekali": "baik_sekali", "b": "baik_sekali",
    "baik": "baik", "terakreditasi": "baik",
    "terakreditasi pertama": "baik", "terakreditasi sementara": "baik",
    "akreditasi pertama": "baik",
    "c": "c",
    "tmsp": "belum", "tidak terakreditasi": "belum",
    "tidak memenuhi syarat peringkat (tmsp)": "belum",
}


def norm(s):
    s = re.sub(r"[.]", "", html_module.unescape(s))
    return re.sub(r"\s+", " ", s.upper().strip())


def strip_city(name):
    m = re.search(r",\s+[A-Z][A-Z\s]+$", name)
    return name[: m.start()].strip() if m else name


def norm_prodi(s):
    """Normalize prodi name: strip common level/program prefixes."""
    s = norm(s)
    s = re.sub(r"^PROGRAM\s+", "", s)           # 'Program Profesi Insinyur' → 'Profesi Insinyur'
    s = re.sub(r"^PENDIDIKAN PROFESI\s+", "", s) # 'Pendidikan Profesi Dokter' → 'Dokter'
    s = re.sub(r"^PROFESI\s+", "", s)            # 'Profesi Ners' / 'Profesi Dokter' → 'Ners' / 'Dokter'
    s = re.sub(r"^MAGISTER\s+", "", s)           # 'Magister Keperawatan' → 'Keperawatan'
    return s


def jnorm(raw):
    return JENJANG_NORM.get((raw or "").strip().lower())


def parse_date(s):
    if not s:
        return None
    m = re.match(r"(\d{2})-(\d{2})-(\d{4})", s)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else s


def map_peringkat(raw):
    return PERINGKAT_MAP.get((raw or "").strip().lower(), "belum")


# ─── Load & normalize all sources ────────────────────────────────────────────

def load_source(path, date_fn=None):
    with open(os.path.join(BASE_DIR, path), encoding="utf-8") as f:
        return json.load(f)


def build_combined_index():
    """Returns idx: norm_pt_name → list of unified records."""
    idx = defaultdict(list)

    def add(records, source, tgl_fn=None):
        for r in records:
            rec = {
                "source":    source,
                "nama_pt":   r.get("nama_pt", ""),
                "nama_prodi": r.get("nama_prodi", ""),
                "jenjang":   jnorm(r.get("jenjang", "")),
                "peringkat": map_peringkat(r.get("peringkat", "")),
                "nomor_sk":  r.get("nomor_sk", ""),
                "tgl_expired": tgl_fn(r.get("tgl_expired", "")) if tgl_fn else r.get("tgl_expired", ""),
            }
            if rec["jenjang"] is None:
                continue
            key = norm(rec["nama_pt"])
            idx[key].append(rec)
            alt = strip_city(key)
            if alt != key:
                idx[alt].append(rec)

    add(load_source("utils/ext/lamdik_prodi.json"),     "lamdik")
    add(load_source("utils/ext/lamptkes_prodi.json"),   "lamptkes")
    add(load_source("utils/ext/laminfokom_prodi.json"), "laminfokom")
    add(load_source("utils/ext/lamsama_prodi.json"),    "lamsama")
    add(load_source("utils/ext/lamspak_prodi.json"),    "lamspak")
    add(load_source("utils/ext/lamteknik_prodi.json"),  "lamteknik",  tgl_fn=parse_date)
    add(load_source("utils/ext/lamemba_prodi.json"),    "lamemba")
    add(load_source("utils/ext/banpt_prodi_akreditasi.json"), "banpt")

    return idx


# ─── TF-IDF matching ─────────────────────────────────────────────────────────

def best_tfidf(nama_db, jenjang_db, candidates, vectorizer):
    jdb = jenjang_db.lower() if jenjang_db not in ("Sp-1",) else jenjang_db
    filtered = [r for r in candidates if r["jenjang"] == jenjang_db]
    if not filtered:
        return None, 0.0

    # Use norm_prodi to strip PSKGJ/Program prefixes for query
    lam_names = [norm_prodi(r["nama_prodi"]).lower() for r in filtered]
    query     = norm_prodi(nama_db).lower()

    try:
        all_vecs = vectorizer.transform([query] + lam_names)
        scores   = cosine_similarity(all_vecs[0], all_vecs[1:])[0]
        best_i   = int(np.argmax(scores))
        best_rec = filtered[best_i]
        score    = float(scores[best_i])

        # Penalti: nama LAM jauh lebih pendek dari nama DB (setelah strip prefix)
        lam_words = norm_prodi(best_rec["nama_prodi"]).split()
        db_words  = norm_prodi(nama_db).split()
        if len(db_words) > 0 and len(lam_words) > 0:
            ratio = len(lam_words) / len(db_words)
            if ratio < 0.6:
                score *= ratio

        # Penalti: kata kunci diskriminatif beda (e.g. "Dokter" vs "Guru", "Bidan" vs "Guru")
        lam_set = set(norm_prodi(best_rec["nama_prodi"]).split())
        db_set  = set(norm_prodi(nama_db).split())
        discriminative = {"DOKTER", "GURU", "BIDAN", "APOTEKER", "INSINYUR",
                          "DOKTER HEWAN", "AKUNTAN", "HAKIM"}
        lam_disc = lam_set & discriminative
        db_disc  = db_set  & discriminative
        if lam_disc and db_disc and lam_disc != db_disc:
            score *= 0.5  # Kata kunci profesi berbeda → hampir pasti salah match

        return best_rec, score
    except Exception:
        return None, 0.0


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    idx = build_combined_index()

    # Fit TF-IDF on all prodi names across all sources
    all_names = []
    for recs in idx.values():
        for r in recs:
            all_names.append(norm_prodi(r["nama_prodi"]).lower())
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    vectorizer.fit(list(set(all_names)))

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

    auto_rows   = []
    review_rows = []
    not_found = low_score = 0

    pskgj_skip = 0
    for ps_id, nama, jenjang, nama_pt_db in rows:
        if nama.upper().startswith("PSKGJ"):
            pskgj_skip += 1
            continue

        candidates = idx.get(norm(nama_pt_db), [])
        if not candidates:
            not_found += 1
            continue

        rec, score = best_tfidf(nama, jenjang, candidates, vectorizer)

        if rec is None or score < THRESHOLD_REVIEW:
            low_score += 1
            continue

        row = (rec["peringkat"], rec["nomor_sk"], rec["tgl_expired"], ps_id)

        if score >= THRESHOLD_AUTO:
            auto_rows.append((score, nama, jenjang, nama_pt_db, rec, row))
        else:
            review_rows.append((score, nama, jenjang, nama_pt_db, rec, row))

    # ─ Auto update ────────────────────────────────────────────────────────────
    print(f"\n=== Auto update (score >= {THRESHOLD_AUTO}) : {len(auto_rows)} prodi ===")
    for score, nama_db, jenjang_db, nama_pt, rec, row in sorted(auto_rows, reverse=True):
        print(f"  {score:.4f}  {nama_pt[:35]:<35}  {nama_db:<35} ({jenjang_db})"
              f"  ->  {rec['nama_prodi']} [{rec['source']}] [{rec['peringkat']}]")

    if auto_rows:
        cur.executemany(
            """UPDATE universities_programstudi
               SET akreditasi=%s, no_sk_akreditasi=%s, tanggal_kedaluarsa_akreditasi=%s
               WHERE id=%s""",
            [r[-1] for r in auto_rows],
        )

    # ─ Review rows ────────────────────────────────────────────────────────────
    print(f"\n=== Perlu review ({THRESHOLD_REVIEW}–{THRESHOLD_AUTO}) : {len(review_rows)} prodi ===")
    for score, nama_db, jenjang_db, nama_pt, rec, row in sorted(review_rows, reverse=True):
        print(f"  {score:.4f}  {nama_pt[:35]:<35}  {nama_db:<35} ({jenjang_db})"
              f"  ->  {rec['nama_prodi']} [{rec['source']}] [{rec['peringkat']}]")

    db.commit()
    db.close()

    print(f"\n=== Selesai ===")
    print(f"Auto updated   : {len(auto_rows)}")
    print(f"Perlu review   : {len(review_rows)}")
    print(f"Score rendah   : {low_score}")
    print(f"PT tidak ada   : {not_found}")
    print(f"PSKGJ skip     : {pskgj_skip}")
    print(f"Total diproses : {len(rows)}")


if __name__ == "__main__":
    main()
