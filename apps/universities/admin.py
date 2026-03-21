"""Admin configuration for Universities app"""

from django.contrib import admin
from .models import (
    Wilayah, PerguruanTinggi, ProgramStudi, DataMahasiswa, DataDosen,
    SintaAfiliasi, SintaTrendTahunan, SintaWcuTahunan, SintaCluster, SintaClusterItem,
    SintaJurnal,
)


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


@admin.register(SintaAfiliasi)
class SintaAfiliasiAdmin(admin.ModelAdmin):
    list_display = [
        'perguruan_tinggi', 'sinta_id', 'sinta_score_overall', 'sinta_score_3year',
        'jumlah_authors', 'scopus_dokumen', 'scopus_sitasi',
        'scopus_q1', 'scopus_q2', 'scopus_q3', 'scopus_q4', 'scraped_at',
    ]
    list_filter  = ['scraped_at']
    search_fields = ['perguruan_tinggi__nama', 'perguruan_tinggi__singkatan', 'sinta_id']
    readonly_fields = ['scraped_at', 'logo_base64']


@admin.register(SintaTrendTahunan)
class SintaTrendTahunanAdmin(admin.ModelAdmin):
    list_display  = ['afiliasi', 'jenis', 'tahun', 'jumlah', 'research_article', 'research_conference', 'research_others']
    list_filter   = ['jenis', 'tahun']
    search_fields = ['afiliasi__perguruan_tinggi__nama']


@admin.register(SintaWcuTahunan)
class SintaWcuTahunanAdmin(admin.ModelAdmin):
    list_display  = ['afiliasi', 'tahun', 'overall', 'engineering_technology', 'social_sciences_management',
                     'natural_sciences', 'life_sciences_medicine', 'arts_humanities']
    list_filter   = ['tahun']
    search_fields = ['afiliasi__perguruan_tinggi__nama']


class SintaClusterItemInline(admin.TabularInline):
    model  = SintaClusterItem
    extra  = 0
    fields = ['kode', 'section', 'nama', 'bobot', 'nilai', 'total']


@admin.register(SintaCluster)
class SintaClusterAdmin(admin.ModelAdmin):
    list_display   = ['afiliasi', 'cluster_name', 'total_score',
                      'score_publication', 'score_hki', 'score_kelembagaan',
                      'score_research', 'score_community_service', 'score_sdm']
    list_filter    = ['cluster_name']
    search_fields  = ['afiliasi__perguruan_tinggi__nama']
    readonly_fields = ['scraped_at']
    inlines        = [SintaClusterItemInline]


@admin.register(SintaClusterItem)
class SintaClusterItemAdmin(admin.ModelAdmin):
    list_display  = ['cluster', 'kode', 'section', 'nama', 'bobot', 'nilai', 'total']
    list_filter   = ['section']
    search_fields = ['kode', 'nama', 'cluster__afiliasi__perguruan_tinggi__nama']


@admin.register(SintaJurnal)
class SintaJurnalAdmin(admin.ModelAdmin):
    list_display   = ['nama', 'perguruan_tinggi', 'akreditasi', 'impact', 'h5_index',
                      'sitasi_total', 'is_scopus', 'is_garuda']
    list_filter    = ['akreditasi', 'is_scopus', 'is_garuda']
    search_fields  = ['nama', 'p_issn', 'e_issn', 'perguruan_tinggi__nama']
    readonly_fields = ['scraped_at', 'logo_base64']
