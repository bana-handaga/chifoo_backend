"""Views for Monitoring app"""

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import (
    KategoriIndikator, Indikator, PeriodePelaporan,
    LaporanPT, IsiLaporan, Notifikasi
)
from .serializers import (
    KategoriIndikatorSerializer, IndikatorSerializer,
    PeriodePelaporanSerializer, LaporanPTListSerializer,
    LaporanPTDetailSerializer, IsiLaporanSerializer, NotifikasiSerializer
)


class PublicReadAuthWriteMixin:
    """GET/HEAD/OPTIONS bebas akses; metode tulis butuh autentikasi."""
    def get_permissions(self):
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return [AllowAny()]
        return [IsAuthenticated()]


class KategoriIndikatorViewSet(PublicReadAuthWriteMixin, viewsets.ModelViewSet):
    queryset = KategoriIndikator.objects.prefetch_related('indikator')
    serializer_class = KategoriIndikatorSerializer


class IndikatorViewSet(PublicReadAuthWriteMixin, viewsets.ModelViewSet):
    queryset = Indikator.objects.select_related('kategori')
    serializer_class = IndikatorSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['kategori', 'tipe_data', 'is_wajib', 'is_active']
    search_fields = ['kode', 'nama']


class PeriodePelaporanViewSet(PublicReadAuthWriteMixin, viewsets.ModelViewSet):
    queryset = PeriodePelaporan.objects.all()
    serializer_class = PeriodePelaporanSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['tahun', 'semester', 'status']

    @action(detail=False, methods=['get'])
    def aktif(self, request):
        """Periode pelaporan yang sedang aktif"""
        periode = PeriodePelaporan.objects.filter(status='aktif').first()
        if periode:
            return Response(PeriodePelaporanSerializer(periode).data)
        return Response({'detail': 'Tidak ada periode aktif'}, status=404)


class LaporanPTViewSet(viewsets.ModelViewSet):
    queryset = LaporanPT.objects.select_related(
        'perguruan_tinggi', 'periode', 'submitted_by', 'reviewed_by'
    ).prefetch_related('isi')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['perguruan_tinggi', 'periode', 'status']
    search_fields = ['perguruan_tinggi__nama', 'perguruan_tinggi__singkatan']
    ordering_fields = ['created_at', 'updated_at', 'skor_total', 'persentase_pengisian']

    def get_serializer_class(self):
        if self.action == 'list':
            return LaporanPTListSerializer
        return LaporanPTDetailSerializer

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit laporan untuk direview"""
        laporan = self.get_object()
        if laporan.status not in ['draft', 'rejected']:
            return Response(
                {'detail': 'Laporan tidak dapat disubmit pada status ini.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        laporan.status = 'submitted'
        laporan.submitted_at = timezone.now()
        laporan.submitted_by = request.user
        laporan.save()
        return Response({'detail': 'Laporan berhasil disubmit.'})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve laporan"""
        laporan = self.get_object()
        if laporan.status != 'submitted':
            return Response(
                {'detail': 'Hanya laporan yang disubmit yang dapat disetujui.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        laporan.status = 'approved'
        laporan.reviewed_at = timezone.now()
        laporan.reviewed_by = request.user
        laporan.catatan_reviewer = request.data.get('catatan', '')
        laporan.save()
        return Response({'detail': 'Laporan berhasil disetujui.'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject laporan"""
        laporan = self.get_object()
        if laporan.status != 'submitted':
            return Response(
                {'detail': 'Hanya laporan yang disubmit yang dapat ditolak.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        laporan.status = 'rejected'
        laporan.reviewed_at = timezone.now()
        laporan.reviewed_by = request.user
        laporan.catatan_reviewer = request.data.get('catatan', '')
        laporan.save()
        return Response({'detail': 'Laporan ditolak.'})

    @action(detail=False, methods=['get'])
    def rekap_kepatuhan(self, request):
        """Rekap kepatuhan pelaporan per periode"""
        periode_id = request.query_params.get('periode_id')
        qs = LaporanPT.objects.all()
        if periode_id:
            qs = qs.filter(periode_id=periode_id)

        total = qs.count()
        approved = qs.filter(status='approved').count()
        submitted = qs.filter(status='submitted').count()
        rejected = qs.filter(status='rejected').count()
        draft = qs.filter(status='draft').count()
        belum = qs.filter(status='belum').count()

        return Response({
            'total': total,
            'approved': approved,
            'submitted': submitted,
            'rejected': rejected,
            'draft': draft,
            'belum': belum,
            'persen_kepatuhan': round((approved + submitted) / total * 100, 2) if total > 0 else 0,
        })


class IsiLaporanViewSet(viewsets.ModelViewSet):
    queryset = IsiLaporan.objects.select_related('laporan', 'indikator')
    serializer_class = IsiLaporanSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['laporan', 'indikator', 'is_verified']


class NotifikasiViewSet(viewsets.ModelViewSet):
    serializer_class = NotifikasiSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notifikasi.objects.filter(user=self.request.user)

    @action(detail=False, methods=['post'])
    def tandai_baca_semua(self, request):
        """Tandai semua notifikasi sebagai sudah dibaca"""
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'detail': 'Semua notifikasi telah ditandai sebagai dibaca.'})
