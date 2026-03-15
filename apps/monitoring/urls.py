"""URLs for Monitoring app"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    KategoriIndikatorViewSet, IndikatorViewSet, PeriodePelaporanViewSet,
    LaporanPTViewSet, IsiLaporanViewSet, NotifikasiViewSet
)

router = DefaultRouter()
router.register(r'kategori-indikator', KategoriIndikatorViewSet, basename='kategori-indikator')
router.register(r'indikator', IndikatorViewSet, basename='indikator')
router.register(r'periode-pelaporan', PeriodePelaporanViewSet, basename='periode-pelaporan')
router.register(r'laporan-pt', LaporanPTViewSet, basename='laporan-pt')
router.register(r'isi-laporan', IsiLaporanViewSet, basename='isi-laporan')
router.register(r'notifikasi', NotifikasiViewSet, basename='notifikasi')

urlpatterns = [
    path('', include(router.urls)),
]
