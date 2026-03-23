"""Models for Universities (Perguruan Tinggi Muhammadiyah dan Aisyiyah)"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Wilayah(models.Model):
    """Pimpinan Wilayah Muhammadiyah"""
    kode = models.CharField(max_length=10, unique=True)
    nama = models.CharField(max_length=100)
    provinsi = models.CharField(max_length=100)
    
    class Meta:
        verbose_name = 'Wilayah'
        verbose_name_plural = 'Wilayah'
        ordering = ['nama']

    def __str__(self):
        return f"{self.nama} - {self.provinsi}"


class PerguruanTinggi(models.Model):
    """Model utama Perguruan Tinggi Muhammadiyah dan Aisyiyah"""
    
    class JenisPT(models.TextChoices):
        UNIVERSITAS = 'universitas', _('Universitas')
        INSTITUT = 'institut', _('Institut')
        SEKOLAH_TINGGI = 'sekolah_tinggi', _('Sekolah Tinggi')
        POLITEKNIK = 'politeknik', _('Politeknik')
        AKADEMI = 'akademi', _('Akademi')

    class OrganisasiInduk(models.TextChoices):
        MUHAMMADIYAH = 'muhammadiyah', _('Muhammadiyah')
        AISYIYAH = 'aisyiyah', _('Aisyiyah')

    class StatusAkreditasi(models.TextChoices):
        UNGGUL = 'unggul', _('Unggul')
        BAIK_SEKALI = 'baik_sekali', _('Baik Sekali')
        BAIK = 'baik', _('Baik')
        BELUM = 'belum', _('Belum Terakreditasi')

    # Identitas
    kode_pt = models.CharField(max_length=20, unique=True, verbose_name='Kode PT')
    nama = models.CharField(max_length=200, verbose_name='Nama PT')
    singkatan = models.CharField(max_length=20, verbose_name='Singkatan')
    jenis = models.CharField(max_length=20, choices=JenisPT.choices, verbose_name='Jenis PT')
    organisasi_induk = models.CharField(
        max_length=20, choices=OrganisasiInduk.choices, verbose_name='Organisasi Induk'
    )
    wilayah = models.ForeignKey(
        Wilayah, on_delete=models.PROTECT, related_name='perguruan_tinggi'
    )
    
    # Lokasi
    alamat = models.TextField(verbose_name='Alamat')
    kota = models.CharField(max_length=100, verbose_name='Kota/Kabupaten')
    provinsi = models.CharField(max_length=100, verbose_name='Provinsi')
    kode_pos = models.CharField(max_length=10, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    
    # Kontak
    website = models.URLField(blank=True, verbose_name='Website')
    email = models.EmailField(blank=True, verbose_name='Email')
    telepon = models.CharField(max_length=20, blank=True, verbose_name='Telepon')
    
    # Akreditasi
    akreditasi_institusi = models.CharField(
        max_length=20, choices=StatusAkreditasi.choices, 
        default=StatusAkreditasi.BELUM, verbose_name='Akreditasi Institusi'
    )
    nomor_sk_akreditasi = models.CharField(max_length=100, blank=True)
    tanggal_sk_akreditasi = models.DateField(null=True, blank=True)
    tanggal_kadaluarsa_akreditasi = models.DateField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True, verbose_name='Aktif')
    tahun_berdiri = models.PositiveIntegerField(null=True, blank=True)
    logo = models.ImageField(upload_to='logos/', null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Perguruan Tinggi'
        verbose_name_plural = 'Perguruan Tinggi'
        ordering = ['nama']

    def __str__(self):
        return f"{self.singkatan} - {self.nama}"


class ProgramStudi(models.Model):
    """Program Studi di Perguruan Tinggi"""
    
    class Jenjang(models.TextChoices):
        D1 = 'd1', 'Diploma 1'
        D2 = 'd2', 'Diploma 2'
        D3 = 'd3', 'Diploma 3'
        D4 = 'd4', 'Diploma 4 / Sarjana Terapan'
        S1 = 's1', 'Sarjana (S1)'
        PROFESI = 'profesi', 'Profesi'
        S2 = 's2', 'Magister (S2)'
        S3 = 's3', 'Doktor (S3)'

    class StatusAkreditasi(models.TextChoices):
        UNGGUL = 'unggul', 'Unggul'
        BAIK_SEKALI = 'baik_sekali', 'Baik Sekali'
        BAIK = 'baik', 'Baik'
        C = 'c', 'C'
        BELUM = 'belum', 'Belum Terakreditasi'

    perguruan_tinggi = models.ForeignKey(
        PerguruanTinggi, on_delete=models.CASCADE, related_name='program_studi'
    )
    kode_prodi = models.CharField(max_length=20, verbose_name='Kode Prodi')
    nama = models.CharField(max_length=200, verbose_name='Nama Program Studi')
    jenjang = models.CharField(max_length=10, choices=Jenjang.choices)
    akreditasi = models.CharField(
        max_length=20, choices=StatusAkreditasi.choices, default=StatusAkreditasi.BELUM
    )
    no_sk_akreditasi = models.CharField(max_length=100, blank=True, verbose_name='No. SK Akreditasi')
    tanggal_kedaluarsa_akreditasi = models.DateField(null=True, blank=True, verbose_name='Tanggal Kedaluarsa Akreditasi')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Program Studi'
        verbose_name_plural = 'Program Studi'
        unique_together = ['perguruan_tinggi', 'kode_prodi']
        ordering = ['nama']

    def __str__(self):
        return f"{self.nama} ({self.jenjang}) - {self.perguruan_tinggi.singkatan}"


class DataMahasiswa(models.Model):
    """Data jumlah mahasiswa per periode"""
    
    perguruan_tinggi = models.ForeignKey(
        PerguruanTinggi, on_delete=models.CASCADE, related_name='data_mahasiswa'
    )
    program_studi = models.ForeignKey(
        ProgramStudi, on_delete=models.CASCADE, related_name='data_mahasiswa',
        null=True, blank=True
    )
    tahun_akademik = models.CharField(max_length=10, verbose_name='Tahun Akademik')
    semester = models.CharField(max_length=10, choices=[('ganjil', 'Ganjil'), ('genap', 'Genap')])
    
    mahasiswa_baru = models.PositiveIntegerField(default=0)
    mahasiswa_aktif = models.PositiveIntegerField(default=0)
    mahasiswa_lulus = models.PositiveIntegerField(default=0)
    mahasiswa_dropout = models.PositiveIntegerField(default=0)
    
    mahasiswa_pria = models.PositiveIntegerField(default=0)
    mahasiswa_wanita = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Data Mahasiswa'
        verbose_name_plural = 'Data Mahasiswa'
        ordering = ['-tahun_akademik', 'semester']

    def __str__(self):
        return f"{self.perguruan_tinggi.singkatan} - {self.tahun_akademik}/{self.semester}"


class DataDosen(models.Model):
    """Data jumlah dosen per PT per periode"""

    SEMESTER_CHOICES = [('ganjil', 'Ganjil'), ('genap', 'Genap')]

    perguruan_tinggi = models.ForeignKey(
        PerguruanTinggi, on_delete=models.CASCADE, related_name='data_dosen'
    )
    program_studi = models.ForeignKey(
        ProgramStudi, on_delete=models.CASCADE, related_name='data_dosen',
        null=True, blank=True
    )
    tahun_akademik = models.CharField(max_length=10, verbose_name='Tahun Akademik')
    semester = models.CharField(max_length=10, choices=SEMESTER_CHOICES)

    dosen_tetap = models.PositiveIntegerField(default=0)
    dosen_tidak_tetap = models.PositiveIntegerField(default=0)
    dosen_s3 = models.PositiveIntegerField(default=0)
    dosen_s2 = models.PositiveIntegerField(default=0)
    dosen_s1 = models.PositiveIntegerField(default=0)
    dosen_guru_besar = models.PositiveIntegerField(default=0)
    dosen_lektor_kepala = models.PositiveIntegerField(default=0)
    dosen_lektor = models.PositiveIntegerField(default=0)
    dosen_asisten_ahli = models.PositiveIntegerField(default=0)
    dosen_bersertifikat = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Data Dosen'
        verbose_name_plural = 'Data Dosen'
        unique_together = ['perguruan_tinggi', 'program_studi', 'tahun_akademik', 'semester']
        ordering = ['-tahun_akademik', 'semester']

    def __str__(self):
        return f"{self.perguruan_tinggi.singkatan} - {self.tahun_akademik}/{self.semester}"


class ProfilDosen(models.Model):
    """Profil individu dosen hasil scrape PDDikti"""

    class JenisKelamin(models.TextChoices):
        LAKI = 'L', 'Laki-laki'
        PEREMPUAN = 'P', 'Perempuan'

    class PendidikanTertinggi(models.TextChoices):
        S1 = 's1', 'S1'
        S2 = 's2', 'S2'
        S3 = 's3', 'S3'
        PROFESI = 'profesi', 'Profesi'
        LAINNYA = 'lainnya', 'Lainnya'

    class IkatanKerja(models.TextChoices):
        TETAP = 'tetap', 'Dosen Tetap'
        TIDAK_TETAP = 'tidak_tetap', 'Dosen Tidak Tetap'

    # Identitas — nidn nullable agar unique_together (pt, nidn) tetap valid
    # untuk dosen tanpa NIDN (MySQL mengizinkan banyak NULL di unique index)
    nidn  = models.CharField(max_length=20, null=True, blank=True, db_index=True, verbose_name='NIDN')
    nuptk = models.CharField(max_length=20, blank=True, verbose_name='NUPTK')
    nama  = models.CharField(max_length=200, verbose_name='Nama Dosen')
    jenis_kelamin = models.CharField(
        max_length=1, choices=JenisKelamin.choices, blank=True
    )

    # Relasi
    perguruan_tinggi = models.ForeignKey(
        PerguruanTinggi, on_delete=models.CASCADE,
        related_name='profil_dosen', verbose_name='Perguruan Tinggi'
    )
    program_studi = models.ForeignKey(
        ProgramStudi, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='profil_dosen', verbose_name='Program Studi'
    )
    # Nama prodi dari PDDikti (untuk kasus prodi belum ter-match ke FK)
    program_studi_nama = models.CharField(max_length=200, blank=True, verbose_name='Nama Prodi (PDDikti)')

    # Jabatan & status
    jabatan_fungsional   = models.CharField(max_length=50, blank=True, verbose_name='Jabatan Fungsional')
    pendidikan_tertinggi = models.CharField(
        max_length=10, choices=PendidikanTertinggi.choices, blank=True, verbose_name='Pendidikan Tertinggi'
    )
    ikatan_kerja = models.CharField(
        max_length=15, choices=IkatanKerja.choices, blank=True, verbose_name='Ikatan Kerja'
    )
    status = models.CharField(max_length=30, blank=True, verbose_name='Status')

    # Referensi scrape
    url_pencarian = models.CharField(max_length=500, blank=True, verbose_name='URL Pencarian')
    scraped_at    = models.DateTimeField(null=True, blank=True, verbose_name='Waktu Scrape')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Profil Dosen'
        verbose_name_plural = 'Profil Dosen'
        unique_together = [['perguruan_tinggi', 'nidn']]
        ordering = ['nama']
        indexes = [
            models.Index(fields=['nidn']),
            models.Index(fields=['nuptk']),
            models.Index(fields=['perguruan_tinggi', 'program_studi']),
        ]

    def __str__(self):
        return f"{self.nama} ({self.nidn or self.nuptk}) — {self.perguruan_tinggi.singkatan}"


class RiwayatPendidikanDosen(models.Model):
    """Riwayat pendidikan dosen dari PDDikti (field sekolah di ept_itdd.json)"""

    profil_dosen = models.ForeignKey(
        ProfilDosen, on_delete=models.CASCADE,
        related_name='riwayat_pendidikan', verbose_name='Profil Dosen'
    )
    perguruan_tinggi_asal = models.CharField(max_length=300, blank=True, verbose_name='Perguruan Tinggi Asal')
    gelar                 = models.CharField(max_length=150, blank=True, verbose_name='Gelar Akademik')
    jenjang               = models.CharField(max_length=20,  blank=True, verbose_name='Jenjang')
    tahun_lulus           = models.CharField(max_length=4,   blank=True, verbose_name='Tahun Lulus')
    is_luar_negeri        = models.BooleanField(default=False, db_index=True, verbose_name='Luar Negeri')

    class Meta:
        verbose_name        = 'Riwayat Pendidikan Dosen'
        verbose_name_plural = 'Riwayat Pendidikan Dosen'
        ordering            = ['profil_dosen__nama', 'tahun_lulus']
        indexes             = [
            models.Index(fields=['profil_dosen']),
            models.Index(fields=['jenjang']),
            models.Index(fields=['jenjang', 'is_luar_negeri']),
        ]

    def __str__(self):
        return f"{self.profil_dosen.nama} — {self.jenjang} {self.tahun_lulus}"


class SintaAfiliasi(models.Model):
    """Profil afiliasi Perguruan Tinggi dari SINTA (Science and Technology Index)."""

    perguruan_tinggi = models.OneToOneField(
        PerguruanTinggi, on_delete=models.CASCADE,
        related_name='sinta_afiliasi', verbose_name='Perguruan Tinggi'
    )

    # --- Identitas SINTA ---
    sinta_id        = models.CharField(max_length=20, blank=True, db_index=True, verbose_name='SINTA ID')
    sinta_kode      = models.CharField(max_length=20, blank=True, verbose_name='Kode SINTA')
    nama_sinta      = models.CharField(max_length=200, blank=True, verbose_name='Nama di SINTA')
    singkatan_sinta = models.CharField(max_length=50, blank=True, verbose_name='Singkatan di SINTA')
    lokasi_sinta    = models.CharField(max_length=200, blank=True, verbose_name='Lokasi di SINTA')
    sinta_profile_url = models.URLField(blank=True, verbose_name='URL Profil SINTA')

    # --- Logo universitas (base64) ---
    # Diambil dari: /authorverification/public/images/affiliations/{sinta_id}.jpg
    # Disimpan sebagai: "data:image/jpeg;base64,/9j/4AAQ..."
    logo_base64 = models.TextField(blank=True, verbose_name='Logo Universitas (Base64)')

    # --- Ringkasan ---
    jumlah_authors     = models.PositiveIntegerField(default=0, verbose_name='Jumlah Authors')
    jumlah_departments = models.PositiveIntegerField(default=0, verbose_name='Jumlah Departments')
    jumlah_journals    = models.PositiveIntegerField(default=0, verbose_name='Jumlah Journals')

    # --- SINTA Score ---
    sinta_score_overall           = models.BigIntegerField(default=0, verbose_name='SINTA Score Overall')
    sinta_score_3year             = models.BigIntegerField(default=0, verbose_name='SINTA Score 3Yr')
    sinta_score_productivity      = models.IntegerField(default=0, verbose_name='SINTA Score Productivity')
    sinta_score_productivity_3year= models.IntegerField(default=0, verbose_name='SINTA Score Productivity 3Yr')

    # --- Statistik Scopus ---
    scopus_dokumen            = models.FloatField(default=0, verbose_name='Scopus Documents')
    scopus_sitasi             = models.FloatField(default=0, verbose_name='Scopus Citations')
    scopus_dokumen_disitasi   = models.FloatField(default=0, verbose_name='Scopus Cited Documents')
    scopus_sitasi_per_peneliti= models.FloatField(default=0, verbose_name='Scopus Citation per Researcher')

    # --- Statistik Google Scholar ---
    gscholar_dokumen            = models.FloatField(default=0, verbose_name='GScholar Documents')
    gscholar_sitasi             = models.FloatField(default=0, verbose_name='GScholar Citations')
    gscholar_dokumen_disitasi   = models.FloatField(default=0, verbose_name='GScholar Cited Documents')
    gscholar_sitasi_per_peneliti= models.FloatField(default=0, verbose_name='GScholar Citation per Researcher')

    # --- Statistik Web of Science ---
    wos_dokumen            = models.FloatField(default=0, verbose_name='WoS Documents')
    wos_sitasi             = models.FloatField(default=0, verbose_name='WoS Citations')
    wos_dokumen_disitasi   = models.FloatField(default=0, verbose_name='WoS Cited Documents')
    wos_sitasi_per_peneliti= models.FloatField(default=0, verbose_name='WoS Citation per Researcher')

    # --- Statistik Garuda ---
    garuda_dokumen            = models.FloatField(default=0, verbose_name='Garuda Documents')
    garuda_sitasi             = models.FloatField(default=0, verbose_name='Garuda Citations')
    garuda_dokumen_disitasi   = models.FloatField(default=0, verbose_name='Garuda Cited Documents')
    garuda_sitasi_per_peneliti= models.FloatField(default=0, verbose_name='Garuda Citation per Researcher')

    # --- Distribusi Kuartil Scopus ---
    scopus_q1  = models.PositiveIntegerField(default=0, verbose_name='Scopus Q1')
    scopus_q2  = models.PositiveIntegerField(default=0, verbose_name='Scopus Q2')
    scopus_q3  = models.PositiveIntegerField(default=0, verbose_name='Scopus Q3')
    scopus_q4  = models.PositiveIntegerField(default=0, verbose_name='Scopus Q4')
    scopus_noq = models.PositiveIntegerField(default=0, verbose_name='Scopus No-Q')

    # --- Metadata ---
    sinta_last_update = models.CharField(max_length=50, blank=True, verbose_name='Last Update SINTA')
    scraped_at        = models.DateTimeField(auto_now=True, verbose_name='Waktu Scrape')

    class Meta:
        verbose_name        = 'SINTA Afiliasi'
        verbose_name_plural = 'SINTA Afiliasi'
        ordering            = ['-sinta_score_overall']
        indexes             = [
            models.Index(fields=['sinta_id']),
            models.Index(fields=['sinta_score_overall']),
        ]

    def __str__(self):
        return f"{self.perguruan_tinggi.singkatan} — SINTA {self.sinta_id}"


class SintaTrendTahunan(models.Model):
    """
    Tren output tridharma per tahun: publikasi Scopus, penelitian, dan pengabdian.
    Satu baris = satu PT × satu jenis × satu tahun.
    """

    class Jenis(models.TextChoices):
        SCOPUS   = 'scopus',   'Publikasi Scopus'
        RESEARCH = 'research', 'Penelitian'
        SERVICE  = 'service',  'Pengabdian Masyarakat'

    afiliasi = models.ForeignKey(
        SintaAfiliasi, on_delete=models.CASCADE,
        related_name='trend_tahunan', verbose_name='SINTA Afiliasi'
    )
    jenis  = models.CharField(max_length=10, choices=Jenis.choices, verbose_name='Jenis')
    tahun  = models.PositiveSmallIntegerField(verbose_name='Tahun')
    jumlah = models.PositiveIntegerField(default=0, verbose_name='Jumlah')

    # Khusus jenis='research': breakdown dari radar chart
    research_article    = models.PositiveIntegerField(default=0, verbose_name='Research Article')
    research_conference = models.PositiveIntegerField(default=0, verbose_name='Research Conference')
    research_others     = models.PositiveIntegerField(default=0, verbose_name='Research Others')

    class Meta:
        verbose_name        = 'SINTA Trend Tahunan'
        verbose_name_plural = 'SINTA Trend Tahunan'
        unique_together     = ('afiliasi', 'jenis', 'tahun')
        ordering            = ['afiliasi', 'jenis', 'tahun']
        indexes             = [
            models.Index(fields=['jenis', 'tahun']),
        ]

    def __str__(self):
        return f"{self.afiliasi.perguruan_tinggi.singkatan} — {self.jenis} {self.tahun}: {self.jumlah}"


class SintaWcuTahunan(models.Model):
    """
    WCU Analysis: jumlah paper per bidang keilmuan (Scival) per tahun.
    Hanya tersedia untuk PT besar yang terindeks Scival (~8 PT PTMA).
    """

    afiliasi     = models.ForeignKey(
        SintaAfiliasi, on_delete=models.CASCADE,
        related_name='wcu_tahunan', verbose_name='SINTA Afiliasi'
    )
    tahun        = models.PositiveSmallIntegerField(verbose_name='Tahun')

    # 5 bidang keilmuan Scival + overall
    arts_humanities              = models.PositiveIntegerField(default=0, verbose_name='Arts & Humanities')
    engineering_technology       = models.PositiveIntegerField(default=0, verbose_name='Engineering & Technology')
    life_sciences_medicine       = models.PositiveIntegerField(default=0, verbose_name='Life Sciences & Medicine')
    natural_sciences             = models.PositiveIntegerField(default=0, verbose_name='Natural Sciences')
    social_sciences_management   = models.PositiveIntegerField(default=0, verbose_name='Social Sciences & Management')
    overall                      = models.PositiveIntegerField(default=0, verbose_name='Overall')

    class Meta:
        verbose_name        = 'SINTA WCU Tahunan'
        verbose_name_plural = 'SINTA WCU Tahunan'
        unique_together     = ('afiliasi', 'tahun')
        ordering            = ['afiliasi', 'tahun']
        indexes             = [
            models.Index(fields=['tahun']),
        ]

    def __str__(self):
        return f"{self.afiliasi.perguruan_tinggi.singkatan} — WCU {self.tahun}: overall={self.overall}"


class SintaDepartemen(models.Model):
    """
    Daftar departemen (program studi) per Perguruan Tinggi di SINTA.
    Satu baris = satu program studi pada satu PT.
    """

    afiliasi = models.ForeignKey(
        SintaAfiliasi, on_delete=models.CASCADE,
        related_name='departemen', verbose_name='SINTA Afiliasi'
    )

    # --- Identitas departemen ---
    nama            = models.CharField(max_length=300, verbose_name='Nama Departemen')
    jenjang         = models.CharField(max_length=10, blank=True, verbose_name='Jenjang (S1/S2/S3/D3)')
    kode_dept       = models.CharField(max_length=20, blank=True, db_index=True, verbose_name='Kode Departemen SINTA')
    url_profil      = models.URLField(max_length=500, blank=True, verbose_name='URL Profil SINTA')

    # --- SINTA Score ---
    sinta_score_overall      = models.BigIntegerField(default=0, verbose_name='SINTA Score Overall')
    sinta_score_3year        = models.BigIntegerField(default=0, verbose_name='SINTA Score 3Yr')
    sinta_score_productivity      = models.IntegerField(default=0, verbose_name='SINTA Score Productivity')
    sinta_score_productivity_3year= models.IntegerField(default=0, verbose_name='SINTA Score Productivity 3Yr')

    # --- Ringkasan SDM ---
    jumlah_authors  = models.PositiveIntegerField(default=0, verbose_name='Jumlah Authors')

    # --- Statistik Publikasi ---
    scopus_artikel  = models.IntegerField(default=0)
    scopus_sitasi   = models.IntegerField(default=0)
    gscholar_artikel= models.IntegerField(default=0)
    gscholar_sitasi = models.IntegerField(default=0)
    wos_artikel     = models.IntegerField(default=0)
    wos_sitasi      = models.IntegerField(default=0)

    # --- Distribusi Kuartil Scopus ---
    scopus_q1  = models.PositiveIntegerField(default=0)
    scopus_q2  = models.PositiveIntegerField(default=0)
    scopus_q3  = models.PositiveIntegerField(default=0)
    scopus_q4  = models.PositiveIntegerField(default=0)
    scopus_noq = models.PositiveIntegerField(default=0)

    # --- Research Radar ---
    research_conference = models.IntegerField(default=0)
    research_articles   = models.IntegerField(default=0)
    research_others     = models.IntegerField(default=0)

    # --- Tren Scopus (JSON: [{tahun, jumlah}, ...]) ---
    trend_scopus = models.JSONField(default=list, blank=True)

    # --- Metadata ---
    scraped_at = models.DateTimeField(auto_now=True, verbose_name='Waktu Scrape')

    class Meta:
        verbose_name        = 'SINTA Departemen'
        verbose_name_plural = 'SINTA Departemen'
        ordering            = ['-sinta_score_overall']
        unique_together     = ('afiliasi', 'kode_dept')
        indexes             = [
            models.Index(fields=['afiliasi', 'jenjang']),
            models.Index(fields=['sinta_score_overall']),
        ]

    def __str__(self):
        return f"{self.afiliasi.perguruan_tinggi.singkatan} — {self.jenjang} {self.nama}"


class SintaAuthor(models.Model):
    """
    Profil lengkap author SINTA (1 row per author unik).
    Data dari: /authors/profile/{sinta_id}
    """

    # --- Identitas ---
    sinta_id    = models.CharField(max_length=20, unique=True, db_index=True, verbose_name='SINTA ID Author')
    nama        = models.CharField(max_length=300, verbose_name='Nama Author')
    url_profil  = models.URLField(max_length=500, blank=True, verbose_name='URL Profil SINTA')
    foto_url    = models.URLField(max_length=500, blank=True, verbose_name='URL Foto')
    bidang_keilmuan = models.JSONField(default=list, blank=True, verbose_name='Bidang Keilmuan')

    # --- Relasi ke PT & Departemen ---
    afiliasi    = models.ForeignKey(
        SintaAfiliasi, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='authors', verbose_name='SINTA Afiliasi'
    )
    departemen  = models.ForeignKey(
        SintaDepartemen, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='authors', verbose_name='Departemen'
    )

    # --- SINTA Score ---
    sinta_score_overall = models.BigIntegerField(default=0, verbose_name='SINTA Score Overall')
    sinta_score_3year   = models.BigIntegerField(default=0, verbose_name='SINTA Score 3Yr')
    affil_score         = models.BigIntegerField(default=0, verbose_name='Affil Score')
    affil_score_3year   = models.BigIntegerField(default=0, verbose_name='Affil Score 3Yr')

    # --- Statistik Scopus ---
    scopus_artikel   = models.IntegerField(default=0)
    scopus_sitasi    = models.IntegerField(default=0)
    scopus_cited_doc = models.IntegerField(default=0)
    scopus_h_index   = models.SmallIntegerField(default=0)
    scopus_i10_index = models.SmallIntegerField(default=0)
    scopus_g_index   = models.SmallIntegerField(default=0)

    # --- Statistik Google Scholar ---
    gscholar_artikel   = models.IntegerField(default=0)
    gscholar_sitasi    = models.IntegerField(default=0)
    gscholar_cited_doc = models.IntegerField(default=0)
    gscholar_h_index   = models.SmallIntegerField(default=0)
    gscholar_i10_index = models.SmallIntegerField(default=0)
    gscholar_g_index   = models.SmallIntegerField(default=0)

    # --- Statistik Web of Science ---
    wos_artikel   = models.IntegerField(default=0)
    wos_sitasi    = models.IntegerField(default=0)
    wos_cited_doc = models.IntegerField(default=0)
    wos_h_index   = models.SmallIntegerField(default=0)
    wos_i10_index = models.SmallIntegerField(default=0)
    wos_g_index   = models.SmallIntegerField(default=0)

    # --- Distribusi Kuartil Scopus ---
    scopus_q1  = models.PositiveIntegerField(default=0)
    scopus_q2  = models.PositiveIntegerField(default=0)
    scopus_q3  = models.PositiveIntegerField(default=0)
    scopus_q4  = models.PositiveIntegerField(default=0)
    scopus_noq = models.PositiveIntegerField(default=0)

    # --- Research Radar ---
    research_conference = models.IntegerField(default=0)
    research_articles   = models.IntegerField(default=0)
    research_others     = models.IntegerField(default=0)

    # --- Metadata ---
    scraped_at = models.DateTimeField(auto_now=True, verbose_name='Waktu Scrape')

    class Meta:
        verbose_name        = 'SINTA Author'
        verbose_name_plural = 'SINTA Author'
        ordering            = ['-sinta_score_overall']
        indexes             = [
            models.Index(fields=['sinta_score_overall']),
            models.Index(fields=['afiliasi']),
            models.Index(fields=['departemen']),
        ]

    def __str__(self):
        return f"{self.nama} ({self.sinta_id})"


class SintaAuthorTrend(models.Model):
    """
    Tren tahunan per author: Scopus, penelitian, dan pengabdian.
    Hanya menyimpan tahun dengan jumlah > 0.
    """

    class Jenis(models.TextChoices):
        SCOPUS        = 'scopus',        'Publikasi Scopus'
        RESEARCH      = 'research',      'Penelitian'
        SERVICE       = 'service',       'Pengabdian'
        GSCHOLAR_PUB  = 'gscholar_pub',  'Publikasi Google Scholar'
        GSCHOLAR_CITE = 'gscholar_cite', 'Sitasi Google Scholar'

    author = models.ForeignKey(
        SintaAuthor, on_delete=models.CASCADE,
        related_name='trend', verbose_name='Author'
    )
    jenis  = models.CharField(max_length=20, choices=Jenis.choices, verbose_name='Jenis')
    tahun  = models.PositiveSmallIntegerField(verbose_name='Tahun')
    jumlah = models.PositiveIntegerField(default=0, verbose_name='Jumlah')

    class Meta:
        verbose_name        = 'SINTA Author Trend'
        verbose_name_plural = 'SINTA Author Trend'
        unique_together     = ('author', 'jenis', 'tahun')
        ordering            = ['author', 'jenis', 'tahun']
        indexes             = [
            models.Index(fields=['jenis', 'tahun']),
        ]

    def __str__(self):
        return f"{self.author.nama} — {self.jenis} {self.tahun}: {self.jumlah}"


class SintaAuthorPublication(models.Model):
    """
    Daftar publikasi milik author dari Google Scholar / Scopus / WoS.
    Setiap baris = satu karya unik per sumber.
    """

    class Sumber(models.TextChoices):
        GSCHOLAR = 'gscholar', 'Google Scholar'
        SCOPUS   = 'scopus',   'Scopus'
        WOS      = 'wos',      'Web of Science'

    author      = models.ForeignKey(
        SintaAuthor, on_delete=models.CASCADE,
        related_name='publications', verbose_name='Author'
    )
    sumber      = models.CharField(max_length=10, choices=Sumber.choices, verbose_name='Sumber')
    pub_id      = models.CharField(max_length=200, db_index=True, verbose_name='ID Publikasi')
    judul       = models.CharField(max_length=1000, verbose_name='Judul')
    penulis     = models.TextField(blank=True, verbose_name='Penulis')
    jurnal      = models.CharField(max_length=500, blank=True, verbose_name='Jurnal / Venue')
    tahun       = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Tahun')
    sitasi      = models.PositiveIntegerField(default=0, verbose_name='Jumlah Sitasi')
    url         = models.URLField(max_length=800, blank=True, verbose_name='URL')
    scraped_at  = models.DateTimeField(auto_now=True, verbose_name='Waktu Scrape')

    class Meta:
        verbose_name        = 'SINTA Author Publication'
        verbose_name_plural = 'SINTA Author Publications'
        unique_together     = ('author', 'sumber', 'pub_id')
        ordering            = ['-sitasi', '-tahun']
        indexes             = [
            models.Index(fields=['author', 'sumber']),
            models.Index(fields=['tahun']),
        ]

    def __str__(self):
        return f"{self.author.nama} — {self.judul[:60]}"


class SintaAuthorCitation(models.Model):
    """
    Daftar karya dari penulis lain yang mensitasi si author (citing articles).
    Data dari tab Google Scholar / Scopus profil author di SINTA.
    """

    class Sumber(models.TextChoices):
        GSCHOLAR = 'gscholar', 'Google Scholar'
        SCOPUS   = 'scopus',   'Scopus'

    author      = models.ForeignKey(
        SintaAuthor, on_delete=models.CASCADE,
        related_name='citations', verbose_name='Author Disitasi'
    )
    sumber      = models.CharField(max_length=10, choices=Sumber.choices, verbose_name='Sumber')
    cite_id     = models.CharField(max_length=200, db_index=True, verbose_name='ID Sitasi')
    judul       = models.CharField(max_length=1000, verbose_name='Judul Karya Pensitasi')
    penulis     = models.TextField(blank=True, verbose_name='Penulis')
    jurnal      = models.CharField(max_length=500, blank=True, verbose_name='Jurnal / Venue')
    tahun       = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Tahun')
    url         = models.URLField(max_length=800, blank=True, verbose_name='URL')
    scraped_at  = models.DateTimeField(auto_now=True, verbose_name='Waktu Scrape')

    class Meta:
        verbose_name        = 'SINTA Author Citation'
        verbose_name_plural = 'SINTA Author Citations'
        unique_together     = ('author', 'sumber', 'cite_id')
        ordering            = ['-tahun']
        indexes             = [
            models.Index(fields=['author', 'sumber']),
            models.Index(fields=['tahun']),
        ]

    def __str__(self):
        return f"→ {self.author.nama} ← {self.judul[:60]}"


class SintaScopusArtikel(models.Model):
    """
    Artikel Scopus unik (deduplikasi by EID).
    Satu baris = satu artikel, terlepas dari berapa author PTMA yang menulisnya.
    """

    class Kuartil(models.TextChoices):
        Q1   = 'Q1', 'Q1'
        Q2   = 'Q2', 'Q2'
        Q3   = 'Q3', 'Q3'
        Q4   = 'Q4', 'Q4'
        NONE = '',   'No Quartile'

    eid         = models.CharField(
        max_length=50, unique=True, db_index=True,
        verbose_name='Scopus EID'
    )  # contoh: 2-s2.0-85018240220
    judul       = models.CharField(max_length=1000, verbose_name='Judul')
    tahun       = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Tahun')
    sitasi      = models.PositiveIntegerField(default=0, verbose_name='Jumlah Sitasi')
    kuartil     = models.CharField(
        max_length=2, blank=True, choices=Kuartil.choices,
        verbose_name='Kuartil Jurnal'
    )
    jurnal_nama = models.CharField(max_length=500, blank=True, verbose_name='Nama Jurnal')
    jurnal_url  = models.URLField(max_length=400, blank=True, verbose_name='URL Jurnal Scopus')
    scopus_url  = models.URLField(max_length=600, blank=True, verbose_name='URL Artikel Scopus')
    scraped_at  = models.DateTimeField(auto_now=True, verbose_name='Waktu Scrape')

    class Meta:
        verbose_name        = 'Scopus Artikel'
        verbose_name_plural = 'Scopus Artikel'
        ordering            = ['-sitasi', '-tahun']
        indexes             = [
            models.Index(fields=['tahun']),
            models.Index(fields=['kuartil']),
        ]

    def __str__(self):
        return f"[{self.eid}] {self.judul[:80]}"


class SintaScopusArtikelAuthor(models.Model):
    """
    Relasi M2M antara artikel Scopus dengan author PTMA yang tercatat di SINTA.
    Satu baris = satu author menulis satu artikel.
    """

    artikel         = models.ForeignKey(
        SintaScopusArtikel, on_delete=models.CASCADE,
        related_name='artikel_authors', verbose_name='Artikel'
    )
    author          = models.ForeignKey(
        SintaAuthor, on_delete=models.CASCADE,
        related_name='scopus_artikels', verbose_name='Author'
    )
    urutan_penulis  = models.PositiveSmallIntegerField(
        default=0, verbose_name='Urutan Penulis'
    )  # "1 of 4" → 1
    total_penulis   = models.PositiveSmallIntegerField(
        default=0, verbose_name='Total Penulis'
    )  # "1 of 4" → 4
    nama_singkat    = models.CharField(
        max_length=100, blank=True, verbose_name='Nama Singkat'
    )  # "Nurfadly Z."

    class Meta:
        verbose_name        = 'Scopus Artikel Author'
        verbose_name_plural = 'Scopus Artikel Authors'
        unique_together     = ('artikel', 'author')
        ordering            = ['urutan_penulis']
        indexes             = [
            models.Index(fields=['author']),
        ]

    def __str__(self):
        return f"{self.author.nama} → {self.artikel.eid}"


class SintaCluster(models.Model):
    """
    Klasterisasi Perguruan Tinggi oleh Kemdikbud (2022–2024).
    Skor per 6 kategori penilaian dan total score.
    """

    class NamaCluster(models.TextChoices):
        MANDIRI = 'Cluster Mandiri', 'Cluster Mandiri'
        UTAMA   = 'Cluster Utama',   'Cluster Utama'
        MADYA   = 'Cluster Madya',   'Cluster Madya'
        PRATAMA = 'Cluster Pratama', 'Cluster Pratama'
        BINAAN  = 'Cluster Binaan',  'Cluster Binaan'

    afiliasi = models.OneToOneField(
        SintaAfiliasi, on_delete=models.CASCADE,
        related_name='cluster', verbose_name='SINTA Afiliasi'
    )

    cluster_name = models.CharField(
        max_length=30, blank=True,
        choices=NamaCluster.choices, db_index=True,
        verbose_name='Nama Cluster'
    )
    total_score = models.FloatField(default=0, verbose_name='Total Score')

    # Skor tertimbang per 6 kategori (nilai final setelah dikali bobot %)
    score_publication       = models.FloatField(default=0, verbose_name='Score Publication (25%)')
    score_hki               = models.FloatField(default=0, verbose_name='Score HKI (10%)')
    score_kelembagaan       = models.FloatField(default=0, verbose_name='Score Kelembagaan (15%)')
    score_research          = models.FloatField(default=0, verbose_name='Score Research (15%)')
    score_community_service = models.FloatField(default=0, verbose_name='Score Community Service (15%)')
    score_sdm               = models.FloatField(default=0, verbose_name='Score SDM (15%)')

    # Skor ternormal (sebelum dikalikan bobot)
    ternormal_publication       = models.FloatField(default=0, verbose_name='Ternormal Publication')
    ternormal_hki               = models.FloatField(default=0, verbose_name='Ternormal HKI')
    ternormal_kelembagaan       = models.FloatField(default=0, verbose_name='Ternormal Kelembagaan')
    ternormal_research          = models.FloatField(default=0, verbose_name='Ternormal Research')
    ternormal_community_service = models.FloatField(default=0, verbose_name='Ternormal Community Service')
    ternormal_sdm               = models.FloatField(default=0, verbose_name='Ternormal SDM')

    periode  = models.CharField(max_length=20, default='2022-2024', verbose_name='Periode Penilaian')
    scraped_at = models.DateTimeField(auto_now=True, verbose_name='Waktu Scrape')

    class Meta:
        verbose_name        = 'SINTA Cluster'
        verbose_name_plural = 'SINTA Cluster'
        ordering            = ['-total_score']
        indexes             = [
            models.Index(fields=['cluster_name']),
            models.Index(fields=['total_score']),
        ]

    def __str__(self):
        return f"{self.afiliasi.perguruan_tinggi.singkatan} — {self.cluster_name} ({self.total_score:.2f})"


class SintaClusterItem(models.Model):
    """
    Detail item kode penilaian klasterisasi (67 kode per PT).
    Contoh: AI1 (Artikel Q1), KI1 (Paten), P1 (Penelitian Hibah LN), DOS1 (Profesor).
    """

    cluster = models.ForeignKey(
        SintaCluster, on_delete=models.CASCADE,
        related_name='items', verbose_name='Cluster'
    )
    kode    = models.CharField(max_length=10, verbose_name='Kode Item')   # AI1, AN3, KI1, ...
    section = models.CharField(max_length=30, verbose_name='Seksi')       # publication, hki, ...
    nama    = models.CharField(max_length=200, verbose_name='Nama Item')
    bobot   = models.FloatField(default=0, verbose_name='Bobot')
    nilai   = models.FloatField(default=0, verbose_name='Nilai (dinormalisasi)')
    total   = models.FloatField(default=0, verbose_name='Total (nilai × bobot)')

    class Meta:
        verbose_name        = 'SINTA Cluster Item'
        verbose_name_plural = 'SINTA Cluster Items'
        unique_together     = ('cluster', 'kode')
        ordering            = ['cluster', 'section', 'kode']
        indexes             = [
            models.Index(fields=['kode']),
        ]

    def __str__(self):
        return f"{self.cluster.afiliasi.perguruan_tinggi.singkatan} — {self.kode}: {self.total}"


class SintaJurnal(models.Model):
    """
    Jurnal yang dimiliki/dikelola oleh suatu Perguruan Tinggi, terdaftar di SINTA.
    Satu baris = satu jurnal unik (berdasarkan sinta_id).
    """

    class Akreditasi(models.TextChoices):
        S1 = 'S1', 'S1'
        S2 = 'S2', 'S2'
        S3 = 'S3', 'S3'
        S4 = 'S4', 'S4'
        S5 = 'S5', 'S5'
        S6 = 'S6', 'S6'

    perguruan_tinggi = models.ForeignKey(
        'PerguruanTinggi', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='jurnal_sinta', verbose_name='Perguruan Tinggi'
    )

    # Identitas
    sinta_id      = models.PositiveIntegerField(unique=True, verbose_name='SINTA ID Jurnal')
    nama          = models.CharField(max_length=300, verbose_name='Nama Jurnal')
    p_issn        = models.CharField(max_length=20, blank=True, verbose_name='P-ISSN')
    e_issn        = models.CharField(max_length=20, blank=True, verbose_name='E-ISSN')
    akreditasi    = models.CharField(max_length=2, choices=Akreditasi.choices, blank=True,
                                     db_index=True, verbose_name='Akreditasi')
    subject_area  = models.CharField(max_length=200, blank=True, verbose_name='Subject Area (SINTA)')
    wcu_area      = models.CharField(max_length=200, blank=True, verbose_name='WCU Subject Area',
                                     help_text='Kelompok bidang sesuai standar WCU/QS (diisi manual atau ML)')
    afiliasi_teks = models.CharField(max_length=300, blank=True, verbose_name='Afiliasi (teks)')

    # Statistik
    impact       = models.FloatField(default=0, verbose_name='Impact')
    h5_index     = models.PositiveIntegerField(default=0, verbose_name='H5-Index')
    sitasi_5yr   = models.PositiveIntegerField(default=0, verbose_name='Sitasi 5 Tahun')
    sitasi_total = models.PositiveIntegerField(default=0, verbose_name='Sitasi Total')

    # Index flags
    is_scopus = models.BooleanField(default=False, verbose_name='Scopus Indexed')
    is_garuda = models.BooleanField(default=False, verbose_name='Garuda Indexed')

    # URL eksternal
    url_website = models.CharField(max_length=500, blank=True, verbose_name='URL Website')
    url_scholar = models.CharField(max_length=500, blank=True, verbose_name='URL Google Scholar')
    url_editor  = models.CharField(max_length=500, blank=True, verbose_name='URL Editor')
    url_garuda  = models.CharField(max_length=500, blank=True, verbose_name='URL Garuda')

    # Logo cover jurnal
    logo_base64 = models.TextField(blank=True, verbose_name='Logo (Base64)')

    scraped_at = models.DateTimeField(auto_now=True, verbose_name='Waktu Scrape')

    class Meta:
        verbose_name        = 'SINTA Jurnal'
        verbose_name_plural = 'SINTA Jurnal'
        ordering = ['-impact']
        indexes  = [
            models.Index(fields=['akreditasi']),
            models.Index(fields=['perguruan_tinggi', 'akreditasi']),
        ]

    def __str__(self):
        return f"{self.nama} ({self.akreditasi})"


class RisetAnalisisSnapshot(models.Model):
    """Snapshot hasil analisis riset (maks 4 record, FIFO)."""
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Dibuat pada')
    data       = models.JSONField(verbose_name='Data hasil analisis')

    MAX_HISTORY = 4

    class Meta:
        verbose_name        = 'Riset Analisis Snapshot'
        verbose_name_plural = 'Riset Analisis Snapshots'
        ordering            = ['-created_at']

    def __str__(self):
        return f"Snapshot #{self.pk} — {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    @classmethod
    def save_snapshot(cls, data: dict) -> 'RisetAnalisisSnapshot':
        """Simpan snapshot baru dan hapus yang melebihi MAX_HISTORY (FIFO)."""
        snap = cls.objects.create(data=data)
        # Hapus yang terlama jika melebihi batas
        old_ids = list(
            cls.objects.order_by('-created_at')
            .values_list('id', flat=True)[cls.MAX_HISTORY:]
        )
        if old_ids:
            cls.objects.filter(id__in=old_ids).delete()
        return snap

    @classmethod
    def latest(cls) -> 'RisetAnalisisSnapshot | None':
        return cls.objects.first()


class RisetLdaDeskripsi(models.Model):
    """Deskripsi AI per topik LDA — disimpan permanen di DB."""
    label      = models.CharField(max_length=255, unique=True, verbose_name='Label Topik')
    deskripsi  = models.TextField(verbose_name='Deskripsi AI')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Diperbarui')

    class Meta:
        verbose_name        = 'LDA Deskripsi'
        verbose_name_plural = 'LDA Deskripsi'
        ordering            = ['label']

    def __str__(self):
        return self.label
