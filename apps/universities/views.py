"""Views for Universities app"""

import json, os, re
from difflib import SequenceMatcher
from pathlib import Path
from datetime import date, timedelta
from django.db.models import Count, Sum, Q, Case, When, Value, IntegerField
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, AllowAny, IsAdminUser
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_BANPT_PRODI_PATH = _BASE_DIR / 'public' / 'media' / 'banpt_prodi_akreditasi.json'
_banpt_prodi_cache: list | None = None

def _load_banpt_prodi():
    global _banpt_prodi_cache
    if _banpt_prodi_cache is None:
        with open(_BANPT_PRODI_PATH, encoding='utf-8') as f:
            _banpt_prodi_cache = json.load(f)
    return _banpt_prodi_cache

_STOPWORDS = {'dan', 'atau', 'di', 'ke', 'dari', 'untuk', 'the', 'of', 'and', 'in'}

def _normalize(text: str) -> str:
    return re.sub(r'[^a-z0-9 ]', '', text.lower().strip())

def _tokens(text: str) -> set:
    return {w for w in _normalize(text).split() if w not in _STOPWORDS}

def _similarity(query: str, candidate: str) -> float:
    """Gabungan skor: SequenceMatcher + token overlap, nilai 0–1."""
    q_norm = _normalize(query)
    c_norm = _normalize(candidate)
    seq_score   = SequenceMatcher(None, q_norm, c_norm).ratio()
    q_tok, c_tok = _tokens(query), _tokens(candidate)
    union = q_tok | c_tok
    tok_score = len(q_tok & c_tok) / len(union) if union else 0.0
    return round(0.5 * seq_score + 0.5 * tok_score, 4)

_JENJANG_RE = re.compile(
    r'\b(?:Diploma\s*([1-4])|D([1-4])|S([1-3])|Sp\-?([12])|Profesi)\b', re.IGNORECASE)

def _extract_jenjang(raw: str) -> str:
    """Ekstrak kode jenjang dari string apapun, misal 'Sarjana (S1)' → 'S1', 'Diploma 3' → 'D3'."""
    m = _JENJANG_RE.search(raw)
    if not m:
        return raw.strip().upper()
    d_long, d_short, s_num, sp_num = m.group(1), m.group(2), m.group(3), m.group(4)
    if d_long:  return f'D{d_long}'
    if d_short: return f'D{d_short}'
    if s_num:   return f'S{s_num}'
    if sp_num:  return f'Sp{sp_num}'
    return 'Profesi'

@api_view(['GET'])
@permission_classes([AllowAny])
def banpt_prodi_search(request):
    """Cari data akreditasi prodi dari BAN-PT dengan fuzzy matching nama + jenjang."""
    nama    = request.query_params.get('nama', '').strip()
    jenjang = _extract_jenjang(request.query_params.get('jenjang', ''))
    if not nama:
        return Response([])
    try:
        data = _load_banpt_prodi()
    except FileNotFoundError:
        return Response([])

    scored = []
    for r in data:
        sim = _similarity(nama, r.get('nama_prodi', ''))
        # bonus 0.15 jika kode jenjang cocok
        if jenjang and jenjang == r.get('jenjang', '').upper():
            sim = min(1.0, sim + 0.15)
        if sim >= 0.25:
            scored.append((sim, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    hasil = []
    for sim, r in scored[:5]:
        item = dict(r)
        item['similarity'] = round(sim * 100)
        hasil.append(item)
    return Response(hasil)


class PT10Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 500

from .models import Wilayah, PerguruanTinggi, ProgramStudi, DataMahasiswa, DataDosen, ProfilDosen, RiwayatPendidikanDosen
from django.db.models import OuterRef, Subquery
from .serializers import _get_periode_aktif
from apps.monitoring.models import PeriodePelaporan
from .serializers import (
    WilayahSerializer, PerguruanTinggiListSerializer,
    PerguruanTinggiDetailSerializer, ProgramStudiSerializer,
    DataMahasiswaSerializer, DataDosenSerializer
)


class PublicReadAdminWriteMixin:
    """GET/HEAD/OPTIONS bebas akses; metode tulis butuh admin (is_staff)."""
    def get_permissions(self):
        if self.request.method in ('GET', 'HEAD', 'OPTIONS'):
            return [AllowAny()]
        return [IsAdminUser()]


class WilayahViewSet(PublicReadAdminWriteMixin, viewsets.ModelViewSet):
    queryset = Wilayah.objects.all().order_by('nama')
    serializer_class = WilayahSerializer
    pagination_class = None
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['nama', 'provinsi']
    ordering_fields = ['nama', 'provinsi']


class PerguruanTinggiViewSet(PublicReadAdminWriteMixin, viewsets.ModelViewSet):
    queryset = PerguruanTinggi.objects.select_related('wilayah').prefetch_related(
        'program_studi', 'program_studi__data_mahasiswa', 'program_studi__data_dosen',
        'data_mahasiswa', 'data_dosen'
    )
    pagination_class = PT10Pagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['jenis', 'organisasi_induk', 'wilayah', 'akreditasi_institusi', 'is_active', 'provinsi']
    search_fields = ['nama', 'singkatan', 'kota', 'provinsi', 'kode_pt']
    ordering_fields = ['nama', 'kode_pt', 'kota', 'akreditasi_institusi',
                       'tanggal_kadaluarsa_akreditasi', 'created_at', 'mhs_sort', 'dosen_sort']

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
                data_mahasiswa__program_studi__is_active=True,
                data_mahasiswa__tahun_akademik=tahun_akademik,
                data_mahasiswa__semester=periode.semester,
            )
            dsn_filter = Q(
                data_dosen__tahun_akademik=tahun_akademik,
                data_dosen__semester=periode.semester,
            )
        else:
            mhs_filter = Q(data_mahasiswa__program_studi__is_active=True)
            dsn_filter = Q()
        qs = qs.annotate(
            mhs_sort=Sum('data_mahasiswa__mahasiswa_aktif', filter=mhs_filter),
            dosen_sort=Sum('data_dosen__dosen_tetap', filter=dsn_filter),
        )
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
        ).order_by('-total')

        pt_ids = qs.values_list('id', flat=True)
        total_prodi = ProgramStudi.objects.filter(is_active=True, perguruan_tinggi_id__in=pt_ids).count()

        # Gunakan periode pelaporan aktif sebagai acuan tahun/semester
        periode_aktif = PeriodePelaporan.objects.filter(status='aktif').order_by('-tahun', 'semester').first()
        total_mahasiswa = 0
        tahun_akademik = None
        periode_label = None

        if periode_aktif:
            if periode_aktif.semester == 'genap':
                tahun_akademik = f"{periode_aktif.tahun - 1}/{periode_aktif.tahun}"
            else:
                tahun_akademik = f"{periode_aktif.tahun}/{periode_aktif.tahun + 1}"
            periode_label = f"{tahun_akademik} {periode_aktif.semester.capitalize()}"
            # Gunakan program_studi_id__in (konsisten dengan endpoint grouping)
            prodi_ids = ProgramStudi.objects.filter(
                is_active=True, perguruan_tinggi_id__in=pt_ids
            ).values_list('id', flat=True)
            total_mahasiswa = DataMahasiswa.objects.filter(
                program_studi_id__in=prodi_ids,
                tahun_akademik=tahun_akademik,
                semester=periode_aktif.semester,
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

        # Top 7 PT by mahasiswa aktif
        top_mhs = []
        if tahun_akademik and periode_aktif:
            mhs_q = Q(
                data_mahasiswa__program_studi__is_active=True,
                data_mahasiswa__tahun_akademik=tahun_akademik,
                data_mahasiswa__semester=periode_aktif.semester,
            )
            top_mhs = list(
                qs.annotate(mhs_total=Sum('data_mahasiswa__mahasiswa_aktif', filter=mhs_q))
                  .filter(mhs_total__gt=0)
                  .order_by('-mhs_total')
                  .values('singkatan', 'nama', 'mhs_total')[:7]
            )

        # Top 7 PT by prodi aktif
        top_prodi = list(
            qs.annotate(prodi_total=Count('program_studi', filter=Q(program_studi__is_active=True)))
              .filter(prodi_total__gt=0)
              .order_by('-prodi_total')
              .values('singkatan', 'nama', 'prodi_total')[:7]
        )

        # Top 7 PT by dosen tetap
        top_dosen = []
        if tahun_akademik and periode_aktif:
            dsn_q = Q(
                data_dosen__tahun_akademik=tahun_akademik,
                data_dosen__semester=periode_aktif.semester,
            )
            top_dosen = list(
                qs.annotate(dsn_total=Sum('data_dosen__dosen_tetap', filter=dsn_q))
                  .filter(dsn_total__gt=0)
                  .order_by('-dsn_total')
                  .values('singkatan', 'nama', 'dsn_total')[:7]
            )

        total_dosen_with_detail = ProfilDosen.objects.filter(
            perguruan_tinggi_id__in=pt_ids,
            jabatan_fungsional__gt='',
        ).count()

        return Response({
            'total_pt': total_pt,
            'total_muhammadiyah': total_muhammadiyah,
            'total_aisyiyah': total_aisyiyah,
            'total_prodi': total_prodi,
            'total_mahasiswa': total_mahasiswa,
            'periode_label': periode_label,
            'total_dosen': total_dosen,
            'total_dosen_tetap': total_dosen_tetap,
            'total_dosen_with_detail': total_dosen_with_detail,
            'tahun_dosen': tahun_dosen,
            'per_jenis': list(per_jenis),
            'per_akreditasi': list(per_akreditasi),
            'per_wilayah': list(per_wilayah),
            'top_mhs': top_mhs,
            'top_prodi': top_prodi,
            'top_dosen': top_dosen,
        })

    @action(detail=False, methods=['get'])
    def tren_mahasiswa(self, request):
        """
        Tren mahasiswa aktif 12 semester terakhir.
        Params:
          pt_id[]    - filter PT (bisa multiple)
          prodi_id[] - filter Prodi (bisa multiple)
          mode       - 'gabung' | 'perbandingan'
          filter_by  - 'pt' | 'prodi' (konteks perbandingan, default 'pt')
        """
        sem_order = Case(
            When(semester='ganjil', then=Value(1)),
            When(semester='genap', then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
        semesters = list(
            DataMahasiswa.objects
            .exclude(tahun_akademik='2017/2018')
            .values('tahun_akademik', 'semester')
            .distinct()
            .annotate(sem_order=sem_order)
            .order_by('tahun_akademik', 'sem_order')
        )
        labels = [f"{s['tahun_akademik']} {s['semester'].capitalize()}" for s in semesters]

        pt_ids    = request.query_params.getlist('pt_id')
        prodi_ids = request.query_params.getlist('prodi_id')
        mode      = request.query_params.get('mode', 'gabung')
        filter_by = request.query_params.get('filter_by', 'pt')  # 'pt' | 'prodi'
        metric    = request.query_params.get('metric', 'aktif')  # 'aktif'|'baru'|'lulus'|'dropout'

        METRIC_FIELD = {
            'aktif':   'mahasiswa_aktif',
            'baru':    'mahasiswa_baru',
            'lulus':   'mahasiswa_lulus',
            'dropout': 'mahasiswa_dropout',
        }
        metric_field = METRIC_FIELD.get(metric, 'mahasiswa_aktif')

        def _base_qs(s, extra_filter=None):
            qs = DataMahasiswa.objects.filter(
                tahun_akademik=s['tahun_akademik'],
                semester=s['semester'],
            )
            if pt_ids:
                qs = qs.filter(perguruan_tinggi_id__in=pt_ids)
            if prodi_ids:
                qs = qs.filter(program_studi_id__in=prodi_ids)
            if extra_filter:
                qs = qs.filter(**extra_filter)
            return qs.aggregate(total=Sum(metric_field))['total'] or 0

        if mode == 'perbandingan':
            datasets = []
            if filter_by == 'prodi':
                from apps.universities.models import ProgramStudi
                if not prodi_ids:
                    # auto-pilih top 10 prodi berdasarkan total mahasiswa aktif
                    top_qs = ProgramStudi.objects.filter(is_active=True)
                    if pt_ids:
                        top_qs = top_qs.filter(perguruan_tinggi_id__in=pt_ids)
                    top_qs = top_qs.annotate(
                        total_mhs=Sum(f'data_mahasiswa__{metric_field}')
                    ).order_by('-total_mhs')[:10]
                    prodi_ids = [str(p.id) for p in top_qs]
                for pid in prodi_ids:
                    try:
                        prodi = ProgramStudi.objects.select_related('perguruan_tinggi').get(pk=pid)
                    except ProgramStudi.DoesNotExist:
                        continue
                    label = f"{prodi.nama} ({prodi.jenjang}) — {prodi.perguruan_tinggi.singkatan or ''}"
                    data_points = []
                    for s in semesters:
                        qs = DataMahasiswa.objects.filter(
                            program_studi_id=pid,
                            tahun_akademik=s['tahun_akademik'],
                            semester=s['semester'],
                        )
                        if pt_ids:
                            qs = qs.filter(perguruan_tinggi_id__in=pt_ids)
                        data_points.append(qs.aggregate(total=Sum(metric_field))['total'] or 0)
                    datasets.append({'label': label, 'data': data_points})
            elif pt_ids:  # filter_by == 'pt'
                for pt_id in pt_ids:
                    try:
                        pt = PerguruanTinggi.objects.get(pk=pt_id)
                    except PerguruanTinggi.DoesNotExist:
                        continue
                    data_points = []
                    for s in semesters:
                        qs = DataMahasiswa.objects.filter(
                            perguruan_tinggi_id=pt_id,
                            tahun_akademik=s['tahun_akademik'],
                            semester=s['semester'],
                        )
                        if prodi_ids:
                            qs = qs.filter(program_studi_id__in=prodi_ids)
                        data_points.append(qs.aggregate(total=Sum(metric_field))['total'] or 0)
                    datasets.append({'label': pt.singkatan or pt.nama, 'data': data_points})
            if not datasets:
                # fallback gabung
                data_points = [_base_qs(s) for s in semesters]
                datasets = [{'label': 'Semua PT', 'data': data_points}]
            return Response({'labels': labels, 'datasets': datasets, 'mode': 'perbandingan'})
        else:
            # Mode gabung
            data_points = [_base_qs(s) for s in semesters]
            label = 'Semua PT'
            if pt_ids and len(pt_ids) == 1:
                try:
                    pt = PerguruanTinggi.objects.get(pk=pt_ids[0])
                    label = pt.singkatan or pt.nama
                except PerguruanTinggi.DoesNotExist:
                    pass
            elif pt_ids:
                label = f'{len(pt_ids)} PT (gabung)'
            if prodi_ids:
                label += f' · {len(prodi_ids)} Prodi'
            return Response({'labels': labels, 'datasets': [{'label': label, 'data': data_points}], 'mode': 'gabung'})

    @action(detail=False, methods=['get'])
    def estimasi_mahasiswa(self, request):
        """
        Estimasi mahasiswa baru / lulus per tahun akademik.
        Rumus: baru_est(T) = Σ [ aktif_ganjil(T, jenjang) / masa_studi(jenjang) ]
                lulus_est(T) = baru_est(T - 4)
        Params:
          metric    - 'baru' | 'lulus'  (default: 'baru')
          pt_id[]   - filter PT
          prodi_id[]- filter Prodi
          mode      - 'gabung' | 'perbandingan'
          filter_by - 'pt' | 'prodi'
        """
        MASA_STUDI = {
            's1': 4, 's2': 2, 's3': 3,
            'd4': 4, 'd3': 3, 'd2': 2, 'd1': 1,
            'profesi': 1,
        }
        DEFAULT_MS = 4

        pt_ids    = request.query_params.getlist('pt_id')
        prodi_ids = request.query_params.getlist('prodi_id')
        mode      = request.query_params.get('mode', 'gabung')
        filter_by = request.query_params.get('filter_by', 'pt')
        metric    = request.query_params.get('metric', 'baru')  # 'baru' | 'lulus'

        # Tahun akademik ganjil yang tersedia (exclude 2017/2018)
        tahun_list = list(
            DataMahasiswa.objects
            .filter(semester='ganjil')
            .exclude(tahun_akademik='2017/2018')
            .values_list('tahun_akademik', flat=True)
            .distinct()
            .order_by('tahun_akademik')
        )

        def _baru_est(tahun, extra_filter=None):
            """Hitung estimasi mahasiswa baru untuk satu tahun akademik."""
            qs = DataMahasiswa.objects.filter(
                semester='ganjil',
                tahun_akademik=tahun,
                mahasiswa_aktif__gt=0,
            )
            if pt_ids:
                qs = qs.filter(perguruan_tinggi_id__in=pt_ids)
            if prodi_ids:
                qs = qs.filter(program_studi_id__in=prodi_ids)
            if extra_filter:
                qs = qs.filter(**extra_filter)
            rows = qs.values('program_studi__jenjang').annotate(total=Sum('mahasiswa_aktif'))
            total = 0
            for r in rows:
                ms = MASA_STUDI.get(r['program_studi__jenjang'] or '', DEFAULT_MS)
                total += round(r['total'] / ms)
            return total

        def _lulus_est(tahun, extra_filter=None):
            thn = int(tahun[:4])
            thn_masuk = f'{thn - DEFAULT_MS}/{thn - DEFAULT_MS + 1}'
            if thn_masuk not in tahun_list:
                return 0
            return _baru_est(thn_masuk, extra_filter)

        def _data_for(tahun, extra_filter=None):
            return _baru_est(tahun, extra_filter) if metric == 'baru' else _lulus_est(tahun, extra_filter)

        labels = tahun_list

        if mode == 'perbandingan':
            datasets = []
            if filter_by == 'prodi':
                from apps.universities.models import ProgramStudi
                if not prodi_ids:
                    top_qs = ProgramStudi.objects.filter(is_active=True)
                    if pt_ids:
                        top_qs = top_qs.filter(perguruan_tinggi_id__in=pt_ids)
                    top_qs = top_qs.annotate(
                        total_mhs=Sum('data_mahasiswa__mahasiswa_aktif')
                    ).order_by('-total_mhs')[:10]
                    prodi_ids = [str(p.id) for p in top_qs]
                for pid in prodi_ids:
                    try:
                        prodi = ProgramStudi.objects.select_related('perguruan_tinggi').get(pk=pid)
                    except ProgramStudi.DoesNotExist:
                        continue
                    lbl = f"{prodi.nama} ({prodi.jenjang}) — {prodi.perguruan_tinggi.singkatan or ''}"
                    data_points = [_data_for(t, {'program_studi_id': pid}) for t in tahun_list]
                    datasets.append({'label': lbl, 'data': data_points})
            elif pt_ids:
                for pt_id in pt_ids:
                    try:
                        pt = PerguruanTinggi.objects.get(pk=pt_id)
                    except PerguruanTinggi.DoesNotExist:
                        continue
                    data_points = [_data_for(t, {'perguruan_tinggi_id': pt_id}) for t in tahun_list]
                    datasets.append({'label': pt.singkatan or pt.nama, 'data': data_points})
            if not datasets:
                datasets = [{'label': 'Semua PT (gabung)', 'data': [_data_for(t) for t in tahun_list]}]
        else:
            data_points = [_data_for(t) for t in tahun_list]
            if pt_ids and len(pt_ids) == 1:
                try:
                    pt = PerguruanTinggi.objects.get(pk=pt_ids[0])
                    label = pt.singkatan or pt.nama
                except PerguruanTinggi.DoesNotExist:
                    label = 'Semua PT'
            elif pt_ids:
                label = f'{len(pt_ids)} PT (gabung)'
            else:
                label = 'Semua PT'
            if prodi_ids:
                label += f' · {len(prodi_ids)} Prodi'
            datasets = [{'label': label, 'data': data_points}]

        suffix = ' *(estimasi)'
        for ds in datasets:
            ds['label'] += suffix

        return Response({
            'labels':   labels,
            'datasets': datasets,
            'metric':   metric,
            'note':     'Angka adalah estimasi statistik, bukan data pelaporan PDDikti.',
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


class ProgramStudiViewSet(PublicReadAdminWriteMixin, viewsets.ModelViewSet):
    queryset = ProgramStudi.objects.select_related('perguruan_tinggi')
    serializer_class = ProgramStudiSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['perguruan_tinggi', 'jenjang', 'akreditasi', 'is_active']
    search_fields = ['nama', 'kode_prodi', 'perguruan_tinggi__nama', 'perguruan_tinggi__singkatan']

    @action(detail=False, methods=['get'])
    def pt_list(self, request):
        """Daftar PT yang memiliki prodi dengan nama + jenjang tertentu."""
        try:
            return self._pt_list_inner(request)
        except Exception as e:
            import traceback
            return Response({'error': str(e), 'trace': traceback.format_exc()}, status=500)

    def _pt_list_inner(self, request):
        nama    = request.query_params.get('nama', '').strip()
        jenjang = request.query_params.get('jenjang', '').strip()
        qs = ProgramStudi.objects.filter(is_active=True)
        if nama:
            qs = qs.filter(nama__icontains=nama)
        if jenjang:
            qs = qs.filter(jenjang=jenjang)
        rows = list(
            qs
            .select_related('perguruan_tinggi')
            .order_by('perguruan_tinggi__nama')
            .values(
                'id', 'nama', 'jenjang', 'kode_prodi', 'akreditasi', 'no_sk_akreditasi', 'tanggal_kedaluarsa_akreditasi',
                'perguruan_tinggi__id', 'perguruan_tinggi__kode_pt',
                'perguruan_tinggi__nama', 'perguruan_tinggi__singkatan',
                'perguruan_tinggi__kota', 'perguruan_tinggi__provinsi',
                'perguruan_tinggi__akreditasi_institusi',
            )
        )

        # Ambil periode aktif untuk data mahasiswa & dosen
        periode = PeriodePelaporan.objects.filter(status='aktif').order_by('-tahun', 'semester').first()
        prodi_ids = [r['id'] for r in rows]

        mhs_map = {}
        dsn_map = {}
        if periode and prodi_ids:
            if periode.semester == 'genap':
                ta = f"{periode.tahun - 1}/{periode.tahun}"
            else:
                ta = f"{periode.tahun}/{periode.tahun + 1}"

            for m in DataMahasiswa.objects.filter(
                program_studi_id__in=prodi_ids,
                tahun_akademik=ta,
                semester=periode.semester,
            ).values('program_studi_id', 'mahasiswa_aktif'):
                mhs_map[m['program_studi_id']] = m['mahasiswa_aktif']

            for d in DataDosen.objects.filter(
                program_studi_id__in=prodi_ids,
                tahun_akademik=ta,
                semester=periode.semester,
            ).values('program_studi_id', 'dosen_tetap'):
                dsn_map[d['program_studi_id']] = d['dosen_tetap']

        AKREDITASI_LABEL = dict(ProgramStudi.StatusAkreditasi.choices)
        result = [
            {
                'prodi_id':           r['id'],
                'nama_prodi':         r['nama'],
                'jenjang':            r['jenjang'].upper() if r['jenjang'] else '',
                'kode_prodi':         r['kode_prodi'],
                'akreditasi':         r['akreditasi'],
                'akreditasi_display': AKREDITASI_LABEL.get(r['akreditasi'], r['akreditasi']),
                'no_sk':              r['no_sk_akreditasi'],
                'tgl_exp':            r['tanggal_kedaluarsa_akreditasi'],
                'pt_id':              r['perguruan_tinggi__id'],
                'kode_pt':            r['perguruan_tinggi__kode_pt'],
                'nama_pt':            r['perguruan_tinggi__nama'],
                'singkatan':          r['perguruan_tinggi__singkatan'],
                'kota':               r['perguruan_tinggi__kota'],
                'provinsi':           r['perguruan_tinggi__provinsi'],
                'akr_institusi':      r['perguruan_tinggi__akreditasi_institusi'],
                'mahasiswa_aktif':    mhs_map.get(r['id'], 0),
                'dosen_tetap':        dsn_map.get(r['id'], 0),
            }
            for r in rows
        ]
        result.sort(key=lambda x: x['mahasiswa_aktif'], reverse=True)
        return Response(result)

    @action(detail=False, methods=['get'])
    def statistik_jenjang(self, request):
        """Statistik program studi per jenjang"""
        data = ProgramStudi.objects.filter(is_active=True).values('jenjang').annotate(
            total=Count('id')
        ).order_by('jenjang')
        return Response(list(data))

    @action(detail=False, methods=['get'])
    def grouping(self, request):
        """Pengelompokan prodi berdasarkan nama + jenjang"""
        jenjang = request.query_params.get('jenjang', '')
        search  = request.query_params.get('search', '').strip()
        qs = ProgramStudi.objects.filter(is_active=True)
        if jenjang:
            qs = qs.filter(jenjang=jenjang)
        if search:
            qs = qs.filter(nama__icontains=search)
        # Query 1: jumlah PT unik per (nama, jenjang) — tanpa JOIN mahasiswa
        # Gunakan nama asli untuk tampilan, key lowercase untuk lookup aman
        pt_rows = list(
            qs.values('nama', 'jenjang')
              .annotate(jumlah_pt=Count('perguruan_tinggi_id', distinct=True))
        )
        # {(nama_lower, jenjang): (nama_asli, jumlah_pt)}
        pt_counts = {
            (r['nama'].lower(), r['jenjang']): (r['nama'], r['jumlah_pt'])
            for r in pt_rows
        }

        # Query 2 & 3: mahasiswa dan dosen per (nama, jenjang) — periode aktif
        # Key dinormalisasi lowercase agar cocok meski beda kapitalisasi
        periode = PeriodePelaporan.objects.filter(status='aktif').order_by('-tahun', 'semester').first()
        mhs_map: dict = {}
        dsn_map: dict = {}
        periode_label_g = None
        if periode:
            ta = (f"{periode.tahun - 1}/{periode.tahun}" if periode.semester == 'genap'
                  else f"{periode.tahun}/{periode.tahun + 1}")
            periode_label_g = f"{ta} {periode.semester.capitalize()}"
            prodi_ids = qs.values_list('id', flat=True)

            # Mahasiswa
            for r in (DataMahasiswa.objects
                      .filter(program_studi_id__in=prodi_ids,
                              tahun_akademik=ta, semester=periode.semester)
                      .values('program_studi__nama', 'program_studi__jenjang')
                      .annotate(total=Sum('mahasiswa_aktif'))):
                key = (r['program_studi__nama'].lower(), r['program_studi__jenjang'])
                mhs_map[key] = mhs_map.get(key, 0) + (r['total'] or 0)

            # Dosen tetap + tidak tetap
            for r in (DataDosen.objects
                      .filter(program_studi_id__in=prodi_ids,
                              tahun_akademik=ta, semester=periode.semester)
                      .values('program_studi__nama', 'program_studi__jenjang')
                      .annotate(total=Sum('dosen_tetap') + Sum('dosen_tidak_tetap'))):
                key = (r['program_studi__nama'].lower(), r['program_studi__jenjang'])
                dsn_map[key] = dsn_map.get(key, 0) + (r['total'] or 0)

        JENJANG_LABEL    = dict(ProgramStudi.Jenjang.choices)
        AKREDITASI_LABEL = dict(ProgramStudi.StatusAkreditasi.choices)
        result = [
            {
                'nama': nama_asli,
                'jenjang': jenjang,
                'jenjang_display': JENJANG_LABEL.get(jenjang, jenjang),
                'jumlah_pt': jumlah_pt,
                'total_mahasiswa': mhs_map.get((nama_lower, jenjang), 0),
                'total_dosen': dsn_map.get((nama_lower, jenjang), 0),
            }
            for (nama_lower, jenjang), (nama_asli, jumlah_pt) in pt_counts.items()
        ]

        # Query 3: sebaran akreditasi (dari qs yang sudah terfilter)
        akr_rows = (
            qs.values('akreditasi')
              .annotate(count=Count('id'))
              .order_by('-count')
        )
        akr_summary = [
            {
                'akreditasi': r['akreditasi'],
                'label': AKREDITASI_LABEL.get(r['akreditasi'], r['akreditasi'] or 'Belum'),
                'count': r['count'],
            }
            for r in akr_rows
        ]
        return Response({'groups': result, 'akr_summary': akr_summary, 'periode_label': periode_label_g})


class DataMahasiswaViewSet(PublicReadAdminWriteMixin, viewsets.ModelViewSet):
    queryset = DataMahasiswa.objects.select_related('perguruan_tinggi', 'program_studi')
    serializer_class = DataMahasiswaSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['perguruan_tinggi', 'tahun_akademik', 'semester']
    ordering_fields = ['tahun_akademik', 'mahasiswa_aktif']


class DataDosenViewSet(PublicReadAdminWriteMixin, viewsets.ModelViewSet):
    queryset = DataDosen.objects.select_related('perguruan_tinggi')
    serializer_class = DataDosenSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['perguruan_tinggi', 'tahun_akademik', 'semester']
    ordering_fields = ['tahun_akademik', 'dosen_tetap']


@api_view(['GET'])
@permission_classes([AllowAny])
def dosen_stats(request):
    """Statistik profil dosen untuk halaman infografik."""
    qs = ProfilDosen.objects.all()

    total         = qs.count()
    total_tetap       = qs.filter(ikatan_kerja='tetap').count()
    total_tidak_tetap = qs.filter(ikatan_kerja='tidak_tetap').count()
    total_dtpk        = qs.filter(ikatan_kerja='dtpk').count()
    total_profesor = qs.filter(jabatan_fungsional='Profesor').count()
    total_s3      = qs.filter(pendidikan_tertinggi='s3').count()
    total_aktif         = qs.filter(status='Aktif').count()
    total_tugas_belajar = qs.filter(status='TUGAS BELAJAR').count()
    total_ijin_belajar  = qs.filter(status='IJIN BELAJAR').count()
    total_cuti          = qs.filter(status='CUTI').count()

    # S3 luar negeri / dalam negeri dari RiwayatPendidikanDosen
    total_s3_ln = RiwayatPendidikanDosen.objects.filter(jenjang='S3', is_luar_negeri=True).count()
    total_s3_dn = RiwayatPendidikanDosen.objects.filter(jenjang='S3', is_luar_negeri=False).count()

    # Profesor dengan S3 LN / DN
    prof_s3_ln = ProfilDosen.objects.filter(
        jabatan_fungsional='Profesor',
        riwayat_pendidikan__jenjang='S3', riwayat_pendidikan__is_luar_negeri=True
    ).distinct().count()
    prof_s3_dn = ProfilDosen.objects.filter(
        jabatan_fungsional='Profesor',
        riwayat_pendidikan__jenjang='S3', riwayat_pendidikan__is_luar_negeri=False
    ).distinct().count()

    # Distribusi jabatan fungsional
    per_jabatan_raw = (
        qs.exclude(jabatan_fungsional='')
          .values('jabatan_fungsional')
          .annotate(total=Count('id'))
          .order_by('-total')
    )
    jabatan_order = ['Profesor', 'Lektor Kepala', 'Lektor', 'Asisten Ahli']
    per_jabatan = sorted(
        [r for r in per_jabatan_raw if r['jabatan_fungsional'] in jabatan_order],
        key=lambda r: jabatan_order.index(r['jabatan_fungsional'])
    )

    # Distribusi pendidikan tertinggi
    pend_label = {'s1': 'S1', 's2': 'S2', 's3': 'S3', 'profesi': 'Profesi', 'lainnya': 'Lainnya'}
    per_pendidikan = [
        {'label': pend_label.get(r['pendidikan_tertinggi'], r['pendidikan_tertinggi']),
         'total': r['total']}
        for r in qs.exclude(pendidikan_tertinggi='')
                   .values('pendidikan_tertinggi')
                   .annotate(total=Count('id'))
                   .order_by('-total')
    ]

    # Distribusi jenis kelamin
    per_jk = {
        r['jenis_kelamin']: r['total']
        for r in qs.exclude(jenis_kelamin='').values('jenis_kelamin').annotate(total=Count('id'))
    }

    # Distribusi status
    per_status = list(
        qs.exclude(status='').values('status').annotate(total=Count('id')).order_by('-total')[:6]
    )

    # Top 20 PT dengan dosen terbanyak
    per_pt = list(
        qs.values('perguruan_tinggi__nama', 'perguruan_tinggi__singkatan', 'perguruan_tinggi__kode_pt')
          .annotate(total=Count('id'))
          .order_by('-total')[:20]
    )

    # Distribusi per wilayah
    per_wilayah = list(
        qs.values('perguruan_tinggi__wilayah__nama')
          .annotate(total=Count('id'))
          .order_by('-total')
    )

    return Response({
        'total_dosen':    total,
        'total_tetap':       total_tetap,
        'total_tidak_tetap': total_tidak_tetap,
        'total_dtpk':        total_dtpk,
        'total_profesor': total_profesor,
        'prof_s3_ln':     prof_s3_ln,
        'prof_s3_dn':     prof_s3_dn,
        'total_s3':       total_s3,
        'total_s3_ln':    total_s3_ln,
        'total_s3_dn':    total_s3_dn,
        'total_aktif':          total_aktif,
        'total_tugas_belajar':  total_tugas_belajar,
        'total_ijin_belajar':   total_ijin_belajar,
        'total_cuti':           total_cuti,
        'per_jabatan':    per_jabatan,
        'per_pendidikan': per_pendidikan,
        'per_jk':         {'L': per_jk.get('L', 0), 'P': per_jk.get('P', 0)},
        'per_status':     per_status,
        'per_pt':         per_pt,
        'per_wilayah':    per_wilayah,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def dosen_search(request):
    """Pencarian profil dosen dengan filter nama, PT, jabatan, pendidikan, status."""
    nama       = request.query_params.get('nama', '').strip()
    pt_kode    = request.query_params.get('pt_kode', '').strip()
    pt_nama    = request.query_params.get('pt_nama', '').strip()
    prodi_nama = request.query_params.get('prodi_nama', '').strip()
    jabatan    = request.query_params.get('jabatan', '').strip()
    pendidikan = request.query_params.get('pendidikan', '').strip()
    status     = request.query_params.get('status', '').strip()
    page       = max(1, int(request.query_params.get('page', 1)))
    page_size  = min(int(request.query_params.get('page_size', 5)), 5000)

    ALLOWED_SORT = {
        'nama', 'jabatan_fungsional', 'pendidikan_tertinggi',
        'program_studi_nama', 'perguruan_tinggi__nama', 'status',
    }
    ordering_raw = request.query_params.get('ordering', 'nama')
    desc = ordering_raw.startswith('-')
    ordering_field = ordering_raw.lstrip('-')
    if ordering_field not in ALLOWED_SORT:
        ordering_field = 'nama'
        desc = False
    ordering = ('-' if desc else '') + ordering_field

    qs = ProfilDosen.objects.select_related('perguruan_tinggi', 'program_studi').filter(
        nama__isnull=False
    ).exclude(nama='').exclude(nama__regex=r'^[\.\-\s]+$')

    if nama:
        qs = qs.filter(nama__icontains=nama)
    if pt_kode:
        qs = qs.filter(perguruan_tinggi__kode_pt=pt_kode)
    if pt_nama:
        qs = qs.filter(perguruan_tinggi__nama__icontains=pt_nama)
    if prodi_nama:
        qs = qs.filter(program_studi_nama__icontains=prodi_nama)
    if jabatan:
        qs = qs.filter(jabatan_fungsional=jabatan)
    if pendidikan:
        qs = qs.filter(pendidikan_tertinggi=pendidikan)
    if status:
        qs = qs.filter(status=status)

    total = qs.count()
    offset = (page - 1) * page_size
    results = qs.order_by(ordering)[offset: offset + page_size]

    data = [{
        'nidn':              r.nidn or '',
        'nuptk':             r.nuptk,
        'nama':              r.nama,
        'jenis_kelamin':     r.jenis_kelamin,
        'jabatan_fungsional': r.jabatan_fungsional,
        'pendidikan_tertinggi': r.pendidikan_tertinggi,
        'ikatan_kerja':      r.ikatan_kerja,
        'status':            r.status,
        'program_studi_nama': r.program_studi_nama,
        'kode_prodi':        r.program_studi.kode_prodi if r.program_studi else '',
        'pt_nama':           r.perguruan_tinggi.nama,
        'pt_kode':           r.perguruan_tinggi.kode_pt,
        'pt_singkatan':      r.perguruan_tinggi.singkatan,
    } for r in results]

    return Response({
        'total':     total,
        'page':      page,
        'page_size': page_size,
        'results':   data,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def riwayat_pendidikan_search(request):
    """Pencarian riwayat pendidikan dosen dengan filter jenjang, nama dosen, PT dosen, PT asal."""
    nama_dosen   = request.query_params.get('nama_dosen', '').strip()
    jenjang      = request.query_params.get('jenjang', '').strip()
    pt_dosen     = request.query_params.get('pt_dosen', '').strip()
    pt_asal      = request.query_params.get('pt_asal', '').strip()
    prodi_dosen  = request.query_params.get('prodi_dosen', '').strip()
    luar_negeri  = request.query_params.get('luar_negeri', '').strip()  # '1' atau '0'
    page        = max(1, int(request.query_params.get('page', 1)))
    page_size   = min(int(request.query_params.get('page_size', 50)), 5000)

    ALLOWED_SORT = {
        'profil_dosen__nama', 'jenjang', 'tahun_lulus',
        'perguruan_tinggi_asal', 'profil_dosen__perguruan_tinggi__nama',
    }
    ordering_raw   = request.query_params.get('ordering', 'profil_dosen__nama')
    desc           = ordering_raw.startswith('-')
    ordering_field = ordering_raw.lstrip('-')
    if ordering_field not in ALLOWED_SORT:
        ordering_field = 'profil_dosen__nama'
        desc = False
    ordering = ('-' if desc else '') + ordering_field

    qs = RiwayatPendidikanDosen.objects.select_related(
        'profil_dosen', 'profil_dosen__perguruan_tinggi', 'profil_dosen__program_studi'
    ).exclude(profil_dosen__nama__regex=r'^[\.\-\s]+')

    if jenjang:
        qs = qs.filter(jenjang=jenjang)
    if nama_dosen:
        qs = qs.filter(profil_dosen__nama__icontains=nama_dosen)
    if pt_dosen:
        qs = qs.filter(profil_dosen__perguruan_tinggi__nama__icontains=pt_dosen)
    if prodi_dosen:
        qs = qs.filter(profil_dosen__program_studi_nama__icontains=prodi_dosen)
    if pt_asal:
        qs = qs.filter(perguruan_tinggi_asal__icontains=pt_asal)
    if luar_negeri == '1':
        qs = qs.filter(is_luar_negeri=True)
    elif luar_negeri == '0':
        qs = qs.filter(is_luar_negeri=False)

    total   = qs.count()
    offset  = (page - 1) * page_size
    results = qs.order_by(ordering)[offset: offset + page_size]

    data = [{
        'id':                    r.id,
        'nidn':                  r.profil_dosen.nidn or '',
        'nama_dosen':            r.profil_dosen.nama,
        'jabatan_fungsional':    r.profil_dosen.jabatan_fungsional,
        'program_studi_nama':    r.profil_dosen.program_studi_nama,
        'pt_nama':               r.profil_dosen.perguruan_tinggi.nama,
        'pt_singkatan':          r.profil_dosen.perguruan_tinggi.singkatan,
        'perguruan_tinggi_asal': r.perguruan_tinggi_asal,
        'gelar':                 r.gelar,
        'jenjang':               r.jenjang,
        'tahun_lulus':           r.tahun_lulus,
        'is_luar_negeri':        r.is_luar_negeri,
    } for r in results]

    return Response({
        'total':     total,
        'page':      page,
        'page_size': page_size,
        'results':   data,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def prodi_distribusi(request):
    """
    Distribusi Program Studi dikelompokkan berdasarkan nama prodi.
    Setiap baris = satu nama prodi unik, berisi jumlah PT, total dosen tetap, total mhs aktif.
    Query params: ta (tahun akademik), sem (ganjil/genap)
    """
    ta_filter      = request.GET.get('ta', '')
    sem_filter     = request.GET.get('sem', '')
    jenjang_filter = request.GET.get('jenjang', '')

    # Semester choices
    sem_choices = list(
        DataMahasiswa.objects
        .values('tahun_akademik', 'semester')
        .distinct()
        .annotate(sem_order=Case(
            When(semester='ganjil', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        ))
        .order_by('-tahun_akademik', 'sem_order')
        .values('tahun_akademik', 'semester')
    )

    if ta_filter and sem_filter:
        selected_ta, selected_sem = ta_filter, sem_filter
    elif sem_choices:
        selected_ta  = sem_choices[0]['tahun_akademik']
        selected_sem = sem_choices[0]['semester']
    else:
        selected_ta = selected_sem = ''

    # Annotate each prodi record
    qs = ProgramStudi.objects
    if jenjang_filter:
        qs = qs.filter(jenjang__iexact=jenjang_filter)
    qs = qs.annotate(
        dosen_ann=Count('profil_dosen', distinct=True)
    )

    if selected_ta and selected_sem:
        mhs_sub = (
            DataMahasiswa.objects
            .filter(program_studi=OuterRef('pk'), tahun_akademik=selected_ta, semester=selected_sem)
            .values('mahasiswa_aktif')[:1]
        )
        qs = qs.annotate(mhs_aktif=Subquery(mhs_sub, output_field=IntegerField()))
    else:
        qs = qs.annotate(mhs_aktif=Value(None, output_field=IntegerField()))

    # Group by nama in Python
    from collections import defaultdict
    groups: dict = defaultdict(lambda: {'jumlah_pt': set(), 'total_dosen': 0, 'total_mhs': 0, 'has_mhs': False})

    for ps in qs.only('id', 'nama', 'perguruan_tinggi_id'):
        g = groups[ps.nama.strip()]
        g['jumlah_pt'].add(ps.perguruan_tinggi_id)
        g['total_dosen'] += ps.dosen_ann or 0
        if ps.mhs_aktif is not None:
            g['total_mhs'] += ps.mhs_aktif
            g['has_mhs'] = True

    results = [
        {
            'nama':        nama,
            'jumlah_pt':   len(g['jumlah_pt']),
            'total_dosen': g['total_dosen'],
            'total_mhs':   g['total_mhs'] if g['has_mhs'] else None,
        }
        for nama, g in sorted(groups.items(), key=lambda x: x[0].lower())
    ]

    return Response({
        'selected_ta':  selected_ta,
        'selected_sem': selected_sem,
        'sem_choices':  sem_choices,
        'total':        len(results),
        'results':      results,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def prodi_daftar(request):
    """
    Daftar seluruh prodi (paginated, filterable, sortable).
    Kolom kode_pt dan kode_prodi ditampilkan terpisah.
    Query params: nama, jenjang, nama_pt, kode_pt, kode_prodi, akreditasi,
                  ta, sem, sort, dir, page, page_size
    """
    nama_f      = request.GET.get('nama', '').strip()
    jenjang_f   = request.GET.get('jenjang', '').strip()
    nama_pt_f   = request.GET.get('nama_pt', '').strip()
    kode_pt_f   = request.GET.get('kode_pt', '').strip()
    kode_prodi_f= request.GET.get('kode_prodi', '').strip()
    akreditasi_f= request.GET.get('akreditasi', '').strip()
    ta_f        = request.GET.get('ta', '').strip()
    sem_f       = request.GET.get('sem', '').strip()

    # Semester choices (ganjil first within same year)
    sem_choices = list(
        DataMahasiswa.objects
        .values('tahun_akademik', 'semester')
        .distinct()
        .annotate(sem_order=Case(
            When(semester='ganjil', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        ))
        .order_by('-tahun_akademik', 'sem_order')
        .values('tahun_akademik', 'semester')
    )

    # Auto-default ta/sem to active reporting period
    if not ta_f and not sem_f:
        periode_aktif = PeriodePelaporan.objects.filter(status='aktif').order_by('-tahun', 'semester').first()
        if periode_aktif:
            if periode_aktif.semester == 'genap':
                ta_f = f"{periode_aktif.tahun - 1}/{periode_aktif.tahun}"
            else:
                ta_f = f"{periode_aktif.tahun}/{periode_aktif.tahun + 1}"
            sem_f = periode_aktif.semester
        elif sem_choices:
            ta_f  = sem_choices[0]['tahun_akademik']
            sem_f = sem_choices[0]['semester']

    selected_ta  = ta_f
    selected_sem = sem_f

    ALLOWED_SORT = {
        'nama': 'nama', 'jenjang': 'jenjang',
        'pt_nama': 'perguruan_tinggi__nama',
        'kode_pt': 'perguruan_tinggi__kode_pt',
        'kode_prodi': 'kode_prodi',
        'akreditasi': 'akreditasi',
        'dosen_tetap': 'dosen_tetap',
        'mhs_aktif': 'mhs_aktif',
    }
    sort_field = ALLOWED_SORT.get(request.GET.get('sort', 'nama'), 'nama')
    sort_dir   = '' if request.GET.get('dir', 'asc') == 'asc' else '-'

    try:
        page      = max(1, int(request.GET.get('page', 1)))
        page_size = min(99999, max(1, int(request.GET.get('page_size', 50))))
    except (ValueError, TypeError):
        page, page_size = 1, 50

    qs = ProgramStudi.objects.select_related('perguruan_tinggi')

    if nama_f:
        qs = qs.filter(nama__icontains=nama_f)
    if jenjang_f:
        qs = qs.filter(jenjang__iexact=jenjang_f)
    if nama_pt_f:
        qs = qs.filter(perguruan_tinggi__nama__icontains=nama_pt_f)
    if kode_pt_f:
        qs = qs.filter(perguruan_tinggi__kode_pt__icontains=kode_pt_f)
    if kode_prodi_f:
        qs = qs.filter(kode_prodi__icontains=kode_prodi_f)
    if akreditasi_f:
        qs = qs.filter(akreditasi__iexact=akreditasi_f)

    # Annotate total dosen from ProfilDosen aggregate
    qs = qs.annotate(
        dosen_ann=Count('profil_dosen', distinct=True)
    )

    # Annotate mahasiswa aktif
    if ta_f and sem_f:
        mhs_sub = (
            DataMahasiswa.objects
            .filter(
                program_studi=OuterRef('pk'),
                tahun_akademik=ta_f,
                semester=sem_f,
            )
            .values('mahasiswa_aktif')[:1]
        )
        qs = qs.annotate(mhs_aktif=Subquery(mhs_sub, output_field=IntegerField()))
    else:
        qs = qs.annotate(mhs_aktif=Value(None, output_field=IntegerField()))

    total = qs.count()

    if sort_field in ('mhs_aktif', 'dosen_tetap'):
        db_field = 'mhs_aktif' if sort_field == 'mhs_aktif' else 'dosen_ann'
        qs = qs.order_by(f'{sort_dir}{db_field}', 'nama')
    else:
        qs = qs.order_by(f'{sort_dir}{sort_field}')

    offset  = (page - 1) * page_size
    results = qs[offset: offset + page_size]

    data = [{
        'id':                ps.id,
        'kode_pt':           ps.perguruan_tinggi.kode_pt   if ps.perguruan_tinggi else '',
        'pt_nama':           ps.perguruan_tinggi.nama       if ps.perguruan_tinggi else '',
        'pt_singkatan':      ps.perguruan_tinggi.singkatan  if ps.perguruan_tinggi else '',
        'kode_prodi':        ps.kode_prodi or '',
        'nama':              ps.nama,
        'jenjang':           ps.jenjang,
        'akreditasi':        ps.akreditasi,
        'no_sk_akreditasi':  ps.no_sk_akreditasi or '',
        'tanggal_kedaluarsa_akreditasi': str(ps.tanggal_kedaluarsa_akreditasi) if ps.tanggal_kedaluarsa_akreditasi else None,
        'dosen_tetap':       ps.dosen_ann or 0,
        'mhs_aktif':         ps.mhs_aktif,
    } for ps in results]

    return Response({
        'total':        total,
        'page':         page,
        'page_size':    page_size,
        'selected_ta':  selected_ta,
        'selected_sem': selected_sem,
        'sem_choices':  sem_choices,
        'results':      data,
    })
