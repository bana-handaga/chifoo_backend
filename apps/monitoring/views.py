"""Views for Monitoring app"""

from django.utils import timezone
from django.db.models.functions import TruncWeek
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

    # ── Jenjang prodi yang dikenal ────────────────────────────────
    JENJANG_KNOWN = {'s1', 's2', 's3', 'd3', 'd4', 'profesi', 'sp-1'}

    # ── 1. 7 semester terakhir ────────────────────────────────────
    semesters = list(
        DataMahasiswa.objects
        .values_list('tahun_akademik', 'semester')
        .distinct()
        .order_by('-tahun_akademik', '-semester')[:7]
    )
    # urut dari lama → baru untuk kolom sem_1..sem_7
    semesters_asc = list(reversed(semesters))

    # ── 2. Agregasi bulk ──────────────────────────────────────────
    prodi_qs = (
        ProgramStudi.objects.filter(is_active=True)
        .values('perguruan_tinggi_id', 'jenjang')
        .annotate(n=Count('id'))
    )
    prodi_total_qs = (
        ProgramStudi.objects
        .values('perguruan_tinggi_id')
        .annotate(n=Count('id'))
    )
    gender_qs = (
        ProfilDosen.objects
        .values('perguruan_tinggi_id', 'jenis_kelamin')
        .annotate(n=Count('id'))
    )
    detail_qs = (
        ProfilDosen.objects
        .values('perguruan_tinggi_id')
        .annotate(
            with_detail=Count('id', filter=Q(jabatan_fungsional__gt='')),
        )
    )
    # DataDosen aggregate — ambil semester terbaru untuk total dosen per PT
    from apps.universities.models import DataDosen as _DataDosen
    _latest_dd = (
        _DataDosen.objects
        .order_by('-tahun_akademik', '-semester')
        .values('tahun_akademik', 'semester')
        .first()
    )
    datadosen_idx: dict = {}
    if _latest_dd:
        for r in (
            _DataDosen.objects
            .filter(tahun_akademik=_latest_dd['tahun_akademik'], semester=_latest_dd['semester'])
            .values('perguruan_tinggi_id')
            .annotate(total=Sum('dosen_tetap') + Sum('dosen_tidak_tetap'))
        ):
            datadosen_idx[r['perguruan_tinggi_id']] = r['total'] or 0
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

    # ── 3. Indeks per PT_id ───────────────────────────────────────
    prodi_idx       = defaultdict(dict)
    prodi_total_idx = defaultdict(int)
    gender_idx  = defaultdict(lambda: {'L': 0, 'P': 0})
    detail_idx  = defaultdict(lambda: {'with': 0})
    jabatan_idx = defaultdict(dict)
    pend_idx    = defaultdict(dict)
    status_idx  = defaultdict(dict)
    ikatan_idx  = defaultdict(dict)
    mhs_idx     = defaultdict(dict)  # pt_id → {(ta, sem): total}

    for r in prodi_qs:
        prodi_idx[r['perguruan_tinggi_id']][r['jenjang'] or ''] = r['n']
    for r in prodi_total_qs:
        prodi_total_idx[r['perguruan_tinggi_id']] = r['n']
    for r in gender_qs:
        gender_idx[r['perguruan_tinggi_id']][r['jenis_kelamin'] or ''] = r['n']
    for r in detail_qs:
        detail_idx[r['perguruan_tinggi_id']] = {'with': r['with_detail']}
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

    # ── 4. Daftar semua PT (aktif & tidak aktif) ──────────────────
    aktif_pt_ids    = set(PerguruanTinggi.objects.filter(is_active=True).values_list('id', flat=True))
    all_pt          = list(PerguruanTinggi.objects.values_list('id', flat=True))
    tidak_aktif     = len(all_pt) - len(aktif_pt_ids)

    # Auto-generate keterangan jika tidak diisi
    if not keterangan:
        keterangan = (
            f"{len(aktif_pt_ids)} dari {len(all_pt)} PT aktif"
            + (f" ({tidak_aktif} PT tidak aktif/dinonaktifkan)" if tidak_aktif else "")
        )

    # ── 5. Hapus snapshot minggu ini jika sudah ada (overwrite) ───
    now = timezone.now()
    # Awal minggu = Senin pagi pukul 00:00 waktu lokal (UTC)
    week_start = now - timezone.timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    SnapshotLaporan.objects.filter(dibuat_pada__gte=week_start).delete()

    # ── 6. Buat snapshot & bulk_create rows ───────────────────────
    snap = SnapshotLaporan.objects.create(keterangan=keterangan, total_pt=len(aktif_pt_ids), total_pt_non_aktif=tidak_aktif)

    bulk = []
    for pt_id in all_pt:
        g = gender_idx[pt_id]
        pria        = g.get('L', 0)
        wanita      = g.get('P', 0)
        # total_dosen dari DataDosen aggregate (lebih akurat dari ProfilDosen yg di-scrape)
        total_dosen = datadosen_idx.get(pt_id, 0)
        gender_no_info = max(0, total_dosen - pria - wanita)

        # Prodi per jenjang
        pj = prodi_idx[pt_id]
        prodi_lainnya = sum(v for k, v in pj.items() if (k or '').lower() not in JENJANG_KNOWN)

        # Jabatan fungsional — lainnya = total_dosen - yg sudah diketahui
        jab = jabatan_idx[pt_id]
        jab_lainnya = max(0, total_dosen - jab.get('Profesor', 0) - jab.get('Lektor Kepala', 0)
                         - jab.get('Lektor', 0) - jab.get('Asisten Ahli', 0))

        # Pendidikan — lainnya = total_dosen - yg sudah diketahui
        pend = pend_idx[pt_id]
        pend_lainnya = max(0, total_dosen - pend.get('s3', 0) - pend.get('s2', 0)
                          - pend.get('s1', 0) - pend.get('profesi', 0))

        # Status — lainnya = total_dosen - yg sudah diketahui
        sts = status_idx[pt_id]
        sts_lainnya = max(0, total_dosen - sts.get('Aktif', 0) - sts.get('TUGAS BELAJAR', 0)
                         - sts.get('IJIN BELAJAR', 0) - sts.get('CUTI', 0))

        # Ikatan kerja — lainnya = total_dosen - yg sudah diketahui
        ik = ikatan_idx[pt_id]
        ik_lainnya = max(0, total_dosen - ik.get('tetap', 0) - ik.get('tidak_tetap', 0)
                        - ik.get('dtpk', 0))

        # Mhs tren — isi kolom sem_1..sem_7 (terlama → terbaru)
        mhs_fields = {}
        for i, (ta, sem) in enumerate(semesters_asc, 1):
            mhs_fields[f'mhs_label_{i}'] = f"{ta} {sem.capitalize()}"
            mhs_fields[f'mhs_sem_{i}']   = mhs_idx[pt_id].get((ta, sem), 0)
        # Isi kolom yang tidak ada semester (jika < 7 semester tersedia)
        for i in range(len(semesters_asc) + 1, 8):
            mhs_fields[f'mhs_label_{i}'] = ''
            mhs_fields[f'mhs_sem_{i}']   = 0

        prodi_aktif_count = sum(pj.values())
        prodi_total       = prodi_total_idx[pt_id]
        prodi_non_aktif   = max(0, prodi_total - prodi_aktif_count)
        bulk.append(SnapshotPerPT(
            snapshot_id           = snap.id,
            perguruan_tinggi_id   = pt_id,
            total_prodi           = prodi_total,
            prodi_aktif           = prodi_aktif_count,
            prodi_non_aktif       = prodi_non_aktif,
            prodi_s1              = pj.get('s1', 0),
            prodi_s2              = pj.get('s2', 0),
            prodi_s3              = pj.get('s3', 0),
            prodi_d3              = pj.get('d3', 0),
            prodi_d4              = pj.get('d4', 0),
            prodi_profesi         = pj.get('profesi', 0),
            prodi_sp1             = pj.get('Sp-1', 0),
            prodi_jenjang_lainnya = prodi_lainnya,
            total_dosen           = total_dosen,
            dosen_with_detail     = detail_idx[pt_id]['with'],
            dosen_no_detail       = max(0, datadosen_idx.get(pt_id, total_dosen) - detail_idx[pt_id]['with']),
            dosen_pria            = pria,
            dosen_wanita          = wanita,
            dosen_gender_no_info  = gender_no_info,
            dosen_profesor        = jab.get('Profesor', 0),
            dosen_lektor_kepala   = jab.get('Lektor Kepala', 0),
            dosen_lektor          = jab.get('Lektor', 0),
            dosen_asisten_ahli    = jab.get('Asisten Ahli', 0),
            dosen_jabatan_lainnya = jab_lainnya,
            dosen_pend_s3         = pend.get('s3', 0),
            dosen_pend_s2         = pend.get('s2', 0),
            dosen_pend_s1         = pend.get('s1', 0),
            dosen_pend_profesi    = pend.get('profesi', 0),
            dosen_pend_lainnya    = pend_lainnya,
            dosen_aktif           = sts.get('Aktif', 0),
            dosen_tugas_belajar   = sts.get('TUGAS BELAJAR', 0),
            dosen_ijin_belajar    = sts.get('IJIN BELAJAR', 0),
            dosen_cuti            = sts.get('CUTI', 0),
            dosen_status_lainnya  = sts_lainnya,
            dosen_tetap           = ik.get('tetap', 0),
            dosen_tidak_tetap     = ik.get('tidak_tetap', 0),
            dosen_dtpk            = ik.get('dtpk', 0),
            dosen_ikatan_lainnya  = ik_lainnya,
            **mhs_fields,
        ))

    SnapshotPerPT.objects.bulk_create(bulk)
    return snap


# ─────────────────────────────────────────────────────────────────
# ViewSet: SnapshotLaporan
# ─────────────────────────────────────────────────────────────────

class SnapshotLaporanViewSet(viewsets.ModelViewSet):
    """
    GET  /api/snapshot-laporan/         → daftar 10 snapshot terbaru
    POST /api/snapshot-laporan/generate/ → hitung & simpan snapshot baru
    GET  /api/snapshot-laporan/<id>/    → detail + per_pt
    """
    queryset = SnapshotLaporan.objects.all()

    def get_permissions(self):
        return [AllowAny()]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SnapshotLaporanSerializer
        return SnapshotLaporanListSerializer

    def list(self, request, *args, **kwargs):
        qs = SnapshotLaporan.objects.all()[:10]
        serializer = SnapshotLaporanListSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        keterangan = request.data.get('keterangan', '')
        snap = _compute_snapshot(keterangan)
        return Response(
            SnapshotLaporanSerializer(snap).data,
            status=status.HTTP_201_CREATED,
        )
