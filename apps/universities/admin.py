"""Admin configuration for Universities app"""

from django.contrib import admin
from .models import Wilayah, PerguruanTinggi, ProgramStudi, DataMahasiswa, DataDosen


@admin.register(Wilayah)
class WilayahAdmin(admin.ModelAdmin):
    list_display = ['kode', 'nama', 'provinsi']
    search_fields = ['nama', 'provinsi']


@admin.register(PerguruanTinggi)
class PerguruanTinggiAdmin(admin.ModelAdmin):
    list_display = ['kode_pt', 'singkatan', 'nama', 'jenis', 'organisasi_induk', 'kota', 'akreditasi_institusi', 'is_active']
    list_filter = ['jenis', 'organisasi_induk', 'akreditasi_institusi', 'is_active', 'wilayah']
    search_fields = ['nama', 'singkatan', 'kode_pt', 'kota']
    list_editable = ['is_active']


@admin.register(ProgramStudi)
class ProgramStudiAdmin(admin.ModelAdmin):
    list_display = ['kode_prodi', 'nama', 'jenjang', 'akreditasi', 'perguruan_tinggi', 'is_active']
    list_filter = ['jenjang', 'akreditasi', 'is_active']
    search_fields = ['nama', 'kode_prodi']


@admin.register(DataMahasiswa)
class DataMahasiswaAdmin(admin.ModelAdmin):
    list_display = ['perguruan_tinggi', 'tahun_akademik', 'semester', 'mahasiswa_aktif']
    list_filter = ['tahun_akademik', 'semester']


@admin.register(DataDosen)
class DataDosenAdmin(admin.ModelAdmin):
    list_display = ['perguruan_tinggi', 'program_studi', 'tahun_akademik', 'semester', 'dosen_tetap', 'dosen_tidak_tetap']
    list_filter = ['tahun_akademik', 'semester']
