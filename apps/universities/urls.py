"""URLs for Universities app"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WilayahViewSet, PerguruanTinggiViewSet,
    ProgramStudiViewSet, DataMahasiswaViewSet, DataDosenViewSet,
    banpt_prodi_search, dosen_stats, dosen_search, riwayat_pendidikan_search,
    prodi_distribusi, prodi_daftar, SintaJurnalViewSet, SintaAfiliasiViewSet,
    SintaDepartemenViewSet, SintaAuthorViewSet, SintaScopusArtikelViewSet,
    SintaPengabdianViewSet, SintaPenelitianViewSet, KolaboasiViewSet,
    proxy_image_b64,
    sync_jadwal_list, sync_jadwal_detail, sync_pt_list,
    sync_status, sync_jalankan, sync_hentikan,
)

router = DefaultRouter()
router.register(r'wilayah', WilayahViewSet, basename='wilayah')
router.register(r'perguruan-tinggi', PerguruanTinggiViewSet, basename='perguruan-tinggi')
router.register(r'program-studi', ProgramStudiViewSet, basename='program-studi')
router.register(r'data-mahasiswa', DataMahasiswaViewSet, basename='data-mahasiswa')
router.register(r'data-dosen', DataDosenViewSet, basename='data-dosen')
router.register(r'sinta-jurnal',    SintaJurnalViewSet,    basename='sinta-jurnal')
router.register(r'sinta-afiliasi',    SintaAfiliasiViewSet,    basename='sinta-afiliasi')
router.register(r'sinta-departemen', SintaDepartemenViewSet, basename='sinta-departemen')
router.register(r'sinta-author',         SintaAuthorViewSet,         basename='sinta-author')
router.register(r'sinta-scopus-artikel', SintaScopusArtikelViewSet,  basename='sinta-scopus-artikel')
router.register(r'sinta-pengabdian',    SintaPengabdianViewSet,     basename='sinta-pengabdian')
router.register(r'sinta-penelitian',    SintaPenelitianViewSet,     basename='sinta-penelitian')
router.register(r'sinta-kolaborasi',    KolaboasiViewSet,            basename='sinta-kolaborasi')

urlpatterns = [
    path('', include(router.urls)),
    path('banpt-prodi-search/', banpt_prodi_search, name='banpt-prodi-search'),
    path('dosen-stats/', dosen_stats, name='dosen-stats'),
    path('dosen-search/', dosen_search, name='dosen-search'),
    path('riwayat-pendidikan/', riwayat_pendidikan_search, name='riwayat-pendidikan'),
    path('prodi-distribusi/', prodi_distribusi, name='prodi-distribusi'),
    path('prodi-daftar/', prodi_daftar, name='prodi-daftar'),
    path('proxy-image/', proxy_image_b64, name='proxy-image'),
    path('sync/jadwal/', sync_jadwal_list, name='sync-jadwal-list'),
    path('sync/jadwal/<int:pk>/', sync_jadwal_detail, name='sync-jadwal-detail'),
    path('sync/jadwal/<int:pk>/status/', sync_status, name='sync-status'),
    path('sync/jadwal/<int:pk>/jalankan/', sync_jalankan, name='sync-jalankan'),
    path('sync/jadwal/<int:pk>/hentikan/', sync_hentikan, name='sync-hentikan'),
    path('sync/pt-list/', sync_pt_list, name='sync-pt-list'),
]
