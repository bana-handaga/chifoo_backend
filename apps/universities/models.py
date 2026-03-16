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
