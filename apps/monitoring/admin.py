"""Admin configuration for Monitoring app"""

from django.contrib import admin
from .models import KategoriIndikator, Indikator, PeriodePelaporan, LaporanPT, IsiLaporan, Notifikasi


@admin.register(KategoriIndikator)
class KategoriIndikatorAdmin(admin.ModelAdmin):
    list_display = ['nama', 'urutan']
    ordering = ['urutan']


@admin.register(Indikator)
class IndikatorAdmin(admin.ModelAdmin):
    list_display = ['kode', 'nama', 'kategori', 'tipe_data', 'is_wajib', 'is_active']
    list_filter = ['kategori', 'tipe_data', 'is_wajib', 'is_active']
    search_fields = ['kode', 'nama']


@admin.register(PeriodePelaporan)
class PeriodePelaporanAdmin(admin.ModelAdmin):
    list_display = ['nama', 'tahun', 'semester', 'status', 'tanggal_mulai', 'tanggal_selesai']
    list_filter = ['tahun', 'semester', 'status']


@admin.register(LaporanPT)
class LaporanPTAdmin(admin.ModelAdmin):
    list_display = ['perguruan_tinggi', 'periode', 'status', 'persentase_pengisian', 'submitted_at']
    list_filter = ['status', 'periode']
    search_fields = ['perguruan_tinggi__nama']


@admin.register(Notifikasi)
class NotifikasiAdmin(admin.ModelAdmin):
    list_display = ['tipe', 'judul', 'perguruan_tinggi', 'is_read', 'created_at']
    list_filter = ['tipe', 'is_read']
