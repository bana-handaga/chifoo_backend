"""
=====================================================================
Script: sp_distribusi_dosen.py  (v2 — dengan parameter kodept)
Deskripsi: Deploy & test Store Procedure sp_distribusi_dosen
           ke remote MySQL database birotium_sifoo
Kebutuhan: pip install pymysql tabulate
=====================================================================
"""

import pymysql
import pymysql.cursors
from tabulate import tabulate

# ─────────────────────────────────────────────
# KONFIGURASI KONEKSI
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
}

# ─────────────────────────────────────────────
# DDL STORE PROCEDURE
# Parameter: p_kodept, p_kodeps, p_semester
# ─────────────────────────────────────────────
SP_DDL = """
CREATE PROCEDURE `sp_distribusi_dosen`(
    IN p_kodept   VARCHAR(20),
    IN p_kodeps   VARCHAR(14),
    IN p_semester INT
)
BEGIN
    DECLARE v_col_name VARCHAR(10);
    SET v_col_name = CONCAT('S', p_semester);

    -- ────────────────────────────────────────
    -- RESULT SET 1: Info Perguruan Tinggi
    -- ────────────────────────────────────────
    SELECT
        pt.kodept,
        pt.namapt,
        pt.jenis,
        pt.organisasi,
        pt.akreditasi,
        pt.status
    FROM ept_itpt pt
    WHERE pt.kodept = p_kodept
    LIMIT 1;

    -- ────────────────────────────────────────
    -- RESULT SET 2: Info Program Studi
    -- ────────────────────────────────────────
    SELECT
        ps.kodeps,
        ps.namaps,
        ps.jenjang,
        ps.status,
        ps.akreditasi,
        ps.akreditasi_internasional,
        ps.dosen_homebase,
        ps.mahasiswa,
        ps.rasio
    FROM ept_itps ps
    WHERE ps.kodept = p_kodept
      AND ps.kodeps = p_kodeps
    LIMIT 1;

    -- ────────────────────────────────────────
    -- RESULT SET 3: Distribusi Pendidikan
    -- ────────────────────────────────────────
    SET @sql_pendidikan = CONCAT(
        'SELECT
            COALESCE(d.pendidikan, ''Tidak Diketahui'') AS pendidikan,
            COUNT(*) AS jumlah_dosen,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS persentase
        FROM ept_htdd d
        WHERE d.kodept = ?
          AND d.kodeps = ?
        GROUP BY d.pendidikan
        ORDER BY jumlah_dosen DESC'
    );
    PREPARE stmt1 FROM @sql_pendidikan;
    SET @p_kodept = p_kodept;
    SET @p_kodeps = p_kodeps;
    EXECUTE stmt1 USING @p_kodept, @p_kodeps;
    DEALLOCATE PREPARE stmt1;

    -- ────────────────────────────────────────
    -- RESULT SET 4: Distribusi Fungsional
    -- ────────────────────────────────────────
    SET @sql_fungsional = CONCAT(
        'SELECT
            COALESCE(d.fungsional, ''Belum Ada'') AS fungsional,
            COUNT(*) AS jumlah_dosen,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS persentase
        FROM ept_htdd d
        WHERE d.kodept = ?
          AND d.kodeps = ?
        GROUP BY d.fungsional
        ORDER BY jumlah_dosen DESC'
    );
    PREPARE stmt2 FROM @sql_fungsional;
    EXECUTE stmt2 USING @p_kodept, @p_kodeps;
    DEALLOCATE PREPARE stmt2;

    -- ────────────────────────────────────────
    -- RESULT SET 5: Distribusi Ikatan Kerja
    -- ────────────────────────────────────────
    SET @sql_ikatankerja = CONCAT(
        'SELECT
            COALESCE(d.ikatankerja, ''Tidak Diketahui'') AS ikatankerja,
            COUNT(*) AS jumlah_dosen,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS persentase
        FROM ept_htdd d
        WHERE d.kodept = ?
          AND d.kodeps = ?
        GROUP BY d.ikatankerja
        ORDER BY jumlah_dosen DESC'
    );
    PREPARE stmt3 FROM @sql_ikatankerja;
    EXECUTE stmt3 USING @p_kodept, @p_kodeps;
    DEALLOCATE PREPARE stmt3;

    -- ────────────────────────────────────────
    -- RESULT SET 6: Detail Dosen Aktif
    -- ────────────────────────────────────────
    SET @sql_detail = CONCAT(
        'SELECT
            d.nidn,
            d.nama,
            d.gelar,
            d.pendidikan,
            d.fungsional,
            d.ikatankerja,
            d.statuskeaktifan,
            d.jk
        FROM ept_htdd d
        WHERE d.kodept = ?
          AND d.kodeps = ?
        ORDER BY d.nama ASC'
    );
    PREPARE stmt4 FROM @sql_detail;
    EXECUTE stmt4 USING @p_kodept, @p_kodeps;
    DEALLOCATE PREPARE stmt4;

END
"""

# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────
def print_section(title, rows):
    print(f"\n{'═'*65}")
    print(f"  {title}")
    print(f"{'═'*65}")
    if not rows:
        print("  [Tidak ada data]")
        return
    headers = list(rows[0].keys())
    data    = [list(r.values()) for r in rows]
    print(tabulate(data, headers=headers, tablefmt="fancy_grid"))

def label_semester(sem_str):
    sem_str = str(sem_str)
    if sem_str.endswith("1"):
        return f"Ganjil {sem_str[:4]}/{int(sem_str[:4])+1}"
    else:
        return f"Genap {int(sem_str[:4])-1}/{sem_str[:4]}"

# ─────────────────────────────────────────────
# STEP 1: Test Koneksi
# ─────────────────────────────────────────────
def test_koneksi():
    print("\n[1] Menguji koneksi ke remote MySQL...")
    try:
        conn = pymysql.connect(**DB_CONFIG)
        print(f"    ✅ Koneksi berhasil → {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        conn.close()
        return True
    except pymysql.Error as e:
        print(f"    ❌ Koneksi gagal: {e}")
        return False

# ─────────────────────────────────────────────
# STEP 2: Deploy Store Procedure
# ─────────────────────────────────────────────
def deploy_sp():
    print("\n[2] Mendeploy store procedure sp_distribusi_dosen...")
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("DROP PROCEDURE IF EXISTS sp_distribusi_dosen")
            cur.execute(SP_DDL)
            conn.commit()
        conn.close()
        print("    ✅ Store procedure berhasil dideploy!")
        return True
    except pymysql.Error as e:
        print(f"    ❌ Deploy gagal: {e}")
        return False

# ─────────────────────────────────────────────
# STEP 3: Pilih Perguruan Tinggi
# ─────────────────────────────────────────────
def pilih_perguruan_tinggi():
    print("\n[3] Mengambil daftar Perguruan Tinggi...")
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT kodept, namapt, jenis, akreditasi
                FROM ept_itpt
                WHERE status = 'Aktif' and akreditasi='unggul'
                ORDER BY namapt ASC
                LIMIT 30
            """)
            rows = cur.fetchall()
        conn.close()

        if not rows:
            print("    ⚠️  Tidak ada data PT aktif.")
            return input("    Masukkan kodept manual: ").strip()

        print(f"\n    {'No':<4} {'Kode PT':<15} {'Nama PT':<45} {'Jenis':<15} {'Akreditasi'}")
        print(f"    {'─'*4} {'─'*15} {'─'*45} {'─'*15} {'─'*10}")
        for i, r in enumerate(rows, 1):
            namapt = (r['namapt'] or '')[:43]
            print(f"    {i:<4} {r['kodept']:<15} {namapt:<45} {r['jenis']:<15} {r['akreditasi']}")

        print()
        while True:
            pilihan = input("    Pilih nomor atau ketik kodept langsung: ").strip()
            if pilihan.isdigit():
                idx = int(pilihan) - 1
                if 0 <= idx < len(rows):
                    kodept = rows[idx]['kodept']
                    print(f"    → PT dipilih: [{kodept}] {rows[idx]['namapt']}")
                    return kodept
                else:
                    print("    ⚠️  Nomor tidak valid.")
            else:
                return pilihan.upper()

    except pymysql.Error as e:
        print(f"    ❌ Gagal: {e}")
        return input("    Masukkan kodept manual: ").strip()

# ─────────────────────────────────────────────
# STEP 4: Pilih Program Studi
# ─────────────────────────────────────────────
def pilih_program_studi(kodept):
    print(f"\n[4] Mengambil daftar Program Studi untuk PT [{kodept}]...")
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT kodeps, namaps, jenjang, akreditasi, status
                FROM ept_itps
                WHERE kodept = %s
                ORDER BY jenjang, namaps ASC
            """, (kodept,))
            rows = cur.fetchall()
        conn.close()

        if not rows:
            print(f"    ⚠️  Tidak ada data prodi untuk PT [{kodept}].")
            return input("    Masukkan kodeps manual: ").strip()

        print(f"\n    {'No':<4} {'Kode PS':<15} {'Nama PS':<40} {'Jenjang':<10} {'Akreditasi':<12} {'Status'}")
        print(f"    {'─'*4} {'─'*15} {'─'*40} {'─'*10} {'─'*12} {'─'*10}")
        for i, r in enumerate(rows, 1):
            namaps = (r['namaps'] or '')[:38]
            print(f"    {i:<4} {r['kodeps']:<15} {namaps:<40} {r['jenjang']:<10} {r['akreditasi']:<12} {r['status']}")

        print()
        while True:
            pilihan = input("    Pilih nomor atau ketik kodeps langsung: ").strip()
            if pilihan.isdigit():
                idx = int(pilihan) - 1
                if 0 <= idx < len(rows):
                    kodeps = rows[idx]['kodeps']
                    print(f"    → PS dipilih: [{kodeps}] {rows[idx]['namaps']}")
                    return kodeps
                else:
                    print("    ⚠️  Nomor tidak valid.")
            else:
                return pilihan

    except pymysql.Error as e:
        print(f"    ❌ Gagal: {e}")
        return input("    Masukkan kodeps manual: ").strip()

# ─────────────────────────────────────────────
# STEP 5: Pilih Semester
# ─────────────────────────────────────────────
def pilih_semester():
    semesters = [
        ("20252", "Genap 2024/2025"),
        ("20251", "Ganjil 2025/2026"),
        ("20242", "Genap 2023/2024"),
        ("20241", "Ganjil 2024/2025"),
        ("20232", "Genap 2022/2023"),
        ("20231", "Ganjil 2023/2024"),
    ]
    print("\n[5] Pilih Semester:")
    for i, (kode, nama) in enumerate(semesters, 1):
        print(f"    {i}. {kode}  —  {nama}")
    print()
    while True:
        pilihan = input("    Pilih nomor atau ketik kode semester (misal 20251): ").strip()
        if pilihan.isdigit() and 1 <= int(pilihan) <= len(semesters):
            kode, nama = semesters[int(pilihan) - 1]
            print(f"    → Semester dipilih: [{kode}] {nama}")
            return kode
        elif len(pilihan) == 5 and pilihan.isdigit():
            return pilihan
        else:
            print("    ⚠️  Input tidak valid.")

# ─────────────────────────────────────────────
# STEP 6: Eksekusi Store Procedure
# ─────────────────────────────────────────────
def eksekusi_sp(kodept, kodeps, semester):
    lbl = label_semester(semester)
    print(f"\n[6] Menjalankan sp_distribusi_dosen('{kodept}', '{kodeps}', {semester})")
    print(f"    Semester : {lbl}")

    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.callproc("sp_distribusi_dosen", [kodept, kodeps, int(semester)])
            results = []
            while True:
                rows = cur.fetchall()
                results.append(rows)
                if not cur.nextset():
                    break
        conn.close()

        titles = [
            "📌 INFO PERGURUAN TINGGI",
            "🏫 INFO PROGRAM STUDI",
            f"🎓 DISTRIBUSI PENDIDIKAN — {lbl}",
            f"📊 DISTRIBUSI FUNGSIONAL — {lbl}",
            f"🤝 DISTRIBUSI IKATAN KERJA — {lbl}",
            f"👥 DETAIL DOSEN AKTIF — {lbl}",
        ]

        for title, rows in zip(titles, results):
            print_section(title, rows)

    except pymysql.Error as e:
        print(f"    ❌ Eksekusi gagal: {e}")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("  SP DISTRIBUSI DOSEN — Remote MySQL Tester  (v2)")
    print("  Database : birotium_sifoo @ birotium-ums.id")
    print("=" * 65)

    if not test_koneksi():
        exit(1)

    if not deploy_sp():
        exit(1)

    kodept   = pilih_perguruan_tinggi()
    kodeps   = pilih_program_studi(kodept)
    semester = pilih_semester()

    eksekusi_sp(kodept, kodeps, semester)

    print(f"\n{'='*65}")
    print("  Selesai! ✅")
    print(f"{'='*65}\n")
