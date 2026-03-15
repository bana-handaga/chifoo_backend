"""URLs for Universities app"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WilayahViewSet, PerguruanTinggiViewSet, 
    ProgramStudiViewSet, DataMahasiswaViewSet, DataDosenViewSet
)

router = DefaultRouter()
router.register(r'wilayah', WilayahViewSet, basename='wilayah')
router.register(r'perguruan-tinggi', PerguruanTinggiViewSet, basename='perguruan-tinggi')
router.register(r'program-studi', ProgramStudiViewSet, basename='program-studi')
router.register(r'data-mahasiswa', DataMahasiswaViewSet, basename='data-mahasiswa')
router.register(r'data-dosen', DataDosenViewSet, basename='data-dosen')

urlpatterns = [
    path('', include(router.urls)),
]
