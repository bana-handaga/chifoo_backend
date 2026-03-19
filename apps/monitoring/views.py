"""Views for Monitoring app"""

from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from collections import defaultdict

from django.db.models import Count, Sum, Q

from apps.universities.models import (
    PerguruanTinggi, ProgramStudi, ProfilDosen, DataMahasiswa
)

from .models import (
    KategoriIndikator, Indikator, PeriodePelaporan,
    LaporanPT, IsiLaporan, Notifikasi,
    SnapshotLaporan, SnapshotPerPT,
)
from .serializers import (
    KategoriIndikatorSerializer, IndikatorSerializer,
    PeriodePelaporanSerializer, LaporanPTListSerializer,
    LaporanPTDetailSerializer, IsiLaporanSerializer, NotifikasiSerializer,
    SnapshotLaporanSerializer, SnapshotLaporanListSerializer,
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


# ─────────────────────────────────────────────────────────────────
# Helper: hitung semua distribusi dan simpan ke SnapshotLaporan
# ─────────────────────────────────────────────────────────────────

def _compute_snapshot(keterangan: str = '') -> SnapshotLaporan:
    """Hitung semua distribusi per-PT dan simpan snapshot baru."""

    # 1. 7 semester terakhir berdasarkan DataMahasiswa
    semesters = list(
        DataMahasiswa.objects
        .values_list('tahun_akademik', 'semester')
        .distinct()
        .order_by('-tahun_akademik', '-semester')[:7]
    )

    # 2. Kumpulkan semua query sekaligus (bulk)
    prodi_qs = (
        ProgramStudi.objects.filter(is_active=True)
        .values('perguruan_tinggi_id', 'jenjang')
        .annotate(n=Count('id'))
    )
    gender_qs = (
        ProfilDosen.objects
        .values('perguruan_tinggi_id', 'jenis_kelamin')
        .annotate(n=Count('id'))
    )
    jabatan_qs = (
        ProfilDosen.objects
        .values('perguruan_tinggi_id', 'jabatan_fungsional')
        .annotate(n=Count('id'))
    )
    pendidikan_qs = (
        ProfilDosen.objects
        .values('perguruan_tinggi_id', 'pendidikan_tertinggi')
        .annotate(n=Count('id'))
    )
    status_qs = (
        ProfilDosen.objects
        .values('perguruan_tinggi_id', 'status')
        .annotate(n=Count('id'))
    )
    ikatan_qs = (
        ProfilDosen.objects
        .values('perguruan_tinggi_id', 'ikatan_kerja')
        .annotate(n=Count('id'))
    )

    ta_list  = [s[0] for s in semesters]
    sem_list = [s[1] for s in semesters]
    mhs_qs = (
        DataMahasiswa.objects
        .filter(tahun_akademik__in=ta_list, semester__in=sem_list)
        .values('perguruan_tinggi_id', 'tahun_akademik', 'semester')
        .annotate(total=Sum('mahasiswa_aktif'))
    ) if semesters else []

    # 3. Indeks per PT_id
    prodi_idx    = defaultdict(dict)
    gender_idx   = defaultdict(lambda: {'L': 0, 'P': 0})
    jabatan_idx  = defaultdict(dict)
    pend_idx     = defaultdict(dict)
    status_idx   = defaultdict(dict)
    ikatan_idx   = defaultdict(dict)
    mhs_idx      = defaultdict(dict)   # pt_id → {(ta, sem): total}

    for r in prodi_qs:
        prodi_idx[r['perguruan_tinggi_id']][r['jenjang'] or ''] = r['n']
    for r in gender_qs:
        gender_idx[r['perguruan_tinggi_id']][r['jenis_kelamin'] or ''] = r['n']
    for r in jabatan_qs:
        jabatan_idx[r['perguruan_tinggi_id']][r['jabatan_fungsional'] or ''] = r['n']
    for r in pendidikan_qs:
        pend_idx[r['perguruan_tinggi_id']][r['pendidikan_tertinggi'] or ''] = r['n']
    for r in status_qs:
        status_idx[r['perguruan_tinggi_id']][r['status'] or ''] = r['n']
    for r in ikatan_qs:
        ikatan_idx[r['perguruan_tinggi_id']][r['ikatan_kerja'] or ''] = r['n']
    for r in mhs_qs:
        mhs_idx[r['perguruan_tinggi_id']][(r['tahun_akademik'], r['semester'])] = r['total'] or 0

    # 4. Daftar semua PT aktif
    all_pt = list(PerguruanTinggi.objects.filter(is_active=True).values_list('id', flat=True))

    # 5. Simpan snapshot
    snap = SnapshotLaporan.objects.create(keterangan=keterangan, total_pt=len(all_pt))

    bulk = []
    for pt_id in all_pt:
        g = gender_idx[pt_id]
        pria   = g.get('L', 0)
        wanita = g.get('P', 0)
        total_dosen = sum(g.values())

        # Tren 7 semester — urut dari lama ke baru
        tren = []
        for ta, sem in reversed(semesters):
            tren.append({
                'periode': f"{ta} {sem.capitalize()}",
                'total': mhs_idx[pt_id].get((ta, sem), 0),
            })

        bulk.append(SnapshotPerPT(
            snapshot_id          = snap.id,
            perguruan_tinggi_id  = pt_id,
            total_prodi          = sum(prodi_idx[pt_id].values()),
            prodi_per_jenjang    = prodi_idx[pt_id],
            total_dosen          = total_dosen,
            dosen_pria           = pria,
            dosen_wanita         = wanita,
            dosen_per_jabatan    = jabatan_idx[pt_id],
            dosen_per_pendidikan = pend_idx[pt_id],
            dosen_per_status     = status_idx[pt_id],
            dosen_per_ikatan     = ikatan_idx[pt_id],
            mhs_tren             = tren,
        ))

    SnapshotPerPT.objects.bulk_create(bulk)
    return snap


# ─────────────────────────────────────────────────────────────────
# ViewSet: SnapshotLaporan
# ─────────────────────────────────────────────────────────────────

class SnapshotLaporanViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/snapshot-laporan/         → daftar 10 snapshot terbaru
    POST /api/snapshot-laporan/generate/ → hitung & simpan snapshot baru
    GET  /api/snapshot-laporan/<id>/    → detail + per_pt
    """
    queryset = SnapshotLaporan.objects.all()[:10]

    def get_permissions(self):
        return [AllowAny()]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SnapshotLaporanSerializer
        return SnapshotLaporanListSerializer

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        keterangan = request.data.get('keterangan', '')
        snap = _compute_snapshot(keterangan)
        return Response(
            SnapshotLaporanSerializer(snap).data,
            status=status.HTTP_201_CREATED,
        )
