"""
=====================================================================
Script  : sp_generate_ept_out.py  (v3 — fixed commit & DDL)
Deskripsi: Deploy & jalankan SP sp_generate_ept_out
           → Membuat & mengisi tabel ept_out dari ept_htdd + ept_itps
Kebutuhan: pip install pymysql tabulate
Perbaikan:
  - autocommit=True agar INSERT di SP langsung tersimpan
  - CREATE TABLE dipisah ke luar SP (DDL tidak boleh di dalam SP
    yang menggunakan PREPARE/EXECUTE karena menyebabkan implicit commit)
  - Ganti callproc → execute("CALL ...") agar result set terbaca benar
=====================================================================
"""

import pymysql
import pymysql.cursors
from tabulate import tabulate

# ─────────────────────────────────────────────
# KONFIGURASI KONEKSI
# autocommit=True wajib agar INSERT dalam SP langsung di-commit
# ─────────────────────────────────────────────
DB_CONFIG = {
    "host":        "biroti-ums.id",
    "port":        3306,
    "user":        "birotium_sifoo",
    "password":    "BtiUMS1214",
    "database":    "birotium_sifoo",
    "charset":     "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "connect_timeout": 10,
    "autocommit":  True,       # ← KUNCI: tanpa ini INSERT tidak tersimpan
}

# ─────────────────────────────────────────────
# DDL: Buat tabel ept_out (dipisah dari SP)
# DDL tidak boleh di dalam SP yang pakai PREPARE/EXECUTE
# karena CREATE TABLE menyebabkan implicit commit di MySQL
# ─────────────────────────────────────────────
DDL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ept_out (
    id               BIGINT(20)  NOT NULL AUTO_INCREMENT,
    kodept           VARCHAR(20) NOT NULL,
    kodeps           VARCHAR(14) NOT NULL,
    ik_tetap         INT(11)     NOT NULL DEFAULT 0,
    ik_tidak_tetap   INT(11)     NOT NULL DEFAULT 0,
    fn_asisten_ahli  INT(11)     NOT NULL DEFAULT 0,
    fn_lektor        INT(11)     NOT NULL DEFAULT 0,
    fn_lektor_kepala INT(11)     NOT NULL DEFAULT 0,
    fn_profesor      INT(11)     NOT NULL DEFAULT 0,
    pdd_s1           INT(11)     NOT NULL DEFAULT 0,
    pdd_s2           INT(11)     NOT NULL DEFAULT 0,
    pdd_s3           INT(11)     NOT NULL DEFAULT 0,
    pdd_sp1          INT(11)     NOT NULL DEFAULT 0,
    pdd_sp2          INT(11)     NOT NULL DEFAULT 0,
    tahun_akademik   VARCHAR(20) NOT NULL,
    semester         VARCHAR(20) NOT NULL,
    created_at       DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ept_out (kodept, kodeps, tahun_akademik, semester)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

# ─────────────────────────────────────────────
# DDL STORE PROCEDURE
# CREATE TABLE sudah dipisah ke luar agar PREPARE/EXECUTE
# tidak terganggu oleh implicit commit dari DDL statement
# ─────────────────────────────────────────────
SP_DDL = """
CREATE PROCEDURE sp_generate_ept_out(
    IN p_semester_col    VARCHAR(10),
    IN p_tahun_akademik  VARCHAR(20),
    IN p_semester_label  VARCHAR(20)
)
BEGIN
    DECLARE v_col VARCHAR(12);
    SET v_col = CONCAT('S', p_semester_col);

    -- ────────────────────────────────────────
    -- STEP 1: Hapus data lama periode yang sama
    --         agar SP bisa dijalankan ulang
    -- ────────────────────────────────────────
    DELETE FROM ept_out
    WHERE tahun_akademik = p_tahun_akademik
      AND semester       = p_semester_label;

    -- ────────────────────────────────────────
    -- STEP 2: Insert agregasi via dynamic SQL
    --         (nama kolom semester bersifat dinamis)
    -- ────────────────────────────────────────
    SET @insert_sql = CONCAT('
        INSERT INTO ept_out (
            kodept, kodeps,
            ik_tetap, ik_tidak_tetap,
            fn_asisten_ahli, fn_lektor, fn_lektor_kepala, fn_profesor,
            pdd_s1, pdd_s2, pdd_s3, pdd_sp1, pdd_sp2,
            tahun_akademik, semester
        )
        SELECT
            ps.kodept,
            ps.kodeps,

            -- Ikatan Kerja: Tetap
            COALESCE(SUM(CASE
                WHEN LOWER(TRIM(d.ikatankerja)) LIKE ''%tetap%''
                 AND LOWER(TRIM(d.ikatankerja)) NOT LIKE ''%tidak%''
                THEN 1 ELSE 0 END), 0),

            -- Ikatan Kerja: Tidak Tetap
            COALESCE(SUM(CASE
                WHEN LOWER(TRIM(d.ikatankerja)) LIKE ''%tidak tetap%''
                THEN 1 ELSE 0 END), 0),

            -- Fungsional: Asisten Ahli
            COALESCE(SUM(CASE
                WHEN LOWER(TRIM(d.fungsional)) LIKE ''%asisten ahli%''
                THEN 1 ELSE 0 END), 0),

            -- Fungsional: Lektor (bukan Lektor Kepala)
            COALESCE(SUM(CASE
                WHEN LOWER(TRIM(d.fungsional)) LIKE ''%lektor%''
                 AND LOWER(TRIM(d.fungsional)) NOT LIKE ''%kepala%''
                THEN 1 ELSE 0 END), 0),

            -- Fungsional: Lektor Kepala
            COALESCE(SUM(CASE
                WHEN LOWER(TRIM(d.fungsional)) LIKE ''%lektor kepala%''
                THEN 1 ELSE 0 END), 0),

            -- Fungsional: Profesor / Guru Besar
            COALESCE(SUM(CASE
                WHEN LOWER(TRIM(d.fungsional)) LIKE ''%profesor%''
                  OR LOWER(TRIM(d.fungsional)) LIKE ''%guru besar%''
                THEN 1 ELSE 0 END), 0),

            -- Pendidikan: S1
            COALESCE(SUM(CASE
                WHEN LOWER(TRIM(d.pendidikan)) IN (''s1'',''s-1'',''sarjana'')
                THEN 1 ELSE 0 END), 0),

            -- Pendidikan: S2
            COALESCE(SUM(CASE
                WHEN LOWER(TRIM(d.pendidikan)) IN (''s2'',''s-2'',''magister'')
                THEN 1 ELSE 0 END), 0),

            -- Pendidikan: S3
            COALESCE(SUM(CASE
                WHEN LOWER(TRIM(d.pendidikan)) IN (''s3'',''s-3'',''doktor'')
                THEN 1 ELSE 0 END), 0),

            -- Pendidikan: Sp-1
            COALESCE(SUM(CASE
                WHEN LOWER(TRIM(d.pendidikan)) IN (''sp-1'',''sp1'',''spesialis 1'',''spesialis-1'')
                THEN 1 ELSE 0 END), 0),

            -- Pendidikan: Sp-2
            COALESCE(SUM(CASE
                WHEN LOWER(TRIM(d.pendidikan)) IN (''sp-2'',''sp2'',''spesialis 2'',''spesialis-2'')
                THEN 1 ELSE 0 END), 0),

            ''', p_tahun_akademik, ''',
            ''', p_semester_label, '''

        FROM ept_itps ps
        LEFT JOIN ept_htdd d
               ON d.kodept = ps.kodept
              AND d.kodeps  = ps.kodeps
        GROUP BY ps.kodept, ps.kodeps
        ORDER BY ps.kodept, ps.kodeps
    ');

    PREPARE stmt FROM @insert_sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;

    -- ────────────────────────────────────────
    -- STEP 3: Tampilkan hasil yang baru diinsert
    -- ────────────────────────────────────────
    SELECT
        o.kodept,
        pt.namapt,
        o.kodeps,
        ps.namaps,
        o.ik_tetap,
        o.ik_tidak_tetap,
        o.fn_asisten_ahli,
        o.fn_lektor,
        o.fn_lektor_kepala,
        o.fn_profesor,
        o.pdd_s1,
        o.pdd_s2,
        o.pdd_s3,
        o.pdd_sp1,
        o.pdd_sp2,
        o.tahun_akademik,
        o.semester
    FROM ept_out o
    LEFT JOIN ept_itpt pt ON pt.kodept = o.kodept
    LEFT JOIN ept_itps ps ON ps.kodept = o.kodept AND ps.kodeps = o.kodeps
    WHERE o.tahun_akademik = p_tahun_akademik
      AND o.semester       = p_semester_label
    ORDER BY o.kodept, o.kodeps;

END
"""

# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────
def get_conn():
    """Buat koneksi baru dengan autocommit=True."""
    return pymysql.connect(**DB_CONFIG)

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
# STEP 1: Test Koneksi
# ─────────────────────────────────────────────
def test_koneksi():
    print("\n[1] Menguji koneksi ke remote MySQL...")
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS versi")
            row = cur.fetchone()
            print(f"    ✅ Koneksi berhasil → {DB_CONFIG['host']}:{DB_CONFIG['port']}")
            print(f"    MySQL version: {row['versi']}")
        conn.close()
        return True
    except pymysql.Error as e:
        print(f"    ❌ Koneksi gagal: {e}")
        return False

# ─────────────────────────────────────────────
# STEP 2: Cek nilai unik pendidikan, fungsional, ikatankerja
# ─────────────────────────────────────────────
def cek_nilai_unik():
    print("\n[2] Mengecek nilai unik kolom pendidikan, fungsional, ikatankerja...")
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT pendidikan FROM ept_htdd ORDER BY pendidikan")
            pdd = [r['pendidikan'] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT fungsional FROM ept_htdd ORDER BY fungsional")
            fng = [r['fungsional'] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT ikatankerja FROM ept_htdd ORDER BY ikatankerja")
            ik  = [r['ikatankerja'] for r in cur.fetchall()]
        conn.close()
        print(f"    Nilai PENDIDIKAN  : {pdd}")
        print(f"    Nilai FUNGSIONAL  : {fng}")
        print(f"    Nilai IKATANKERJA : {ik}")
    except pymysql.Error as e:
        print(f"    ❌ Gagal: {e}")

# ─────────────────────────────────────────────
# STEP 3: Buat tabel ept_out (dipisah dari SP)
# ─────────────────────────────────────────────
def buat_tabel():
    print("\n[3] Membuat tabel ept_out jika belum ada...")
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(DDL_CREATE_TABLE)
        conn.close()
        print("    ✅ Tabel ept_out siap.")
        return True
    except pymysql.Error as e:
        print(f"    ❌ Gagal membuat tabel: {e}")
        return False

# ─────────────────────────────────────────────
# STEP 4: Deploy Store Procedure
# ─────────────────────────────────────────────
def deploy_sp():
    print("\n[4] Mendeploy store procedure sp_generate_ept_out...")
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DROP PROCEDURE IF EXISTS sp_generate_ept_out")
            cur.execute(SP_DDL)
        conn.close()
        print("    ✅ Store procedure berhasil dideploy!")
        return True
    except pymysql.Error as e:
        print(f"    ❌ Deploy gagal: {e}")
        return False

# ─────────────────────────────────────────────
# STEP 5: Pilih Semester
# ─────────────────────────────────────────────
def pilih_semester():
    options = [
        ("20251", "2025/2026", "Ganjil"),
        ("20252", "2024/2025", "Genap"),
        ("20241", "2024/2025", "Ganjil"),
        ("20242", "2023/2024", "Genap"),
        ("20231", "2023/2024", "Ganjil"),
        ("20232", "2022/2023", "Genap"),
    ]
    print("\n[5] Pilih Semester yang akan diproses:")
    for i, (kode, ta, sem) in enumerate(options, 1):
        print(f"    {i}. Kolom S{kode}  →  TA {ta}  |  {sem}")
    print()
    while True:
        pilihan = input("    Masukkan nomor pilihan: ").strip()
        if pilihan.isdigit() and 1 <= int(pilihan) <= len(options):
            kode, ta, sem = options[int(pilihan) - 1]
            print(f"    → Dipilih: S{kode} | TA {ta} | {sem}")
            return kode, ta, sem
        print("    ⚠️  Pilihan tidak valid.")

# ─────────────────────────────────────────────
# STEP 6: Eksekusi Store Procedure
# Menggunakan execute("CALL ...") bukan callproc()
# agar result set dari SP bisa dibaca dengan benar
# ─────────────────────────────────────────────
def eksekusi_sp(sem_col, tahun_akademik, sem_label):
    print(f"\n[6] Menjalankan sp_generate_ept_out('{sem_col}', '{tahun_akademik}', '{sem_label}')...")
    print(f"    Ini akan mengisi tabel ept_out. Lanjut? (y/n) ", end="")
    if input().strip().lower() != 'y':
        print("    ⚠️  Dibatalkan.")
        return

    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # Gunakan execute("CALL ...") bukan callproc()
            # agar result set SP terbaca dengan benar di pymysql
            cur.execute(
                "CALL sp_generate_ept_out(%s, %s, %s)",
                (sem_col, tahun_akademik, sem_label)
            )
            rows = cur.fetchall()

        conn.close()

        if rows:
            print(f"\n    ✅ Berhasil! {len(rows)} baris dimasukkan ke tabel ept_out.")
            print_section(
                f"TABEL ept_out — TA {tahun_akademik} | Semester {sem_label}",
                rows
            )
        else:
            print("    ⚠️  SP selesai tapi result set kosong.")

    except pymysql.Error as e:
        print(f"    ❌ Eksekusi gagal: {e}")

# ─────────────────────────────────────────────
# STEP 7: Verifikasi langsung dari tabel ept_out
# ─────────────────────────────────────────────
def verifikasi_tabel():
    print("\n[7] Verifikasi langsung dari tabel ept_out...")
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # Cek jumlah total baris
            cur.execute("SELECT COUNT(*) AS total_baris FROM ept_out")
            total = cur.fetchone()
            print(f"    Total baris di ept_out: {total['total_baris']}")

            # Ringkasan per periode
            cur.execute("""
                SELECT
                    tahun_akademik,
                    semester,
                    COUNT(*)              AS jumlah_prodi,
                    SUM(ik_tetap)         AS total_tetap,
                    SUM(ik_tidak_tetap)   AS total_tidak_tetap,
                    SUM(fn_asisten_ahli)  AS total_asisten_ahli,
                    SUM(fn_lektor)        AS total_lektor,
                    SUM(fn_lektor_kepala) AS total_lektor_kepala,
                    SUM(fn_profesor)      AS total_profesor,
                    SUM(pdd_s1)           AS total_s1,
                    SUM(pdd_s2)           AS total_s2,
                    SUM(pdd_s3)           AS total_s3,
                    SUM(pdd_sp1)          AS total_sp1,
                    SUM(pdd_sp2)          AS total_sp2
                FROM ept_out
                GROUP BY tahun_akademik, semester
                ORDER BY tahun_akademik DESC, semester
            """)
            rows = cur.fetchall()
        conn.close()
        print_section("RINGKASAN ept_out per Periode", rows)
    except pymysql.Error as e:
        print(f"    ❌ Gagal verifikasi: {e}")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("  SP GENERATE EPT_OUT — Remote MySQL  (v3 fixed)")
    print("  Database : birotium_sifoo @ birotium-ums.id")
    print("=" * 65)

    if not test_koneksi():
        exit(1)

    cek_nilai_unik()

    if not buat_tabel():
        exit(1)

    if not deploy_sp():
        exit(1)

    sem_col, tahun_akademik, sem_label = pilih_semester()
    eksekusi_sp(sem_col, tahun_akademik, sem_label)
    verifikasi_tabel()

    print(f"\n{'='*65}")
    print("  Selesai! ✅")
    print(f"{'='*65}\n")
