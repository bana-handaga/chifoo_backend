"""Models for Monitoring app - Laporan, Indikator, dan Kepatuhan"""

from django.db import models
from django.contrib.auth import get_user_model
from apps.universities.models import PerguruanTinggi

User = get_user_model()


class KategoriIndikator(models.Model):
    """Kategori indikator monitoring"""
    nama = models.CharField(max_length=100)
    deskripsi = models.TextField(blank=True)
    urutan = models.PositiveIntegerField(default=0)
    icon = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ['urutan', 'nama']
        verbose_name = 'Kategori Indikator'

    def __str__(self):
        return self.nama


class Indikator(models.Model):
    """Indikator kinerja PT"""

    class TipeData(models.TextChoices):
        ANGKA = 'angka', 'Angka'
        PERSENTASE = 'persentase', 'Persentase'
        TEKS = 'teks', 'Teks'
        BOOLEAN = 'boolean', 'Ya/Tidak'
        FILE = 'file', 'File/Dokumen'

    kategori = models.ForeignKey(
        KategoriIndikator, on_delete=models.PROTECT, related_name='indikator'
    )
    kode = models.CharField(max_length=20, unique=True)
    nama = models.CharField(max_length=200)
    deskripsi = models.TextField(blank=True)
    tipe_data = models.CharField(max_length=20, choices=TipeData.choices)
    satuan = models.CharField(max_length=50, blank=True)
    nilai_minimum = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    nilai_maksimum = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    nilai_target = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_wajib = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    urutan = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['kategori__urutan', 'urutan', 'nama']
        verbose_name = 'Indikator'

    def __str__(self):
        return f"{self.kode} - {self.nama}"


class PeriodePelaporan(models.Model):
    """Periode pelaporan monitoring"""
    
    class StatusPeriode(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        AKTIF = 'aktif', 'Aktif'
        SELESAI = 'selesai', 'Selesai'
        ARSIP = 'arsip', 'Arsip'

    nama = models.CharField(max_length=100)
    tahun = models.PositiveIntegerField()
    semester = models.CharField(max_length=10, choices=[('ganjil', 'Ganjil'), ('genap', 'Genap')])
    tanggal_mulai = models.DateField()
    tanggal_selesai = models.DateField()
    status = models.CharField(max_length=10, choices=StatusPeriode.choices, default=StatusPeriode.DRAFT)
    deskripsi = models.TextField(blank=True)

    class Meta:
        ordering = ['-tahun', 'semester']
        verbose_name = 'Periode Pelaporan'

    def __str__(self):
        return f"{self.nama} ({self.tahun}/{self.semester})"


class LaporanPT(models.Model):
    """Laporan kinerja per PT per periode"""

    class StatusLaporan(models.TextChoices):
        BELUM = 'belum', 'Belum Dimulai'
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Dikirim'
        REVIEW = 'review', 'Dalam Review'
        APPROVED = 'approved', 'Disetujui'
        REJECTED = 'rejected', 'Ditolak'

    perguruan_tinggi = models.ForeignKey(
        PerguruanTinggi, on_delete=models.CASCADE, related_name='laporan'
    )
    periode = models.ForeignKey(
        PeriodePelaporan, on_delete=models.PROTECT, related_name='laporan'
    )
    status = models.CharField(
        max_length=20, choices=StatusLaporan.choices, default=StatusLaporan.BELUM
    )
    persentase_pengisian = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    skor_total = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='submitted_laporan'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_laporan'
    )
    catatan_reviewer = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['perguruan_tinggi', 'periode']
        ordering = ['-periode__tahun', 'perguruan_tinggi__nama']
        verbose_name = 'Laporan PT'

    def __str__(self):
        return f"{self.perguruan_tinggi.singkatan} - {self.periode.nama}"


class IsiLaporan(models.Model):
    """Isi data per indikator dalam laporan"""

    laporan = models.ForeignKey(LaporanPT, on_delete=models.CASCADE, related_name='isi')
    indikator = models.ForeignKey(Indikator, on_delete=models.PROTECT)
    nilai_teks = models.TextField(blank=True)
    nilai_angka = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    nilai_boolean = models.BooleanField(null=True, blank=True)
    file = models.FileField(upload_to='laporan_files/', null=True, blank=True)
    keterangan = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['laporan', 'indikator']
        verbose_name = 'Isi Laporan'

    def __str__(self):
        return f"{self.laporan} - {self.indikator.kode}"


class SnapshotLaporan(models.Model):
    """Snapshot perhitungan performa PT — satu baris per sesi generate."""
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    keterangan   = models.CharField(max_length=200, blank=True)
    total_pt     = models.IntegerField(default=0)

    class Meta:
        ordering = ['-dibuat_pada']
        verbose_name = 'Snapshot Laporan Performa'

    def __str__(self):
        return f"Snapshot {self.dibuat_pada.strftime('%d %b %Y %H:%M')} ({self.total_pt} PT)"


class SnapshotPerPT(models.Model):
    """Distribusi per-PT dalam satu snapshot."""
    snapshot          = models.ForeignKey(SnapshotLaporan, on_delete=models.CASCADE, related_name='per_pt')
    perguruan_tinggi  = models.ForeignKey(PerguruanTinggi, on_delete=models.CASCADE)

    # Prodi
    total_prodi       = models.IntegerField(default=0)
    prodi_per_jenjang = models.JSONField(default=dict)   # {"S1": 10, "S2": 3, …}

    # Dosen profil (dari ProfilDosen)
    total_dosen       = models.IntegerField(default=0)
    dosen_pria        = models.IntegerField(default=0)
    dosen_wanita      = models.IntegerField(default=0)
    dosen_per_jabatan    = models.JSONField(default=dict) # {"Profesor": 5, "Lektor": 40, …}
    dosen_per_pendidikan = models.JSONField(default=dict) # {"s3": 20, "s2": 50, …}
    dosen_per_status     = models.JSONField(default=dict) # {"Aktif": 100, …}
    dosen_per_ikatan     = models.JSONField(default=dict) # {"tetap": 80, "tidak_tetap": 20}

    # Mahasiswa aktif — 7 semester terakhir
    mhs_tren = models.JSONField(default=list)  # [{"periode": "2024/2025 Ganjil", "total": 1000}, …]

    class Meta:
        unique_together = [('snapshot', 'perguruan_tinggi')]
        ordering = ['perguruan_tinggi__nama']

    def __str__(self):
        return f"{self.perguruan_tinggi.singkatan} @ {self.snapshot_id}"


class Notifikasi(models.Model):
    """Notifikasi untuk PT"""

    class TipeNotifikasi(models.TextChoices):
        INFO = 'info', 'Informasi'
        WARNING = 'warning', 'Peringatan'
        DEADLINE = 'deadline', 'Tenggat Waktu'
        APPROVED = 'approved', 'Disetujui'
        REJECTED = 'rejected', 'Ditolak'

    perguruan_tinggi = models.ForeignKey(
        PerguruanTinggi, on_delete=models.CASCADE, related_name='notifikasi',
        null=True, blank=True
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='notifikasi',
        null=True, blank=True
    )
    tipe = models.CharField(max_length=20, choices=TipeNotifikasi.choices)
    judul = models.CharField(max_length=200)
    pesan = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notifikasi'

    def __str__(self):
        return f"{self.tipe} - {self.judul}"
