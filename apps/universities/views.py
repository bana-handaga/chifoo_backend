"""Views for Universities app"""

from datetime import date, timedelta
from django.db.models import Count, Sum, Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter


class PT10Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 200

from .models import Wilayah, PerguruanTinggi, ProgramStudi, DataMahasiswa, DataDosen
from apps.monitoring.models import PeriodePelaporan
from .serializers import (
    WilayahSerializer, PerguruanTinggiListSerializer,
    PerguruanTinggiDetailSerializer, ProgramStudiSerializer,
    DataMahasiswaSerializer, DataDosenSerializer
)


class WilayahViewSet(viewsets.ModelViewSet):
    queryset = Wilayah.objects.all()
    serializer_class = WilayahSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['nama', 'provinsi']
    ordering_fields = ['nama', 'provinsi']


class PerguruanTinggiViewSet(viewsets.ModelViewSet):
    queryset = PerguruanTinggi.objects.select_related('wilayah').prefetch_related(
        'program_studi', 'program_studi__data_mahasiswa', 'data_mahasiswa', 'data_dosen'
    )
    permission_classes = [IsAuthenticatedOrReadOnly]
    pagination_class = PT10Pagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['jenis', 'organisasi_induk', 'wilayah', 'akreditasi_institusi', 'is_active', 'provinsi']
    search_fields = ['nama', 'singkatan', 'kota', 'provinsi', 'kode_pt']
    ordering_fields = ['nama', 'kota', 'akreditasi_institusi', 'created_at', 'mhs_sort']

    def get_serializer_class(self):
        if self.action == 'list':
            return PerguruanTinggiListSerializer
        return PerguruanTinggiDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Annotate mhs_sort berdasarkan periode aktif (sama dengan serializer)
        periode = PeriodePelaporan.objects.filter(status='aktif').first()
        if periode:
            if periode.semester == 'genap':
                tahun_akademik = f"{periode.tahun - 1}/{periode.tahun}"
            else:
                tahun_akademik = f"{periode.tahun}/{periode.tahun + 1}"
            mhs_filter = Q(
                data_mahasiswa__program_studi__isnull=False,
                data_mahasiswa__tahun_akademik=tahun_akademik,
                data_mahasiswa__semester=periode.semester,
            )
        else:
            mhs_filter = Q(data_mahasiswa__program_studi__isnull=False)
        qs = qs.annotate(mhs_sort=Sum('data_mahasiswa__mahasiswa_aktif', filter=mhs_filter))
        if not self.request.query_params.get('ordering'):
            qs = qs.order_by('-mhs_sort')
        exp_filter = self.request.query_params.get('exp_filter')
        if exp_filter:
            today = date.today()
            if exp_filter == 'more_1y':
                qs = qs.filter(tanggal_kadaluarsa_akreditasi__gt=today + timedelta(days=365))
            elif exp_filter == 'less_3m':
                qs = qs.filter(
                    tanggal_kadaluarsa_akreditasi__isnull=False,
                    tanggal_kadaluarsa_akreditasi__lte=today + timedelta(days=90)
                )
            elif exp_filter == 'less_2m':
                qs = qs.filter(
                    tanggal_kadaluarsa_akreditasi__isnull=False,
                    tanggal_kadaluarsa_akreditasi__lte=today + timedelta(days=60)
                )
            elif exp_filter == 'less_1m':
                qs = qs.filter(
                    tanggal_kadaluarsa_akreditasi__isnull=False,
                    tanggal_kadaluarsa_akreditasi__lte=today + timedelta(days=30)
                )
        return qs

    @action(detail=False, methods=['get'])
    def statistik(self, request):
        """Statistik keseluruhan PTMA"""
        # Gunakan semua PT (konsisten dengan endpoint list yang tidak memfilter is_active)
        qs = PerguruanTinggi.objects.all()

        # Filter opsional per wilayah (bisa multiple: ?wilayah_id=1&wilayah_id=2)
        wilayah_ids = request.query_params.getlist('wilayah_id')
        if wilayah_ids:
            qs = qs.filter(wilayah_id__in=wilayah_ids)

        total_pt = qs.count()
        total_muhammadiyah = qs.filter(organisasi_induk='muhammadiyah').count()
        total_aisyiyah = qs.filter(organisasi_induk='aisyiyah').count()

        per_jenis = qs.values('jenis').annotate(total=Count('id'))
        per_akreditasi = qs.values('akreditasi_institusi').annotate(total=Count('id'))
        per_wilayah = qs.values('wilayah__nama', 'wilayah__provinsi').annotate(
            total=Count('id')
        ).order_by('-total')[:5]

        pt_ids = qs.values_list('id', flat=True)
        total_prodi = ProgramStudi.objects.filter(is_active=True, perguruan_tinggi_id__in=pt_ids).count()

        # Hanya hitung dari data per program studi (program_studi tidak null)
        qs_mhs = DataMahasiswa.objects.filter(program_studi__isnull=False, perguruan_tinggi_id__in=pt_ids)

        # Gunakan periode pelaporan aktif sebagai acuan tahun/semester
        periode_aktif = PeriodePelaporan.objects.filter(status='aktif').first()
        total_mahasiswa = 0

        if periode_aktif:
            if periode_aktif.semester == 'genap':
                tahun_akademik = f"{periode_aktif.tahun - 1}/{periode_aktif.tahun}"
            else:
                tahun_akademik = f"{periode_aktif.tahun}/{periode_aktif.tahun + 1}"
            total_mahasiswa = qs_mhs.filter(
                tahun_akademik=tahun_akademik,
                semester=periode_aktif.semester,
            ).aggregate(total=Sum('mahasiswa_aktif'))['total'] or 0

        # Fallback jika tidak ada periode aktif atau datanya kosong
        if not total_mahasiswa:
            latest = qs_mhs.order_by('-tahun_akademik', '-semester').first()
            if latest:
                total_mahasiswa = qs_mhs.filter(
                    tahun_akademik=latest.tahun_akademik,
                    semester=latest.semester,
                ).aggregate(total=Sum('mahasiswa_aktif'))['total'] or 0

        # Total dosen: gunakan tahun_akademik + semester dari periode aktif, fallback ke terbaru
        qs_dosen = DataDosen.objects.filter(perguruan_tinggi_id__in=pt_ids)
        agg_dosen = {'tetap': None, 'tidak_tetap': None}
        tahun_dosen = None

        if periode_aktif and tahun_akademik:
            tahun_dosen = f"{tahun_akademik} {periode_aktif.semester.capitalize()}"
            agg_dosen = qs_dosen.filter(
                tahun_akademik=tahun_akademik,
                semester=periode_aktif.semester,
            ).aggregate(tetap=Sum('dosen_tetap'), tidak_tetap=Sum('dosen_tidak_tetap'))

        if not agg_dosen['tetap'] and not agg_dosen['tidak_tetap']:
            latest = qs_dosen.order_by('-tahun_akademik', 'semester').values(
                'tahun_akademik', 'semester'
            ).first()
            if latest:
                agg_dosen = qs_dosen.filter(
                    tahun_akademik=latest['tahun_akademik'],
                    semester=latest['semester'],
                ).aggregate(tetap=Sum('dosen_tetap'), tidak_tetap=Sum('dosen_tidak_tetap'))
                tahun_dosen = f"{latest['tahun_akademik']} {latest['semester'].capitalize()}"

        total_dosen = (agg_dosen['tetap'] or 0) + (agg_dosen['tidak_tetap'] or 0)
        total_dosen_tetap = agg_dosen['tetap'] or 0

        return Response({
            'total_pt': total_pt,
            'total_muhammadiyah': total_muhammadiyah,
            'total_aisyiyah': total_aisyiyah,
            'total_prodi': total_prodi,
            'total_mahasiswa': total_mahasiswa,
            'total_dosen': total_dosen,
            'total_dosen_tetap': total_dosen_tetap,
            'tahun_dosen': tahun_dosen,
            'per_jenis': list(per_jenis),
            'per_akreditasi': list(per_akreditasi),
            'per_wilayah': list(per_wilayah),
        })

    @action(detail=False, methods=['get'])
    def sebaran_peta(self, request):
        """Data sebaran PT untuk peta"""
        qs = PerguruanTinggi.objects.filter(
            is_active=True,
            latitude__isnull=False,
            longitude__isnull=False
        ).values(
            'id', 'nama', 'singkatan', 'jenis', 'organisasi_induk',
            'kota', 'provinsi', 'latitude', 'longitude', 'akreditasi_institusi'
        )
        return Response(list(qs))


class ProgramStudiViewSet(viewsets.ModelViewSet):
    queryset = ProgramStudi.objects.select_related('perguruan_tinggi')
    serializer_class = ProgramStudiSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['perguruan_tinggi', 'jenjang', 'akreditasi', 'is_active']
    search_fields = ['nama', 'kode_prodi']

    @action(detail=False, methods=['get'])
    def statistik_jenjang(self, request):
        """Statistik program studi per jenjang"""
        data = ProgramStudi.objects.filter(is_active=True).values('jenjang').annotate(
            total=Count('id')
        ).order_by('jenjang')
        return Response(list(data))


class DataMahasiswaViewSet(viewsets.ModelViewSet):
    queryset = DataMahasiswa.objects.select_related('perguruan_tinggi', 'program_studi')
    serializer_class = DataMahasiswaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['perguruan_tinggi', 'tahun_akademik', 'semester']
    ordering_fields = ['tahun_akademik', 'mahasiswa_aktif']


class DataDosenViewSet(viewsets.ModelViewSet):
    queryset = DataDosen.objects.select_related('perguruan_tinggi')
    serializer_class = DataDosenSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['perguruan_tinggi', 'tahun_akademik', 'semester']
    ordering_fields = ['tahun_akademik', 'dosen_tetap']
