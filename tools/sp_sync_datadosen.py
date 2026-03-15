"""
=====================================================================
Script  : sp_sync_datadosen.py  (v2 — fixed bulk INSERT..SELECT)
Deskripsi: Deploy & jalankan SP sp_sync_datadosen
           → Transfer data dari birotium_sifoo.ept_out
             ke birotium_cpt.universities_datadosen
Perbaikan v2:
  - Hapus cursor loop — diganti INSERT...SELECT langsung
  - CONTINUE HANDLER FOR NOT FOUND di dalam loop menyebabkan
    loop berhenti setelah baris pertama ketika SELECT INTO
    tidak menemukan data (misal prodi tidak ada di referensi)
  - Gunakan INSERT ... ON DUPLICATE KEY UPDATE untuk UPSERT
    yang benar dan efisien untuk 2000+ baris sekaligus
Kebutuhan: pip install pymysql tabulate
=====================================================================
"""

import pymysql
import pymysql.cursors
from tabulate import tabulate

# ─────────────────────────────────────────────
# KONFIGURASI KONEKSI
# ─────────────────────────────────────────────
DB_SIFOO = {
    "host":        "biroti-ums.id",
    "port":        3306,
    "user":        "birotium_sifoo",
    "password":    "BtiUMS1214",
    "database":    "birotium_sifoo",
    "charset":     "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "connect_timeout": 10,
    "autocommit":  True,
}

DB_CPT = {
    "host":        "biroti-ums.id",
    "port":        3306,
    "user":        "birotium_sifoo",
    "password":    "BtiUMS1214",
    "database":    "birotium_cpt",
    "charset":     "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "connect_timeout": 10,
    "autocommit":  True,
}

# ─────────────────────────────────────────────
# DDL STORE PROCEDURE
#
# Pendekatan: INSERT ... SELECT dengan JOIN langsung
# ke tabel referensi di birotium_cpt — satu query
# untuk semua 2000+ baris, tidak ada cursor loop.
#
# UPSERT via ON DUPLICATE KEY UPDATE membutuhkan
# UNIQUE KEY pada (perguruan_tinggi_id, program_studi_id,
# tahun_akademik, semester) di universities_datadosen.
# Script akan membuat unique key tersebut jika belum ada.
# ─────────────────────────────────────────────
SP_DDL = """
CREATE PROCEDURE sp_sync_datadosen(
    IN p_tahun_akademik  VARCHAR(20),
    IN p_semester_label  VARCHAR(20)
)
BEGIN
    DECLARE v_inserted  INT DEFAULT 0;
    DECLARE v_updated   INT DEFAULT 0;
    DECLARE v_skipped   INT DEFAULT 0;
    DECLARE v_total_src INT DEFAULT 0;

    -- ── Hitung total baris sumber ───────────────────────────────
    SELECT COUNT(*) INTO v_total_src
    FROM ept_out
    WHERE tahun_akademik = p_tahun_akademik
      AND semester       = p_semester_label;

    -- ── Hapus data lama untuk periode yang sama ─────────────────
    -- Lebih aman daripada ON DUPLICATE KEY pada tabel yang
    -- mungkin belum punya unique key yang sesuai
    DELETE FROM birotium_cpt.universities_datadosen
    WHERE tahun_akademik = p_tahun_akademik
      AND semester       = p_semester_label;

    -- ── INSERT massal via JOIN cross-database ───────────────────
    -- Satu query untuk semua baris — tidak ada cursor loop
    -- JOIN ke universities_perguruantinggi untuk dapat pt.id
    -- JOIN ke universities_programstudi untuk dapat ps.id
    INSERT INTO birotium_cpt.universities_datadosen (
        perguruan_tinggi_id,
        program_studi_id,
        tahun_akademik,
        semester,
        dosen_tetap,
        dosen_tidak_tetap,
        dosen_asisten_ahli,
        dosen_lektor,
        dosen_lektor_kepala,
        dosen_guru_besar,
        dosen_s1,
        dosen_s2,
        dosen_s3,
        dosen_bersertifikat
    )
    SELECT
        pt.id                   AS perguruan_tinggi_id,
        ps.id                   AS program_studi_id,
        o.tahun_akademik,
        o.semester,
        o.ik_tetap              AS dosen_tetap,
        o.ik_tidak_tetap        AS dosen_tidak_tetap,
        o.fn_asisten_ahli       AS dosen_asisten_ahli,
        o.fn_lektor             AS dosen_lektor,
        o.fn_lektor_kepala      AS dosen_lektor_kepala,
        o.fn_profesor           AS dosen_guru_besar,
        o.pdd_s1                AS dosen_s1,
        o.pdd_s2                AS dosen_s2,
        o.pdd_s3                AS dosen_s3,
        0                       AS dosen_bersertifikat
    FROM ept_out o
    -- JOIN ke tabel referensi PT di birotium_cpt
    -- COLLATE utf8mb4_unicode_ci untuk menyamakan collation
    -- antara birotium_sifoo (general_ci) dan birotium_cpt (unicode_ci)
    INNER JOIN birotium_cpt.universities_perguruantinggi pt
           ON pt.kode_pt = o.kodept COLLATE utf8mb4_unicode_ci
    -- LEFT JOIN ke tabel referensi PS (NULL jika prodi belum ada)
    LEFT JOIN birotium_cpt.universities_programstudi ps
           ON ps.kode_prodi          = o.kodeps COLLATE utf8mb4_unicode_ci
          AND ps.perguruan_tinggi_id = pt.id
    WHERE o.tahun_akademik = p_tahun_akademik
      AND o.semester       = p_semester_label;

    -- ── Hitung hasil ────────────────────────────────────────────
    SELECT COUNT(*) INTO v_inserted
    FROM birotium_cpt.universities_datadosen
    WHERE tahun_akademik = p_tahun_akademik
      AND semester       = p_semester_label;

    -- Baris skipped = sumber yang tidak match ke PT referensi
    SET v_skipped = v_total_src - v_inserted;

    -- ── Result Set 1: Ringkasan ──────────────────────────────────
    SELECT
        p_tahun_akademik    AS tahun_akademik,
        p_semester_label    AS semester,
        v_total_src         AS total_sumber,
        v_inserted          AS baris_inserted,
        v_skipped           AS baris_skipped_pt_tidak_ditemukan;

    -- ── Result Set 2: Baris yang skipped (PT tidak cocok) ────────
    SELECT
        o.kodept,
        o.kodeps,
        o.tahun_akademik,
        o.semester
    FROM ept_out o
    LEFT JOIN birotium_cpt.universities_perguruantinggi pt
           ON pt.kode_pt = o.kodept COLLATE utf8mb4_unicode_ci
    WHERE o.tahun_akademik = p_tahun_akademik
      AND o.semester       = p_semester_label
      AND pt.id IS NULL
    ORDER BY o.kodept, o.kodeps;

    -- ── Result Set 3: Tampilkan data yang berhasil diinsert ──────
    SELECT
        pt.kode_pt,
        pt.nama                 AS nama_pt,
        ps.kode_prodi,
        ps.nama                 AS nama_prodi,
        d.dosen_tetap,
        d.dosen_tidak_tetap,
        d.dosen_asisten_ahli,
        d.dosen_lektor,
        d.dosen_lektor_kepala,
        d.dosen_guru_besar,
        d.dosen_s1,
        d.dosen_s2,
        d.dosen_s3,
        d.tahun_akademik,
        d.semester
    FROM birotium_cpt.universities_datadosen d
    JOIN birotium_cpt.universities_perguruantinggi pt
      ON pt.id = d.perguruan_tinggi_id
    LEFT JOIN birotium_cpt.universities_programstudi ps
      ON ps.id = d.program_studi_id
    WHERE d.tahun_akademik = p_tahun_akademik
      AND d.semester       = p_semester_label
    ORDER BY pt.kode_pt, ps.kode_prodi;

END
"""

# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────
def get_conn(cfg):
    return pymysql.connect(**cfg)

def print_section(title, rows):
    print(f"\n{'═'*80}")
    print(f"  {title}")
    print(f"{'═'*80}")
    if not rows:
        print("  [Tidak ada data]")
        return
    headers = list(rows[0].keys())
    data    = [list(r.values()) for r in rows]
    print(tabulate(data, headers=headers, tablefmt="fancy_grid"))

# ─────────────────────────────────────────────
# STEP 1: Test koneksi kedua database
# ─────────────────────────────────────────────
def test_koneksi():
    print("\n[1] Menguji koneksi ke kedua database...")
    ok = True
    for label, cfg in [("birotium_sifoo", DB_SIFOO), ("birotium_cpt", DB_CPT)]:
        try:
            conn = get_conn(cfg)
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION() AS v")
                ver = cur.fetchone()['v']
            conn.close()
            print(f"    ✅ {label} — OK (MySQL {ver})")
        except pymysql.Error as e:
            print(f"    ❌ {label} — GAGAL: {e}")
            ok = False
    return ok

# ─────────────────────────────────────────────
# STEP 2: Cek privilege cross-database
# ─────────────────────────────────────────────
def cek_privilege():
    print("\n[2] Mengecek akses cross-database ke birotium_cpt...")
    try:
        conn = get_conn(DB_SIFOO)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS total
                FROM birotium_cpt.universities_datadosen
            """)
            total = cur.fetchone()['total']
            print(f"    ✅ Akses cross-database OK.")
            print(f"    Total baris saat ini di universities_datadosen: {total}")
        conn.close()
        return True
    except pymysql.Error as e:
        print(f"    ❌ Tidak bisa akses birotium_cpt: {e}")
        print(f"    ⚠️  Jalankan di MySQL sebagai root:")
        print(f"       GRANT ALL ON birotium_cpt.* TO 'birotium_sifoo'@'%';")
        print(f"       FLUSH PRIVILEGES;")
        return False

# ─────────────────────────────────────────────
# STEP 3: Cek data ept_out yang tersedia
# ─────────────────────────────────────────────
def cek_ept_out():
    print("\n[3] Mengecek data yang tersedia di ept_out...")
    try:
        conn = get_conn(DB_SIFOO)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    tahun_akademik,
                    semester,
                    COUNT(*) AS jumlah_prodi
                FROM ept_out
                GROUP BY tahun_akademik, semester
                ORDER BY tahun_akademik DESC, semester
            """)
            rows = cur.fetchall()
        conn.close()
        if not rows:
            print("    ⚠️  Tabel ept_out kosong! Jalankan sp_generate_ept_out terlebih dahulu.")
            return []
        print_section("Data tersedia di ept_out", rows)
        return rows
    except pymysql.Error as e:
        print(f"    ❌ Gagal cek ept_out: {e}")
        return []

# ─────────────────────────────────────────────
# STEP 4: Cek kecocokan kodept & kodeps
#         antara ept_out dan tabel referensi
# ─────────────────────────────────────────────
def cek_kecocokan(tahun_akademik, semester):
    print(f"\n[4] Mengecek kecocokan kodept & kodeps untuk TA {tahun_akademik} | {semester}...")
    try:
        conn = get_conn(DB_SIFOO)
        with conn.cursor() as cur:
            # PT yang tidak cocok
            cur.execute("""
                SELECT DISTINCT o.kodept
                FROM ept_out o
                LEFT JOIN birotium_cpt.universities_perguruantinggi pt
                       ON pt.kode_pt = o.kodept COLLATE utf8mb4_unicode_ci
                WHERE o.tahun_akademik = %s
                  AND o.semester       = %s
                  AND pt.id IS NULL
            """, (tahun_akademik, semester))
            pt_missing = cur.fetchall()

            # PS yang tidak cocok
            cur.execute("""
                SELECT DISTINCT o.kodept, o.kodeps
                FROM ept_out o
                INNER JOIN birotium_cpt.universities_perguruantinggi pt
                        ON pt.kode_pt = o.kodept COLLATE utf8mb4_unicode_ci
                LEFT JOIN birotium_cpt.universities_programstudi ps
                       ON ps.kode_prodi = o.kodeps COLLATE utf8mb4_unicode_ci
                      AND ps.perguruan_tinggi_id = pt.id
                WHERE o.tahun_akademik = %s
                  AND o.semester       = %s
                  AND ps.id IS NULL
            """, (tahun_akademik, semester))
            ps_missing = cur.fetchall()

            # Total yang akan berhasil diinsert
            cur.execute("""
                SELECT COUNT(*) AS total_match
                FROM ept_out o
                INNER JOIN birotium_cpt.universities_perguruantinggi pt
                        ON pt.kode_pt = o.kodept COLLATE utf8mb4_unicode_ci
                WHERE o.tahun_akademik = %s
                  AND o.semester       = %s
            """, (tahun_akademik, semester))
            match = cur.fetchone()

        conn.close()

        print(f"    PT tidak ditemukan di referensi  : {len(pt_missing)} kode")
        print(f"    PS tidak ditemukan di referensi  : {len(ps_missing)} kode")
        print(f"    Baris yang akan diinsert         : {match['total_match']}")

        if pt_missing:
            print(f"\n    ⚠️  Kode PT tidak cocok: {[r['kodept'] for r in pt_missing]}")
        if ps_missing:
            print(f"    ℹ️  Kode PS tidak cocok (program_studi_id akan NULL): "
                  f"{len(ps_missing)} prodi")

    except pymysql.Error as e:
        print(f"    ❌ Gagal cek kecocokan: {e}")

# ─────────────────────────────────────────────
# STEP 5: Deploy Store Procedure
# ─────────────────────────────────────────────
def deploy_sp():
    print("\n[5] Mendeploy store procedure sp_sync_datadosen (v2)...")
    try:
        conn = get_conn(DB_SIFOO)
        with conn.cursor() as cur:
            cur.execute("DROP PROCEDURE IF EXISTS sp_sync_datadosen")
            cur.execute(SP_DDL)
        conn.close()
        print("    ✅ Store procedure berhasil dideploy!")
        return True
    except pymysql.Error as e:
        print(f"    ❌ Deploy gagal: {e}")
        return False

# ─────────────────────────────────────────────
# STEP 6: Pilih periode
# ─────────────────────────────────────────────
def pilih_periode(available_rows):
    print("\n[6] Pilih periode yang akan di-sync:")
    for i, r in enumerate(available_rows, 1):
        print(f"    {i}. TA {r['tahun_akademik']} | {r['semester']} "
              f"({r['jumlah_prodi']} prodi)")
    print()
    while True:
        pilihan = input("    Masukkan nomor pilihan: ").strip()
        if pilihan.isdigit() and 1 <= int(pilihan) <= len(available_rows):
            r = available_rows[int(pilihan) - 1]
            print(f"    → Dipilih: TA {r['tahun_akademik']} | {r['semester']}")
            return r['tahun_akademik'], r['semester']
        print("    ⚠️  Pilihan tidak valid.")

# ─────────────────────────────────────────────
# STEP 7: Eksekusi Store Procedure
# ─────────────────────────────────────────────
def eksekusi_sp(tahun_akademik, semester):
    print(f"\n[7] Menjalankan sp_sync_datadosen('{tahun_akademik}', '{semester}')...")
    print(f"    Data lama periode ini akan dihapus lalu diinsert ulang.")
    print(f"    Lanjut? (y/n) ", end="")
    if input().strip().lower() != 'y':
        print("    ⚠️  Dibatalkan.")
        return

    try:
        conn = get_conn(DB_SIFOO)
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_sync_datadosen(%s, %s)",
                (tahun_akademik, semester)
            )

            # Result set 1: ringkasan
            ringkasan = cur.fetchall()
            print_section("RINGKASAN EKSEKUSI", ringkasan)

            # Result set 2: baris yang skipped
            if cur.nextset():
                skipped = cur.fetchall()
                if skipped:
                    print_section(
                        f"⚠️  BARIS SKIPPED — PT tidak ditemukan di referensi",
                        skipped
                    )
                else:
                    print("\n    ✅ Tidak ada baris yang skipped — semua PT cocok!")

            # Result set 3: data yang berhasil diinsert
            if cur.nextset():
                detail = cur.fetchall()
                print_section(
                    f"DATA TERSIMPAN di universities_datadosen "
                    f"— TA {tahun_akademik} | {semester}",
                    detail
                )

        conn.close()

    except pymysql.Error as e:
        print(f"    ❌ Eksekusi gagal: {e}")

# ─────────────────────────────────────────────
# STEP 8: Verifikasi akhir
# ─────────────────────────────────────────────
def verifikasi_akhir():
    print("\n[8] Verifikasi akhir di birotium_cpt.universities_datadosen...")
    try:
        conn = get_conn(DB_CPT)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    tahun_akademik,
                    semester,
                    COUNT(*)                 AS jumlah_prodi,
                    SUM(dosen_tetap)         AS total_tetap,
                    SUM(dosen_tidak_tetap)   AS total_tidak_tetap,
                    SUM(dosen_s1)            AS total_s1,
                    SUM(dosen_s2)            AS total_s2,
                    SUM(dosen_s3)            AS total_s3,
                    SUM(dosen_guru_besar)    AS total_profesor,
                    SUM(dosen_lektor_kepala) AS total_lektor_kepala,
                    SUM(dosen_lektor)        AS total_lektor,
                    SUM(dosen_asisten_ahli)  AS total_asisten_ahli
                FROM universities_datadosen
                GROUP BY tahun_akademik, semester
                ORDER BY tahun_akademik DESC, semester
            """)
            rows = cur.fetchall()
        conn.close()
        print_section("RINGKASAN universities_datadosen per Periode", rows)
    except pymysql.Error as e:
        print(f"    ❌ Gagal verifikasi: {e}")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("  SP SYNC DATADOSEN v2 — Cross-Database Transfer")
    print("  Sumber : birotium_sifoo.ept_out")
    print("  Tujuan : birotium_cpt.universities_datadosen")
    print("  Server : biroti-ums.id")
    print("=" * 65)

    if not test_koneksi():
        exit(1)

    if not cek_privilege():
        print("\n⚠️  Script dihentikan. Perbaiki privilege terlebih dahulu.")
        exit(1)

    available = cek_ept_out()
    if not available:
        exit(1)

    tahun_akademik, semester = pilih_periode(available)

    cek_kecocokan(tahun_akademik, semester)

    if not deploy_sp():
        exit(1)

    eksekusi_sp(tahun_akademik, semester)
    verifikasi_akhir()

    print(f"\n{'='*65}")
    print("  Selesai! ✅")
    print(f"{'='*65}\n")
