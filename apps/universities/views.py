"""Views for Universities app"""

import json, os, re, sys
from difflib import SequenceMatcher
from pathlib import Path
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Count, Sum, Q, Case, When, Value, IntegerField
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes, authentication_classes
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

from .models import Wilayah, PerguruanTinggi, ProgramStudi, DataMahasiswa, DataDosen, ProfilDosen, RiwayatPendidikanDosen, SintaJurnal, SintaAfiliasi, SintaDepartemen, SintaAuthor, SintaScopusArtikel, SintaScopusArtikelAuthor, SintaAuthorTrend, SintaPengabdian, SintaPengabdianAuthor, SintaPenelitian, SintaPenelitianAuthor, KolaboasiSnapshot
from django.db.models import OuterRef, Subquery
from .serializers import _get_periode_aktif
from apps.monitoring.models import PeriodePelaporan
from .serializers import (
    WilayahSerializer, PerguruanTinggiListSerializer,
    PerguruanTinggiDetailSerializer, ProgramStudiSerializer,
    DataMahasiswaSerializer, DataDosenSerializer,
    SintaJurnalSerializer, SintaJurnalListSerializer,
    SintaAfiliasiListSerializer, SintaAfiliasiDetailSerializer,
    SintaDepartemenListSerializer, SintaDepartemenDetailSerializer,
    SintaAuthorListSerializer, SintaAuthorDetailSerializer,
)
SintaDepartemenSerializer = SintaDepartemenListSerializer  # legacy alias


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
            _month_map = {'less_1m': 1, 'less_2m': 2, 'less_3m': 3, 'less_5m': 5,
                          'less_7m': 7, 'less_12m': 12}
            if exp_filter in _month_map:
                qs = qs.filter(
                    tanggal_kadaluarsa_akreditasi__isnull=False,
                    tanggal_kadaluarsa_akreditasi__lte=today + relativedelta(months=_month_map[exp_filter])
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

        Catatan: jenjang 'profesi' (PPG, Ners, Apoteker, dll) DIKECUALIKAN dari estimasi baru
        karena merupakan sertifikasi profesional (bukan mahasiswa baru masuk PT), dan
        sejak 2022 jumlahnya meledak karena program PPG Daljab sehingga mendistorsi estimasi.

        Params:
          metric          - 'baru' | 'lulus'  (default: 'baru')
          pt_id[]         - filter PT
          prodi_id[]      - filter Prodi
          mode            - 'gabung' | 'perbandingan'
          filter_by       - 'pt' | 'prodi'
          include_profesi - 'true' | 'false'  (default: 'false')
                            false = profesi (PPG/Ners) dikecualikan karena bukan mahasiswa baru PT
                            true  = profesi diikutkan untuk perbandingan / analisis dampak
        """
        MASA_STUDI_TANPA_PROFESI = {
            's1': 4, 's2': 2, 's3': 3,
            'd4': 4, 'd3': 3, 'd2': 2, 'd1': 1,
        }
        MASA_STUDI_DENGAN_PROFESI = {
            's1': 4, 's2': 2, 's3': 3,
            'd4': 4, 'd3': 3, 'd2': 2, 'd1': 1,
            'profesi': 1,
        }
        DEFAULT_MS = 4

        pt_ids          = request.query_params.getlist('pt_id')
        prodi_ids       = request.query_params.getlist('prodi_id')
        mode            = request.query_params.get('mode', 'gabung')
        filter_by       = request.query_params.get('filter_by', 'pt')
        metric          = request.query_params.get('metric', 'baru')
        include_profesi = request.query_params.get('include_profesi', 'false').lower() == 'true'

        MASA_STUDI = MASA_STUDI_DENGAN_PROFESI if include_profesi else MASA_STUDI_TANPA_PROFESI

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
            if not include_profesi:
                qs = qs.exclude(program_studi__jenjang='profesi')
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
    def ringkasan_mahasiswa(self, request):
        """
        Ringkasan tren per tahun akademik: aktif (semester ganjil) + estimasi baru + estimasi lulus.
        Semua dataset menggunakan sumbu X yang sama (tahun akademik ganjil).
        Params:
          pt_id[]         - filter PT (tepat 1)
          prodi_id[]      - filter Prodi (tepat 1)
          filter_by       - 'pt' | 'prodi'
          include_profesi - 'true' | 'false'  (default: 'false')
        """
        MASA_STUDI_TANPA_PROFESI = {
            's1': 4, 's2': 2, 's3': 3,
            'd4': 4, 'd3': 3, 'd2': 2, 'd1': 1,
        }
        MASA_STUDI_DENGAN_PROFESI = {
            's1': 4, 's2': 2, 's3': 3,
            'd4': 4, 'd3': 3, 'd2': 2, 'd1': 1,
            'profesi': 1,
        }
        DEFAULT_MS = 4

        pt_ids          = request.query_params.getlist('pt_id')
        prodi_ids       = request.query_params.getlist('prodi_id')
        filter_by       = request.query_params.get('filter_by', 'pt')
        include_profesi = request.query_params.get('include_profesi', 'false').lower() == 'true'

        MASA_STUDI = MASA_STUDI_DENGAN_PROFESI if include_profesi else MASA_STUDI_TANPA_PROFESI

        # Tahun akademik ganjil (exclude 2017/2018 karena data tidak lengkap)
        tahun_list = list(
            DataMahasiswa.objects
            .filter(semester='ganjil')
            .exclude(tahun_akademik='2017/2018')
            .values_list('tahun_akademik', flat=True)
            .distinct()
            .order_by('tahun_akademik')
        )

        def _base_filter(tahun):
            qs = DataMahasiswa.objects.filter(semester='ganjil', tahun_akademik=tahun)
            if pt_ids:
                qs = qs.filter(perguruan_tinggi_id__in=pt_ids)
            if prodi_ids:
                qs = qs.filter(program_studi_id__in=prodi_ids)
            return qs

        def _aktif(tahun):
            return _base_filter(tahun).aggregate(total=Sum('mahasiswa_aktif'))['total'] or 0

        def _baru_est(tahun):
            qs = _base_filter(tahun).filter(mahasiswa_aktif__gt=0)
            if not include_profesi:
                qs = qs.exclude(program_studi__jenjang='profesi')
            rows = qs.values('program_studi__jenjang').annotate(total=Sum('mahasiswa_aktif'))
            total = 0
            for r in rows:
                ms = MASA_STUDI.get(r['program_studi__jenjang'] or '', DEFAULT_MS)
                total += round(r['total'] / ms)
            return total

        def _lulus_est(tahun):
            thn = int(tahun[:4])
            thn_masuk = f'{thn - DEFAULT_MS}/{thn - DEFAULT_MS + 1}'
            if thn_masuk not in tahun_list:
                return 0
            return _baru_est(thn_masuk)

        # Buat label nama dataset
        label_name = 'Semua PT'
        if filter_by == 'prodi' and prodi_ids:
            try:
                prodi = ProgramStudi.objects.select_related('perguruan_tinggi').get(pk=prodi_ids[0])
                label_name = f"{prodi.nama} ({prodi.jenjang}) — {prodi.perguruan_tinggi.singkatan}"
            except ProgramStudi.DoesNotExist:
                pass
        elif pt_ids:
            try:
                pt = PerguruanTinggi.objects.get(pk=pt_ids[0])
                label_name = pt.singkatan or pt.nama
            except PerguruanTinggi.DoesNotExist:
                pass

        aktif_data = [_aktif(t)    for t in tahun_list]
        baru_data  = [_baru_est(t) for t in tahun_list]
        lulus_data = [_lulus_est(t) if _lulus_est(t) > 0 else None for t in tahun_list]

        return Response({
            'labels': tahun_list,
            'datasets': [
                {'label': f'{label_name} — Aktif',       'data': aktif_data},
                {'label': f'{label_name} — Est. Baru',   'data': baru_data},
                {'label': f'{label_name} — Est. Lulus',  'data': lulus_data},
            ],
            'note': 'Aktif = data semester ganjil. Baru/Lulus = estimasi statistik.',
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
        pt_id   = request.query_params.get('pt_id', '').strip()
        qs = ProgramStudi.objects.filter(is_active=True)
        if nama:
            qs = qs.filter(nama__icontains=nama)
        if jenjang:
            qs = qs.filter(jenjang=jenjang)
        if pt_id:
            qs = qs.filter(perguruan_tinggi_id=pt_id)
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

    @action(detail=True, methods=['get'])
    def detail_popup(self, request, pk=None):
        """Detail prodi untuk popup: info, tren mahasiswa, tren dosen"""
        try:
            prodi = ProgramStudi.objects.select_related('perguruan_tinggi').get(pk=pk)
        except ProgramStudi.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)

        pt = prodi.perguruan_tinggi
        AKREDITASI_LABEL = dict(ProgramStudi.StatusAkreditasi.choices)

        # Tren mahasiswa aktif per semester (ganjil only, ascending)
        mhs_qs = (DataMahasiswa.objects
                  .filter(program_studi=prodi)
                  .exclude(tahun_akademik='2017/2018')
                  .order_by('tahun_akademik', 'semester'))
        tren_mhs = [
            {
                'label': f"{m.tahun_akademik} {m.semester.title()}",
                'aktif': m.mahasiswa_aktif,
                'pria': m.mahasiswa_pria,
                'wanita': m.mahasiswa_wanita,
            }
            for m in mhs_qs
        ]

        # Tren dosen per semester
        dsn_qs = (DataDosen.objects
                  .filter(program_studi=prodi)
                  .exclude(tahun_akademik='2017/2018')
                  .order_by('tahun_akademik', 'semester'))
        tren_dsn = [
            {
                'label': f"{d.tahun_akademik} {d.semester.title()}",
                'tetap': d.dosen_tetap,
                'tidak_tetap': d.dosen_tidak_tetap,
                's3': d.dosen_s3,
                's2': d.dosen_s2,
                's1': d.dosen_s1,
            }
            for d in dsn_qs
        ]

        return Response({
            'id':           prodi.id,
            'kode_prodi':   prodi.kode_prodi,
            'nama':         prodi.nama,
            'jenjang':      prodi.jenjang,
            'jenjang_display': prodi.get_jenjang_display(),
            'akreditasi':   prodi.akreditasi,
            'akreditasi_display': AKREDITASI_LABEL.get(prodi.akreditasi, prodi.akreditasi),
            'no_sk':        prodi.no_sk_akreditasi,
            'tgl_exp':      prodi.tanggal_kedaluarsa_akreditasi,
            'is_active':    prodi.is_active,
            'pt_id':        pt.id,
            'pt_nama':      pt.nama,
            'pt_singkatan': pt.singkatan,
            'pt_kota':      pt.kota,
            'pt_provinsi':  pt.provinsi,
            'pt_akreditasi': pt.akreditasi_institusi,
            'tren_mahasiswa': tren_mhs,
            'tren_dosen':     tren_dsn,
        })

    @action(detail=False, methods=['get'])
    def exp_counts(self, request):
        """Hitung jumlah prodi yang kedaluarsa < 7 bulan dan < 12 bulan"""
        today = date.today()
        qs = ProgramStudi.objects.filter(is_active=True, tanggal_kedaluarsa_akreditasi__isnull=False)
        count_1m  = qs.filter(tanggal_kedaluarsa_akreditasi__lte=today + relativedelta(months=1)).count()
        count_2m  = qs.filter(tanggal_kedaluarsa_akreditasi__lte=today + relativedelta(months=2)).count()
        count_3m  = qs.filter(tanggal_kedaluarsa_akreditasi__lte=today + relativedelta(months=3)).count()
        count_5m  = qs.filter(tanggal_kedaluarsa_akreditasi__lte=today + relativedelta(months=5)).count()
        count_7m  = qs.filter(tanggal_kedaluarsa_akreditasi__lte=today + relativedelta(months=7)).count()
        count_12m = qs.filter(tanggal_kedaluarsa_akreditasi__lte=today + relativedelta(months=12)).count()
        return Response({'count_1m': count_1m, 'count_2m': count_2m,
                         'count_3m': count_3m, 'count_5m': count_5m,
                         'count_7m': count_7m, 'count_12m': count_12m})

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
@authentication_classes([])
@permission_classes([AllowAny])
def dosen_dropdown_options(request):
    """Opsi dropdown untuk filter dosen: daftar PT dan (opsional) prodi per PT."""
    pt_kode = request.query_params.get('pt_kode', '').strip()

    pt_list = list(
        PerguruanTinggi.objects.filter(is_active=True)
        .values('id', 'kode_pt', 'nama', 'singkatan')
        .order_by('nama')
    )

    prodi_list = []
    if pt_kode:
        prodi_list = list(
            ProgramStudi.objects.filter(
                perguruan_tinggi__kode_pt=pt_kode, is_active=True
            )
            .values('kode_prodi', 'nama', 'jenjang')
            .order_by('nama')
        )

    return Response({'pt': pt_list, 'prodi': prodi_list})


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
    prodi_kode = request.query_params.get('prodi_kode', '').strip()
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
    if prodi_kode:
        qs = qs.filter(program_studi__kode_prodi=prodi_kode)
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


class PT20Pagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 200


class SintaJurnalViewSet(PublicReadAdminWriteMixin, viewsets.ReadOnlyModelViewSet):
    queryset = SintaJurnal.objects.select_related('perguruan_tinggi').order_by('-impact', 'nama')
    pagination_class = PT20Pagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'akreditasi':       ['exact', 'in'],
        'is_scopus':        ['exact'],
        'is_garuda':        ['exact'],
        'perguruan_tinggi': ['exact'],
        'subject_area':     ['icontains'],
        'wcu_area':         ['icontains'],
    }
    search_fields = ['nama', 'p_issn', 'e_issn', 'afiliasi_teks', 'perguruan_tinggi__nama', 'perguruan_tinggi__singkatan']
    ordering_fields = ['impact', 'h5_index', 'sitasi_total', 'sitasi_5yr', 'nama', 'akreditasi', 'perguruan_tinggi__nama', 'wcu_area']

    def get_serializer_class(self):
        if self.action == 'list':
            return SintaJurnalListSerializer
        return SintaJurnalSerializer

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Statistik ringkas: total, distribusi akreditasi, scopus, garuda, wcu_area."""
        from django.db.models import Count
        qs = SintaJurnal.objects.all()

        pt_id = request.query_params.get('perguruan_tinggi')
        if pt_id:
            qs = qs.filter(perguruan_tinggi=pt_id)

        total  = qs.count()
        scopus = qs.filter(is_scopus=True).count()
        garuda = qs.filter(is_garuda=True).count()
        distrib = list(
            qs.values('akreditasi')
              .annotate(jumlah=Count('id'))
              .order_by('akreditasi')
        )

        # Distribusi WCU — hitung per tag (bisa multi-value)
        WCU_ORDER = [
            'Natural Sciences', 'Engineering & Technology',
            'Life Sciences & Medicine', 'Social Sciences & Management',
            'Arts & Humanities',
        ]
        wcu_counter = {g: 0 for g in WCU_ORDER}
        for val in qs.values_list('wcu_area', flat=True):
            for part in (val or '').split(','):
                p = part.strip()
                if p in wcu_counter:
                    wcu_counter[p] += 1
        distribusi_wcu = [
            {'wcu_area': g, 'jumlah': wcu_counter[g]}
            for g in WCU_ORDER if wcu_counter[g] > 0
        ]

        return Response({
            'total': total,
            'scopus': scopus,
            'garuda': garuda,
            'distribusi_akreditasi': distrib,
            'distribusi_wcu': distribusi_wcu,
        })


class SintaAfiliasiViewSet(PublicReadAdminWriteMixin, viewsets.ReadOnlyModelViewSet):
    """
    Endpoint profil afiliasi SINTA per Perguruan Tinggi.

    List  : GET /api/sinta-afiliasi/
    Detail: GET /api/sinta-afiliasi/{id}/
    Stats : GET /api/sinta-afiliasi/stats/
    """
    queryset = (
        SintaAfiliasi.objects
        .select_related('perguruan_tinggi', 'cluster')
        .prefetch_related('trend_tahunan', 'wcu_tahunan')
        .order_by('-sinta_score_overall')
    )
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'cluster__cluster_name': ['exact', 'icontains'],
    }
    search_fields   = [
        'nama_sinta', 'singkatan_sinta',
        'perguruan_tinggi__nama', 'perguruan_tinggi__singkatan',
        'perguruan_tinggi__kota', 'perguruan_tinggi__provinsi',
    ]
    ordering_fields = [
        'sinta_score_overall', 'sinta_score_3year',
        'scopus_dokumen', 'scopus_sitasi',
        'gscholar_dokumen', 'gscholar_sitasi',
        'garuda_dokumen',
        'jumlah_authors',
        'cluster__total_score',
        'nama_sinta',
    ]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SintaAfiliasiDetailSerializer
        return SintaAfiliasiListSerializer

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Statistik agregat seluruh PTMA di SINTA."""
        from django.db.models import Avg, Max, Count as DCount
        qs = SintaAfiliasi.objects.all()

        total_pt      = qs.count()
        total_authors = qs.aggregate(t=Sum('jumlah_authors'))['t'] or 0
        total_scopus  = qs.aggregate(t=Sum('scopus_dokumen'))['t'] or 0
        total_gscholar= qs.aggregate(t=Sum('gscholar_dokumen'))['t'] or 0
        total_garuda  = qs.aggregate(t=Sum('garuda_dokumen'))['t'] or 0
        avg_score     = qs.aggregate(a=Avg('sinta_score_overall'))['a'] or 0
        max_score     = qs.aggregate(m=Max('sinta_score_overall'))['m'] or 0

        # Distribusi cluster
        from .models import SintaCluster
        cluster_dist = list(
            SintaCluster.objects
            .values('cluster_name')
            .annotate(jumlah=DCount('id'))
            .order_by('cluster_name')
        )

        return Response({
            'total_pt':       total_pt,
            'total_authors':  total_authors,
            'total_scopus':   int(total_scopus),
            'total_gscholar': int(total_gscholar),
            'total_garuda':   int(total_garuda),
            'avg_score':      round(avg_score),
            'max_score':      max_score,
            'distribusi_cluster': cluster_dist,
        })


class SintaDepartemenViewSet(PublicReadAdminWriteMixin, viewsets.ReadOnlyModelViewSet):
    """
    Endpoint daftar departemen (program studi) PTMA di SINTA.

    List  : GET /api/sinta-departemen/
    Detail: GET /api/sinta-departemen/{id}/
    Stats : GET /api/sinta-departemen/stats/

    Filter  : afiliasi__sinta_kode, jenjang
    Search  : nama, afiliasi__nama_sinta, afiliasi__perguruan_tinggi__singkatan
    Ordering: sinta_score_overall, sinta_score_3year, jumlah_authors, nama
    """
    queryset = (
        SintaDepartemen.objects
        .select_related('afiliasi__perguruan_tinggi')
        .order_by('-sinta_score_overall')
    )
    serializer_class = SintaDepartemenListSerializer
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'afiliasi__sinta_kode': ['exact'],
        'jenjang':              ['exact', 'icontains'],
    }
    search_fields   = [
        'nama',
        'afiliasi__nama_sinta',
        'afiliasi__singkatan_sinta',
        'afiliasi__perguruan_tinggi__singkatan',
        'afiliasi__perguruan_tinggi__nama',
    ]
    ordering_fields = [
        'sinta_score_overall', 'sinta_score_3year',
        'sinta_score_productivity', 'sinta_score_productivity_3year',
        'jumlah_authors', 'nama',
        'scopus_artikel', 'scopus_sitasi',
        'afiliasi__nama_sinta',
    ]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SintaDepartemenDetailSerializer
        return SintaDepartemenListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'retrieve':
            qs = qs.prefetch_related('authors')
        return qs

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Statistik agregat departemen seluruh PTMA."""
        from django.db.models import Avg, Max, Count as DCount

        qs = SintaDepartemen.objects.all()

        # Filter per PT jika ada query param
        kode_pt = request.query_params.get('kode_pt')
        if kode_pt:
            qs = qs.filter(afiliasi__sinta_kode=kode_pt)

        total_dept   = qs.count()
        total_authors = qs.aggregate(t=Sum('jumlah_authors'))['t'] or 0
        avg_score    = qs.aggregate(a=Avg('sinta_score_overall'))['a'] or 0
        max_score    = qs.aggregate(m=Max('sinta_score_overall'))['m'] or 0

        distribusi_jenjang = list(
            qs.values('jenjang')
            .annotate(jumlah=DCount('id'))
            .order_by('-jumlah')
        )

        return Response({
            'total_departemen':    total_dept,
            'total_authors':       total_authors,
            'avg_score_overall':   round(avg_score),
            'max_score_overall':   max_score,
            'distribusi_jenjang':  distribusi_jenjang,
        })


class SintaAuthorViewSet(PublicReadAdminWriteMixin, viewsets.ReadOnlyModelViewSet):
    """
    Endpoint profil author PTMA di SINTA.

    List  : GET /api/sinta-author/
    Detail: GET /api/sinta-author/{id}/
    Stats : GET /api/sinta-author/stats/

    Filter  : afiliasi__sinta_kode, departemen, departemen__kode_dept
    Search  : nama, bidang_keilmuan
    Ordering: sinta_score_overall, sinta_score_3year, scopus_artikel, scopus_h_index
    """

    def get_permissions(self):
        if self.action == 'sync_single':
            return [AllowAny()]
        return super().get_permissions()

    def get_authenticators(self):
        if self.action == 'sync_single':
            return []
        return super().get_authenticators()

    queryset = (
        SintaAuthor.objects
        .select_related('afiliasi__perguruan_tinggi', 'departemen')
        .order_by('-sinta_score_overall')
    )
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'afiliasi__sinta_kode':    ['exact'],
        'departemen':              ['exact'],
        'departemen__kode_dept':   ['exact'],
    }
    search_fields   = ['nama', 'bidang_keilmuan']
    ordering_fields = [
        'sinta_score_overall', 'sinta_score_3year',
        'scopus_artikel', 'scopus_sitasi', 'scopus_h_index',
        'gscholar_h_index', 'nama',
        'afiliasi__nama_sinta', 'departemen__nama',
    ]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return SintaAuthorDetailSerializer
        return SintaAuthorListSerializer

    @action(detail=False, methods=['get'], url_path='pt-options',
            authentication_classes=[], permission_classes=[AllowAny])
    def pt_options(self, request):
        """Daftar PT unik yang memiliki author di SINTA (tanpa paginasi)."""
        rows = (
            SintaAuthor.objects
            .select_related('afiliasi')
            .values('afiliasi__sinta_kode', 'afiliasi__singkatan_sinta', 'afiliasi__nama_sinta')
            .distinct()
            .order_by('afiliasi__singkatan_sinta')
        )
        result = [
            {'kode': r['afiliasi__sinta_kode'],
             'singkatan': r['afiliasi__singkatan_sinta']
                         if r['afiliasi__singkatan_sinta'] and r['afiliasi__singkatan_sinta'] != '-'
                         else r['afiliasi__nama_sinta']}
            for r in rows if r['afiliasi__sinta_kode']
        ]
        return Response(result)

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Statistik agregat author seluruh PTMA."""
        from django.db.models import Avg, Max, Count as DCount

        qs = SintaAuthor.objects.all()

        kode_pt = request.query_params.get('kode_pt')
        if kode_pt:
            qs = qs.filter(afiliasi__sinta_kode=kode_pt)

        agg = qs.aggregate(
            total=DCount('id'),
            avg_score=Avg('sinta_score_overall'),
            max_score=Max('sinta_score_overall'),
            total_scopus=Sum('scopus_artikel'),
            total_sitasi=Sum('scopus_sitasi'),
        )

        return Response({
            'total_authors':     agg['total'] or 0,
            'avg_score_overall': round(agg['avg_score'] or 0),
            'max_score_overall': agg['max_score'] or 0,
            'total_scopus_artikel': agg['total_scopus'] or 0,
            'total_scopus_sitasi':  agg['total_sitasi'] or 0,
        })

    @action(detail=True, methods=['post'], url_path='sync',
            authentication_classes=[], permission_classes=[AllowAny])
    def sync_single(self, request, pk=None):
        """Sinkron ulang satu author dari SINTA (hanya untuk env lokal)."""
        import subprocess, sys
        from pathlib import Path as PPath

        author = self.get_object()
        if not author.url_profil:
            return Response({'detail': 'Author tidak memiliki url_profil.'}, status=400)

        runner = PPath(__file__).resolve().parent.parent.parent / 'utils' / 'sinta' / 'sync_sinta_author_runner.py'
        cmd = [sys.executable, str(runner), '--author_id', str(author.id)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                return Response({'detail': 'Sync gagal.', 'stderr': result.stderr[-500:]}, status=500)
            return Response({'detail': 'Sync berhasil.', 'output': result.stdout[-500:]})
        except subprocess.TimeoutExpired:
            return Response({'detail': 'Sync timeout (>120 detik).'}, status=504)
        except Exception as e:
            return Response({'detail': str(e)}, status=500)


class SintaScopusArtikelViewSet(PublicReadAdminWriteMixin, viewsets.ReadOnlyModelViewSet):
    """
    Daftar artikel Scopus per author.

    GET /api/sinta-scopus-artikel/?author=<id>&ordering=-sitasi
    GET /api/sinta-scopus-artikel/?author=<id>&kuartil=Q1
    GET /api/sinta-scopus-artikel/?author=<id>&tahun=2023
    """
    serializer_class = None   # pakai inline di bawah
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    def get_permissions(self):
        # riset-analisis POST bebas akses (siapapun boleh trigger)
        if self.action == 'riset_analisis':
            return [AllowAny()]
        return super().get_permissions()
    filterset_fields = {
        'artikel_authors__author': ['exact'],
        'kuartil':                 ['exact', 'in'],
        'tahun':                   ['exact', 'gte', 'lte'],
    }
    search_fields   = ['judul', 'jurnal_nama']
    ordering_fields = ['tahun', 'sitasi', 'kuartil', 'jurnal_nama']
    ordering        = ['-sitasi', '-tahun']

    def get_queryset(self):
        qs = (
            SintaScopusArtikel.objects
            .prefetch_related(
                'artikel_authors__author__afiliasi__perguruan_tinggi'
            )
            .order_by('-sitasi', '-tahun')
        )
        author_id = self.request.query_params.get('author')
        if author_id:
            qs = qs.filter(artikel_authors__author_id=author_id)
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())

        # Paginasi manual
        page_size = min(int(request.query_params.get('page_size', 20)), 200)
        page      = int(request.query_params.get('page', 1))
        total     = qs.count()
        items     = qs[(page - 1) * page_size: page * page_size]

        # Ambil relasi penulis untuk author yg diminta
        author_id = request.query_params.get('author')

        results = []
        for art in items:
            rel = None
            if author_id:
                try:
                    rel = art.artikel_authors.get(author_id=author_id)
                except Exception:
                    pass

            penulis_ptma = [
                {
                    'author_id':      r.author_id,
                    'nama':           r.author.nama,
                    'sinta_id':       r.author.sinta_id,
                    'pt_singkatan':   (
                        r.author.afiliasi.perguruan_tinggi.singkatan
                        if r.author.afiliasi_id and r.author.afiliasi and r.author.afiliasi.perguruan_tinggi_id
                        else ''
                    ),
                    'urutan_penulis': r.urutan_penulis,
                    'total_penulis':  r.total_penulis,
                }
                for r in art.artikel_authors.all()
            ]

            results.append({
                'id':             art.id,
                'eid':            art.eid,
                'judul':          art.judul,
                'tahun':          art.tahun,
                'sitasi':         art.sitasi,
                'kuartil':        art.kuartil,
                'jurnal_nama':    art.jurnal_nama,
                'jurnal_url':     art.jurnal_url,
                'scopus_url':     art.scopus_url,
                'urutan_penulis': rel.urutan_penulis if rel else None,
                'total_penulis':  rel.total_penulis  if rel else None,
                'nama_singkat':   rel.nama_singkat   if rel else None,
                'penulis_ptma':   penulis_ptma,
            })

        return Response({
            'count':    total,
            'page':     page,
            'page_size': page_size,
            'results':  results,
        })

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """Statistik agregat artikel Scopus + tren gabungan seluruh author PTMA."""
        from django.db.models import Count, Sum, Min, Max, Avg

        qs = SintaScopusArtikel.objects

        agg = qs.aggregate(
            total_artikel=Count('id'),
            total_sitasi=Sum('sitasi'),
            min_tahun=Min('tahun'),
            max_tahun=Max('tahun'),
        )
        total_jurnal = qs.exclude(jurnal_nama='').values('jurnal_nama').distinct().count()
        total_author = SintaScopusArtikelAuthor.objects.values('author_id').distinct().count()
        q1q2 = qs.filter(kuartil__in=['Q1', 'Q2']).count()

        # Distribusi kuartil
        dist_kuartil = list(
            qs.values('kuartil')
            .annotate(jumlah=Count('id'), sitasi=Sum('sitasi'))
            .order_by('kuartil')
        )

        # Tren per tahun dari artikel di DB
        tren_artikel = list(
            qs.exclude(tahun__isnull=True)
            .values('tahun')
            .annotate(jumlah=Count('id'), sitasi=Sum('sitasi'))
            .order_by('tahun')
        )

        # Tren kuartil per tahun (stacked)
        tren_kuartil = list(
            qs.exclude(tahun__isnull=True)
            .exclude(kuartil='')
            .values('tahun', 'kuartil')
            .annotate(jumlah=Count('id'))
            .order_by('tahun', 'kuartil')
        )

        # Tren gabungan dari SintaAuthorTrend (lebih lengkap — semua author yg sudah di-scrape)
        tren_scopus_author = list(
            SintaAuthorTrend.objects.filter(jenis='scopus')
            .values('tahun')
            .annotate(jumlah=Sum('jumlah'))
            .order_by('tahun')
        )
        tren_gscholar_pub = list(
            SintaAuthorTrend.objects.filter(jenis='gscholar_pub')
            .values('tahun')
            .annotate(jumlah=Sum('jumlah'))
            .order_by('tahun')
        )
        tren_gscholar_cite = list(
            SintaAuthorTrend.objects.filter(jenis='gscholar_cite')
            .values('tahun')
            .annotate(jumlah=Sum('jumlah'))
            .order_by('tahun')
        )

        # Top jurnal
        top_jurnal = list(
            qs.exclude(jurnal_nama='')
            .values('jurnal_nama')
            .annotate(jumlah=Count('id'), sitasi=Sum('sitasi'))
            .order_by('-jumlah')[:20]
        )

        # Top author berdasarkan artikel di DB
        from apps.universities.models import SintaAuthor
        top_author = list(
            SintaScopusArtikelAuthor.objects
            .values('author__nama', 'author__afiliasi__perguruan_tinggi__singkatan')
            .annotate(jumlah=Count('artikel_id'))
            .order_by('-jumlah')[:10]
        )

        return Response({
            'total_artikel': agg['total_artikel'] or 0,
            'total_sitasi':  agg['total_sitasi']  or 0,
            'total_jurnal':  total_jurnal,
            'total_author':  total_author,
            'q1q2':          q1q2,
            'dist_kuartil':  dist_kuartil,
            'tren_artikel':  tren_artikel,
            'tren_kuartil':  tren_kuartil,
            'tren_scopus_author':  tren_scopus_author,
            'tren_gscholar_pub':   tren_gscholar_pub,
            'tren_gscholar_cite':  tren_gscholar_cite,
            'top_jurnal':    top_jurnal,
            'top_author':    top_author,
        })

    @action(detail=False, methods=['get', 'post'], url_path='riset-analisis',
            permission_classes=[AllowAny])
    def riset_analisis(self, request):
        """
        GET  — Baca hasil analisis dari cache (publik, instan).
               Jika cache kosong kembalikan {"ready": false}.
        POST — Reset cache & trigger regenerasi (bebas, tanpa auth).
        """
        from django.core.cache import cache as _dcache
        _FULL_CACHE_KEY = 'riset_analisis_full_v2'

        # ── POST: bebas, siapapun bisa reset dan generate ulang ─────────
        if request.method == 'POST':
            _dcache.delete(_FULL_CACHE_KEY)
            from .models import RisetAnalisisSnapshot
            RisetAnalisisSnapshot.objects.all().delete()
            return Response({'status': 'cache_cleared', 'detail': 'Cache dan snapshot dihapus. Analisis baru akan dibuat pada permintaan berikutnya.'})

        # ── GET: kembalikan cache jika ada, generate jika kosong ─────
        if request.method == 'GET':
            cached = _dcache.get(_FULL_CACHE_KEY)
            if cached is not None:
                return Response(cached)
            # cache kosong — coba restore dari snapshot terbaru
            from .models import RisetAnalisisSnapshot
            snap = RisetAnalisisSnapshot.latest()
            if snap:
                _dcache.set(_FULL_CACHE_KEY, snap.data, timeout=604800)
                return Response(snap.data)
            # tidak ada snapshot — lanjut generate di bawah

        # ── Generate (POST atau GET saat cache kosong — admin saja bisa sampai sini via POST) ──
        import re
        import re
        from collections import Counter
        from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
        from sklearn.decomposition import LatentDirichletAllocation
        import numpy as np

        rows = list(SintaScopusArtikel.objects.values_list('judul', 'tahun'))
        titles = [r[0] for r in rows if r[0]]
        tahuns = [r[1] for r in rows if r[0]]

        # ── Stopwords ────────────────────────────────────────────────
        STOP = [
            'the','a','an','of','in','on','at','to','for','with','and','or','is','are',
            'was','were','be','been','have','has','had','do','does','did','will','would',
            'could','should','may','might','this','that','these','those','it','its','by',
            'from','as','into','through','during','before','after','when','where','which',
            'who','what','how','some','such','than','too','very','just','then','there',
            'also','but','not','only','more','most','each','both','all','any','same',
            'using','based','study','analysis','approach','method','methods','model','models',
            'system','systems','design','review','paper','novel','proposed','performance',
            'results','result','experimental','comparison','toward','towards','effect',
            'effects','impact','research','application','applications','case','development',
            'implementation','evaluation','assessment','investigation','potential','various',
            'different','high','new','used','show','shows','good','between','among','data',
            'type','types','process','level','number','factor','factors','rate','value',
            'work','can','well','thus','two','three','four','five','first','second','third',
            'test','tests','testing','measured','measure','found','show','showed','shows',
        ]

        # ── 1. TF-IDF Word Cloud ──────────────────────────────────────
        tfidf = TfidfVectorizer(
            max_features=80,
            stop_words=STOP,
            ngram_range=(1, 2),
            min_df=3,
            token_pattern=r'\b[a-zA-Z]{4,}\b',
        )
        tfidf_matrix = tfidf.fit_transform(titles)
        feature_names = tfidf.get_feature_names_out()
        tfidf_scores  = tfidf_matrix.sum(axis=0).A1
        word_cloud = sorted(
            [{'word': w, 'score': round(float(s), 3)}
             for w, s in zip(feature_names, tfidf_scores)],
            key=lambda x: -x['score']
        )[:60]

        # ── 2. LDA Topic Modelling ─────────────────────────────────────
        N_TOPICS = 8
        cv = CountVectorizer(
            max_features=500,
            stop_words=STOP,
            ngram_range=(1, 2),
            min_df=3,
            token_pattern=r'\b[a-zA-Z]{4,}\b',
        )
        cv_matrix = cv.fit_transform(titles)
        cv_features = cv.get_feature_names_out()

        lda = LatentDirichletAllocation(
            n_components=N_TOPICS,
            random_state=42,
            max_iter=20,
            learning_method='batch',
        )
        doc_topics = lda.fit_transform(cv_matrix)

        # Top words per topic
        topics_out = []
        for idx, comp in enumerate(lda.components_):
            top_idx   = comp.argsort()[-12:][::-1]
            top_words = [cv_features[i] for i in top_idx]
            article_count = int((doc_topics.argmax(axis=1) == idx).sum())
            # Auto-label dari 3 keyword teratas (title-case)
            label = ' · '.join(w.title() for w in top_words[:3])
            topics_out.append({
                'id':    idx,
                'label': label,
                'keywords': top_words,
                'article_count': article_count,
            })

        # Sort topics by article count descending
        topics_out.sort(key=lambda x: -x['article_count'])

        # ── 2b. Deskripsi per topik: DB → cache → fixture → hardcoded → LLM ──
        from django.core.cache import cache as _cache
        from .models import RisetLdaDeskripsi as _LdaDesc
        import json as _json, os as _os

        # 1. Baca dari DB (permanen)
        _db_descs = {row.label: row.deskripsi
                     for row in _LdaDesc.objects.all()}

        # 2. Fallback cache (24h) untuk label yang belum ada di DB
        _CACHE_KEY = 'riset_analisis_deskripsi_v4'
        _cached_descs = dict(_cache.get(_CACHE_KEY) or {})
        _cached_descs.update(_db_descs)  # DB selalu prioritas

        # 3. Fallback file fixture
        if len(_cached_descs) < len(topics_out):
            _fixture_path = _os.path.join(_os.path.dirname(__file__), 'fixtures', 'riset_analisis_deskripsi.json')
            if _os.path.exists(_fixture_path):
                with open(_fixture_path, encoding='utf-8') as _f:
                    for k, v in _json.load(_f).items():
                        _cached_descs.setdefault(k, v)

        # 4. Fallback hardcoded
        _BUILTIN_DESCS = {
            'Learning & Development & Based': 'Dosen PTMA aktif meneliti bidang pendidikan dan pengembangan pembelajaran berbasis konstruktivisme. Fokus riset mencakup efektivitas model pembelajaran aktif, integrasi teknologi digital, dan peningkatan kemampuan akademik siswa. Tren berkembang ke arah pembelajaran adaptif dan personalisasi kurikulum. Riset ini berkontribusi langsung pada peningkatan kualitas pendidikan nasional di lingkungan Muhammadiyah-Aisyiyah.',
            'Indonesia & 19 & Study': 'Riset ini memusatkan perhatian pada dampak pandemi COVID-19 di Indonesia dari berbagai dimensi — kesehatan, ekonomi, dan sosial. Dosen PTMA aktif mengkaji pola penyebaran, kebijakan penanganan, serta dampak jangka panjang pandemi terhadap masyarakat. Tren riset berkembang ke arah analisis pemulihan pasca-pandemi dan ketahanan sistem kesehatan. Hasil riset berperan penting dalam memberikan rekomendasi kebijakan berbasis data.',
            'From & Oil & As': 'Bidang ini mencakup riset material dan rekayasa, khususnya pemanfaatan ekstrak alam dan limbah industri sebagai bahan konstruksi. Dosen PTMA meneliti sifat mekanis material alternatif seperti pemanfaatan minyak nabati dan produk sampingan industri untuk campuran beton. Tren mengarah pada material berkelanjutan dan ramah lingkungan. Riset ini relevan untuk mendukung industri konstruksi yang lebih efisien dan berwawasan lingkungan.',
            'Using & Learning & Students': 'Riset ini mengkaji metode pengajaran inovatif berbasis student-centered learning untuk meningkatkan hasil belajar mahasiswa. Fokus mencakup pendekatan inquiry-based, problem-solving, dan blended learning. Tren berkembang pada integrasi platform digital dan gamifikasi dalam proses pembelajaran. Dampaknya signifikan dalam meningkatkan motivasi, partisipasi aktif, dan prestasi akademik mahasiswa di perguruan tinggi.',
            'Performance & Using & Analysis': 'Dosen PTMA meneliti analisis kinerja sistem teknis dan operasional, dengan fokus pada optimasi performa menggunakan pendekatan kuantitatif. Bidang ini mencakup sistem energi terbarukan, efisiensi operasional industri, dan analisis data kinerja. Tren berkembang pada penggunaan machine learning untuk prediksi dan optimasi sistem. Riset ini berdampak pada peningkatan efisiensi industri dan pengembangan teknologi energi di Indonesia.',
            'Based & Using & Treatment': 'Riset ini berfokus pada pengolahan limbah dan aktivitas antioksidan, mengkaji efek berbagai perlakuan terhadap sifat biologis bahan. Dosen PTMA aktif meneliti potensi ekstrak alami dan proses bioteknologi untuk aplikasi kesehatan dan lingkungan. Tren mengarah pada pemanfaatan bahan herbal lokal Indonesia sebagai sumber antioksidan. Riset ini berpotensi mendukung pengembangan produk kesehatan berbasis bahan alam.',
            'Review & Analysis & Indonesian': 'Bidang ini mencakup kajian review sistematis dan analisis komprehensif tentang perkembangan ilmu pengetahuan Indonesia. Dosen PTMA aktif melakukan meta-analisis dan tinjauan literatur untuk mengidentifikasi tren riset nasional. Fokus mencakup pemetaan kinerja sains Indonesia dalam konteks global. Riset ini penting untuk perencanaan kebijakan riset dan pengembangan kapasitas ilmiah perguruan tinggi.',
            'Indonesia & Learning & Behavior': 'Riset ini mengkaji perilaku belajar dan faktor psikososial yang memengaruhi prestasi akademik siswa Indonesia. Dosen PTMA meneliti pengaruh lingkungan keluarga, budaya, dan teknologi terhadap motivasi dan gaya belajar. Tren berkembang pada riset perilaku digital dan penggunaan media sosial dalam konteks pendidikan. Hasil riset berkontribusi pada pengembangan pendekatan pendidikan yang kontekstual dan berbasis kearifan lokal.',
        }
        for k, v in _BUILTIN_DESCS.items():
            _cached_descs.setdefault(k, v)

        # 5. Generate LLM untuk label baru yang belum ada di semua fallback
        _needs_gen = [t for t in topics_out if t['label'] not in _cached_descs]
        if _needs_gen:
            try:
                import torch as _torch
                from transformers import AutoModelForCausalLM as _CausalLM, AutoTokenizer as _Tok
                _model_id = 'Qwen/Qwen2.5-0.5B-Instruct'
                _tok = _Tok.from_pretrained(_model_id)
                _mdl = _CausalLM.from_pretrained(_model_id, dtype=_torch.float32)
                _mdl.eval()

                for t in _needs_gen:
                    kw_str = ', '.join(t['keywords'][:8])
                    msgs = [
                        {'role': 'system', 'content': 'Kamu adalah analis riset perguruan tinggi Indonesia yang menulis laporan ilmiah.'},
                        {'role': 'user',   'content': (
                            f"Dosen PTMA (Perguruan Tinggi Muhammadiyah-Aisyiyah) menerbitkan artikel Scopus "
                            f"dengan kata kunci: {kw_str}. "
                            f"Tulis satu paragraf singkat (4-5 kalimat) dalam Bahasa Indonesia yang menjelaskan: "
                            f"(1) bidang riset utama yang sedang dikerjakan, "
                            f"(2) fokus dan tren yang berkembang, "
                            f"(3) relevansi atau dampak riset tersebut."
                        )},
                    ]
                    text = _tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
                    inputs = _tok([text], return_tensors='pt')
                    with _torch.no_grad():
                        out = _mdl.generate(**inputs, max_new_tokens=220, do_sample=False)
                    gen_ids = out[0][inputs.input_ids.shape[1]:]
                    raw = _tok.decode(gen_ids, skip_special_tokens=True).strip()
                    import re as _re
                    raw = _re.sub(r'[^\x00-\x7F\u00C0-\u024F\u0020-\u007E\u00A0-\u00FF\u0100-\u017E\u2018-\u201D\u2026]', '', raw)
                    raw = _re.sub(r' {2,}', ' ', raw).strip()
                    _cached_descs[t['label']] = raw

                _cache.set(_CACHE_KEY, _cached_descs, timeout=86400)
            except Exception:
                pass

        # Simpan deskripsi baru ke DB (update_or_create per label)
        _new_labels = {t['label'] for t in topics_out} - set(_db_descs.keys())
        for _lbl in _new_labels:
            if _cached_descs.get(_lbl):
                _LdaDesc.objects.update_or_create(
                    label=_lbl, defaults={'deskripsi': _cached_descs[_lbl]}
                )

        for t in topics_out:
            t['deskripsi'] = _cached_descs.get(t['label'], '')

        # ── 3. Trending keywords per year (TF-IDF per year) ───────────
        by_year: dict = {}
        for judul, tahun in zip(titles, tahuns):
            if tahun and 2015 <= tahun <= 2025:
                by_year.setdefault(int(tahun), []).append(judul)

        trending_by_year = {}
        for yr in sorted(by_year.keys()):
            docs = by_year[yr]
            if len(docs) < 5:
                continue
            vec = TfidfVectorizer(
                max_features=100, stop_words=STOP,
                ngram_range=(1,1), min_df=2,
                token_pattern=r'\b[a-zA-Z]{4,}\b',
            )
            mat = vec.fit_transform(docs)
            names  = vec.get_feature_names_out()
            scores = mat.sum(axis=0).A1
            top = sorted(zip(names, scores), key=lambda x: -x[1])[:8]
            trending_by_year[str(yr)] = [{'word': w, 'score': round(float(s), 3)} for w, s in top]

        # ── 4. Topic share per year ────────────────────────────────────
        topic_year: dict = {}
        for i, (judul, tahun) in enumerate(zip(titles, tahuns)):
            if not tahun or not (2015 <= tahun <= 2025):
                continue
            dominant = int(doc_topics[i].argmax())
            label    = topics_out[dominant]['label'] if dominant < len(topics_out) else f'Topik {dominant}'
            k = str(tahun)
            topic_year.setdefault(k, Counter())[label] += 1

        topic_per_year = {
            yr: [{'label': t, 'count': c} for t, c in counts.most_common(5)]
            for yr, counts in sorted(topic_year.items())
        }

        # ── 5. Klasifikasi WCU Broad Subject Areas ────────────────────
        WCU_FIELDS = {
            'Engineering & Technology': {
                'id': 'engineering', 'color': '#2563eb',
                'keywords': [
                    'algorithm','optimization','convolutional','classification','detection',
                    'iot','blockchain','software','database','cloud','wireless','circuit',
                    'solar','control','robot','automation','concrete','polymer','composite',
                    'membrane','thermal','mechanical','electrical','fuel','turbine',
                    'construction','building','manufacturing','electronic','semiconductor',
                    'microcontroller','signal','encryption','sensor','voltage','battery',
                    'capacitor','antenna','power','energy','deep','neural','machine',
                    'reinforcement','transfer','computer','vision','language','intelligent',
                    'autonomous','drone','lidar','radar','embedded','microprocessor',
                    'renewable','photovoltaic','wind','geothermal','hydrogen','biomass',
                ],
                'bigrams': [
                    'machine learning','deep learning','reinforcement learning','transfer learning',
                    'computer vision','natural language','smart grid','artificial intelligence',
                    'internet of things','digital twin','edge computing','renewable energy',
                    'neural network','image processing','feature extraction','object detection',
                ],
            },
            'Life Sciences & Medicine': {
                'id': 'lifescience', 'color': '#16a34a',
                'keywords': [
                    'covid','pandemic','health','disease','diabetes','cancer','clinical',
                    'patient','drug','medical','hospital','treatment','therapy','blood',
                    'vaccine','antioxidant','extract','herbal','pharmacology','biology',
                    'cell','protein','enzyme','microbiology','ecology','plant','animal',
                    'genetics','zoology','botany','rice','food','nutrition','livestock',
                    'fish','aquaculture','veterinary','pathogen','bacteria','virus',
                    'antibacterial','antimicrobial','toxicity','bioactive','phytochemical',
                    'flavonoid','leaves','seed','fruit','stem','root','crop','fertilizer',
                    'pesticide','harvest','antifungal','antibiotics','inflammation','wound',
                    'liver','kidney','mortality','morbidity','prevalence','incidence',
                    'mutation','chromosome','genome','metabolite','alkaloid','phenolic',
                ],
                'bigrams': [
                    'essential oil','blood pressure','blood glucose','immune system',
                    'oxidative stress','in vitro','in vivo','clinical trial',
                    'systematic review','meta analysis','risk factor','medicinal plant',
                ],
            },
            'Natural Sciences': {
                'id': 'natural', 'color': '#0891b2',
                'keywords': [
                    'physics','chemistry','mathematics','statistics','geology','earthquake',
                    'environment','water','climate','carbon','emission','waste',
                    'pollution','quantum','molecular','nano','crystallography','mineral',
                    'spectroscopy','thermodynamics','fluid','acoustic','optic','photon',
                    'radiation','isotope','sediment','geothermal','atmospheric',
                    'ocean','river','lake','forest','biodiversity','ecosystem','soil',
                    'rainfall','drought','volcano','landslide','tsunami','calculus',
                    'algebra','topology','differential','integral','probability',
                    'simulation','modelling','numerical','finite','element',
                ],
                'bigrams': [
                    'greenhouse gas','global warming','climate change','heavy metal',
                    'wastewater treatment','water quality','soil contamination',
                    'groundwater','surface water','air quality','noise pollution',
                ],
            },
            'Social Sciences & Management': {
                'id': 'social', 'color': '#d97706',
                'keywords': [
                    'economic','finance','market','business','management','investment',
                    'performance','firm','bank','financial','revenue','education','student',
                    'school','curriculum','teaching','social','community','society',
                    'governance','policy','law','politics','psychology','tourism','urban',
                    'city','zakat','waqf','accounting','audit','taxation','trade',
                    'consumer','marketing','organization','leadership','literacy','poverty',
                    'welfare','employment','salary','teacher','pedagogy','learning',
                    'knowledge','competence','motivation','attitude','perception',
                    'satisfaction','loyalty','productivity','innovation','entrepreneurship',
                    'startup','ecommerce','fintech','microfinance','cooperative','village',
                    'district','region','province','indonesia','indonesian','local',
                ],
                'bigrams': [
                    'supply chain','human resource','public policy','local government',
                    'small medium','micro enterprise','digital economy','critical thinking',
                    'problem solving','project based','cooperative learning','game based',
                    'blended learning','flipped classroom','higher education',
                ],
            },
            'Arts & Humanities': {
                'id': 'arts', 'color': '#9333ea',
                'keywords': [
                    'literature','history','art','culture','religion','philosophy',
                    'linguistics','language','arabic','quran','hadith','heritage','music',
                    'theater','film','journalism','communication','discourse',
                    'narrative','translation','poetry','novel','folklore','tradition',
                    'manuscript','archaeology','ethnography','anthropology','identity',
                    'ideology','ethics','moral','islamic','mosque','madrasa','pesantren',
                    'sufism','fiqh','tafsir','sharia','halal','fatwa','ijtihad',
                    'calligraphy','batik','wayang','gamelan','architecture','design',
                    'graphic','typography','visual','aesthetics','semiotics',
                ],
                'bigrams': [
                    'cultural identity','social media','content analysis','discourse analysis',
                    'thematic analysis','islamic education','character education',
                    'moral education','religious education',
                ],
            },
        }

        def classify_wcu(title_lower):
            scores = {f: 0 for f in WCU_FIELDS}
            words = set(re.findall(r'\b[a-z]{3,}\b', title_lower))
            # Bigram matching (higher weight)
            for field, cfg in WCU_FIELDS.items():
                for bg in cfg.get('bigrams', []):
                    if bg in title_lower:
                        scores[field] += 3
            # Single keyword matching
            for field, cfg in WCU_FIELDS.items():
                scores[field] += len(words & set(cfg['keywords']))
            best = max(scores, key=scores.get)
            return best if scores[best] > 0 else 'Social Sciences & Management'

        # Klasifikasi per artikel
        wcu_counts = Counter()
        wcu_by_year: dict = {}
        for judul, tahun in zip(titles, tahuns):
            field = classify_wcu(judul.lower())
            wcu_counts[field] += 1
            if tahun and 2015 <= tahun <= 2025:
                wcu_by_year.setdefault(int(tahun), Counter())[field] += 1

        total = len(titles) or 1
        wcu_distribution = []
        for field, cfg in WCU_FIELDS.items():
            count = wcu_counts.get(field, 0)
            # Kumpulkan LDA topics yang masuk field ini
            related_topics = []
            for t in topics_out:
                t_kws = set(t['keywords'])
                field_kws = set(cfg['keywords'][:20])
                if len(t_kws & field_kws) >= 1:
                    related_topics.append(t['label'])
            wcu_distribution.append({
                'field':   field,
                'field_id': cfg['id'],
                'color':   cfg['color'],
                'count':   count,
                'pct':     round(count / total * 100, 1),
                'topics':  related_topics,
            })
        wcu_distribution.sort(key=lambda x: -x['count'])

        # WCU tren per tahun (normalized per tahun)
        wcu_trend_year = {}
        for yr in sorted(wcu_by_year.keys()):
            yr_total = sum(wcu_by_year[yr].values()) or 1
            wcu_trend_year[str(yr)] = [
                {'field': f, 'field_id': WCU_FIELDS[f]['id'], 'color': WCU_FIELDS[f]['color'],
                 'count': wcu_by_year[yr].get(f, 0),
                 'pct': round(wcu_by_year[yr].get(f, 0) / yr_total * 100, 1)}
                for f in WCU_FIELDS
            ]

        # Tambahkan wcu_field ke setiap LDA topic
        for t in topics_out:
            kw_text = ' '.join(t['keywords'])
            t['wcu_field'] = classify_wcu(kw_text.lower())
            t['wcu_color'] = WCU_FIELDS[t['wcu_field']]['color']
            t['wcu_id']    = WCU_FIELDS[t['wcu_field']]['id']

        result = {
            'ready':            True,
            'total_titles':     len(titles),
            'word_cloud':       word_cloud,
            'lda_topics':       topics_out,
            'trending_by_year': trending_by_year,
            'topic_per_year':   topic_per_year,
            'wcu_distribution': wcu_distribution,
            'wcu_trend_year':   wcu_trend_year,
        }
        # Simpan ke full cache (7 hari) dan snapshot DB (maks 4, FIFO)
        _dcache.set(_FULL_CACHE_KEY, result, timeout=604800)
        from .models import RisetAnalisisSnapshot
        RisetAnalisisSnapshot.save_snapshot(result)
        return Response(result)


class SintaPengabdianViewSet(PublicReadAdminWriteMixin, viewsets.ReadOnlyModelViewSet):
    """
    Data pengabdian masyarakat dosen PTMA dari SINTA.

    GET /api/sinta-pengabdian/                    - Daftar (paginasi)
    GET /api/sinta-pengabdian/?tahun=2023          - Filter tahun
    GET /api/sinta-pengabdian/?skema_kode=PKM      - Filter kode skema
    GET /api/sinta-pengabdian/?sumber=DIKTI        - Filter sumber dana
    GET /api/sinta-pengabdian/?search=kata         - Cari judul / nama ketua
    GET /api/sinta-pengabdian/stats/               - Statistik agregat
    """
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'tahun':      ['exact', 'gte', 'lte'],
        'skema_kode': ['exact'],
        'sumber':     ['exact'],
    }
    search_fields   = ['judul', 'leader_nama']
    ordering_fields = ['tahun', 'judul', 'skema_kode', 'sumber', 'dana']
    ordering        = ['-tahun', 'judul']

    def get_queryset(self):
        return (
            SintaPengabdian.objects
            .prefetch_related('pengabdian_authors__author__afiliasi__perguruan_tinggi')
            .order_by('-tahun', 'judul')
        )

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())

        page_size = min(int(request.query_params.get('page_size', 20)), 200)
        page      = int(request.query_params.get('page', 1))
        total     = qs.count()
        items     = qs[(page - 1) * page_size: page * page_size]

        results = []
        for p in items:
            authors = []
            for r in p.pengabdian_authors.all():
                pt_singkatan = ''
                try:
                    if r.author.afiliasi_id and r.author.afiliasi and r.author.afiliasi.perguruan_tinggi_id:
                        pt_singkatan = r.author.afiliasi.perguruan_tinggi.singkatan
                except Exception:
                    pass
                authors.append({
                    'author_id':   r.author_id,
                    'nama':        r.author.nama,
                    'sinta_id':    r.author.sinta_id,
                    'pt_singkatan': pt_singkatan,
                    'is_leader':   r.is_leader,
                })
            results.append({
                'id':          p.id,
                'judul':       p.judul,
                'leader_nama': p.leader_nama,
                'skema':       p.skema,
                'skema_kode':  p.skema_kode,
                'tahun':       p.tahun,
                'dana':        p.dana,
                'status':      p.status,
                'sumber':      p.sumber,
                'authors':     authors,
            })

        return Response({
            'count':     total,
            'page':      page,
            'page_size': page_size,
            'results':   results,
        })

    @action(detail=False, methods=['get'], url_path='stats', permission_classes=[AllowAny])
    def stats(self, request):
        total_pengabdian = SintaPengabdian.objects.count()
        total_author = SintaPengabdianAuthor.objects.values('author').distinct().count()

        # Tren dari SintaAuthorTrend (semua author yg sudah di-scrape)
        tren_service = list(
            SintaAuthorTrend.objects.filter(jenis='service')
            .values('tahun')
            .annotate(jumlah=Sum('jumlah'))
            .order_by('tahun')
        )

        # Tren jumlah judul pengabdian per tahun (dari tabel SintaPengabdian)
        tren_judul = list(
            SintaPengabdian.objects
            .exclude(tahun=None)
            .values('tahun')
            .annotate(jumlah=Count('id'))
            .order_by('tahun')
        )

        # Top skema
        top_skema = list(
            SintaPengabdian.objects
            .exclude(skema='')
            .values('skema')
            .annotate(jumlah=Count('id'))
            .order_by('-jumlah')[:15]
        )

        # Top sumber dana
        top_sumber = list(
            SintaPengabdian.objects
            .exclude(sumber='')
            .values('sumber')
            .annotate(jumlah=Count('id'))
            .order_by('-jumlah')[:10]
        )

        # Top ketua — pakai SintaPengabdianAuthor(is_leader=True) agar dapat author_id
        top_ketua = list(
            SintaPengabdianAuthor.objects
            .filter(is_leader=True)
            .values('author_id', 'author__nama',
                    'author__afiliasi__perguruan_tinggi__singkatan')
            .annotate(jumlah=Count('pengabdian_id', distinct=True))
            .order_by('-jumlah')[:10]
        )
        # Normalisasi key nama
        top_ketua = [
            {
                'author_id':   r['author_id'],
                'leader_nama': r['author__nama'],
                'pt_singkatan': r['author__afiliasi__perguruan_tinggi__singkatan'] or '',
                'jumlah':      r['jumlah'],
            }
            for r in top_ketua
        ]

        # Daftar pilihan filter
        tahun_list = list(
            SintaPengabdian.objects
            .exclude(tahun=None)
            .values_list('tahun', flat=True)
            .distinct()
            .order_by('-tahun')
        )
        sumber_list = list(
            SintaPengabdian.objects
            .exclude(sumber='')
            .values_list('sumber', flat=True)
            .distinct()
            .order_by('sumber')
        )
        skema_kode_list = list(
            SintaPengabdian.objects
            .exclude(skema_kode='')
            .values('skema_kode', 'skema')
            .annotate(jumlah=Count('id'))
            .order_by('-jumlah')[:30]
        )

        return Response({
            'total_pengabdian': total_pengabdian,
            'total_author':     total_author,
            'tren_service':     tren_service,
            'tren_judul':       tren_judul,
            'top_skema':        top_skema,
            'top_sumber':       top_sumber,
            'top_ketua':        top_ketua,
            'tahun_list':       tahun_list,
            'sumber_list':      sumber_list,
            'skema_kode_list':  skema_kode_list,
        })


class SintaPenelitianViewSet(PublicReadAdminWriteMixin, viewsets.ReadOnlyModelViewSet):
    """
    Data penelitian dosen PTMA dari SINTA.

    GET /api/sinta-penelitian/                    - Daftar (paginasi)
    GET /api/sinta-penelitian/?tahun=2023          - Filter tahun
    GET /api/sinta-penelitian/?skema_kode=PKM      - Filter kode skema
    GET /api/sinta-penelitian/?sumber=DIKTI        - Filter sumber dana
    GET /api/sinta-penelitian/?search=kata         - Cari judul / nama ketua
    GET /api/sinta-penelitian/?ordering=-tahun     - Urutan (judul, tahun, skema_kode, sumber, dana)
    GET /api/sinta-penelitian/stats/               - Statistik agregat
    """
    filter_backends  = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'tahun':      ['exact', 'gte', 'lte'],
        'skema_kode': ['exact'],
        'sumber':     ['exact'],
    }
    search_fields   = ['judul', 'leader_nama']
    ordering_fields = ['tahun', 'judul', 'skema_kode', 'sumber', 'dana']
    ordering        = ['-tahun', 'judul']

    def get_queryset(self):
        return (
            SintaPenelitian.objects
            .prefetch_related('penelitian_authors__author__afiliasi__perguruan_tinggi')
            .order_by('-tahun', 'judul')
        )

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())

        page_size = min(int(request.query_params.get('page_size', 20)), 200)
        page      = int(request.query_params.get('page', 1))
        total     = qs.count()
        items     = qs[(page - 1) * page_size: page * page_size]

        results = []
        for p in items:
            authors = []
            for r in p.penelitian_authors.all():
                pt_singkatan = ''
                try:
                    if r.author.afiliasi_id and r.author.afiliasi and r.author.afiliasi.perguruan_tinggi_id:
                        pt_singkatan = r.author.afiliasi.perguruan_tinggi.singkatan
                except Exception:
                    pass
                authors.append({
                    'author_id':    r.author_id,
                    'nama':         r.author.nama,
                    'sinta_id':     r.author.sinta_id,
                    'pt_singkatan': pt_singkatan,
                    'is_leader':    r.is_leader,
                })
            results.append({
                'id':          p.id,
                'judul':       p.judul,
                'leader_nama': p.leader_nama,
                'skema':       p.skema,
                'skema_kode':  p.skema_kode,
                'tahun':       p.tahun,
                'dana':        p.dana,
                'status':      p.status,
                'sumber':      p.sumber,
                'authors':     authors,
            })

        return Response({
            'count':     total,
            'page':      page,
            'page_size': page_size,
            'results':   results,
        })

    @action(detail=False, methods=['get'], url_path='stats', permission_classes=[AllowAny])
    def stats(self, request):
        total_penelitian = SintaPenelitian.objects.count()
        total_author = SintaPenelitianAuthor.objects.values('author').distinct().count()

        # Tren dari SintaAuthorTrend (jenis='research')
        tren_research = list(
            SintaAuthorTrend.objects.filter(jenis='research')
            .values('tahun')
            .annotate(jumlah=Sum('jumlah'))
            .order_by('tahun')
        )

        # Tren jumlah judul penelitian per tahun (dari tabel SintaPenelitian)
        tren_judul = list(
            SintaPenelitian.objects
            .exclude(tahun=None)
            .values('tahun')
            .annotate(jumlah=Count('id'))
            .order_by('tahun')
        )

        # Top skema
        top_skema = list(
            SintaPenelitian.objects
            .exclude(skema='')
            .values('skema')
            .annotate(jumlah=Count('id'))
            .order_by('-jumlah')[:15]
        )

        # Top sumber dana
        top_sumber = list(
            SintaPenelitian.objects
            .exclude(sumber='')
            .values('sumber')
            .annotate(jumlah=Count('id'))
            .order_by('-jumlah')[:10]
        )

        # Top ketua — pakai SintaPenelitianAuthor(is_leader=True) agar dapat author_id
        top_ketua = list(
            SintaPenelitianAuthor.objects
            .filter(is_leader=True)
            .values('author_id', 'author__nama',
                    'author__afiliasi__perguruan_tinggi__singkatan')
            .annotate(jumlah=Count('penelitian_id', distinct=True))
            .order_by('-jumlah')[:10]
        )
        top_ketua = [
            {
                'author_id':    r['author_id'],
                'leader_nama':  r['author__nama'],
                'pt_singkatan': r['author__afiliasi__perguruan_tinggi__singkatan'] or '',
                'jumlah':       r['jumlah'],
            }
            for r in top_ketua
        ]

        # Daftar pilihan filter
        tahun_list = list(
            SintaPenelitian.objects
            .exclude(tahun=None)
            .values_list('tahun', flat=True)
            .distinct()
            .order_by('-tahun')
        )
        sumber_list = list(
            SintaPenelitian.objects
            .exclude(sumber='')
            .values_list('sumber', flat=True)
            .distinct()
            .order_by('sumber')
        )
        skema_kode_list = list(
            SintaPenelitian.objects
            .exclude(skema_kode='')
            .values('skema_kode', 'skema')
            .annotate(jumlah=Count('id'))
            .order_by('-jumlah')[:30]
        )

        return Response({
            'total_penelitian': total_penelitian,
            'total_author':     total_author,
            'tren_research':    tren_research,
            'tren_judul':       tren_judul,
            'top_skema':        top_skema,
            'top_sumber':       top_sumber,
            'top_ketua':        top_ketua,
            'tahun_list':       tahun_list,
            'sumber_list':      sumber_list,
            'skema_kode_list':  skema_kode_list,
        })


class KolaboasiViewSet(PublicReadAdminWriteMixin, viewsets.ViewSet):
    """
    Jaringan kerjasama antar peneliti PTMA (co-authorship network).

    GET /api/sinta-kolaborasi/graph/
        ?sumber=all|penelitian|pengabdian|scopus
        ?min_bobot=1
        ?max_nodes=400
        ?force=1   (paksa recompute, admin only)

    GET /api/sinta-kolaborasi/stats/   – ringkasan cepat dari snapshot terakhir
    """

    @action(detail=False, methods=['get'], url_path='graph',
            permission_classes=[AllowAny])
    def graph(self, request):
        sumber    = request.query_params.get('sumber', 'all')
        min_bobot = int(request.query_params.get('min_bobot', 1))
        max_nodes = int(request.query_params.get('max_nodes', 400))
        force     = request.query_params.get('force', '0') == '1'

        if sumber not in ('all', 'penelitian', 'pengabdian', 'scopus'):
            sumber = 'all'
        min_bobot = max(1, min(min_bobot, 10))
        max_nodes = max(50, min(max_nodes, 800))

        # Gunakan snapshot cache jika tersedia dan tidak force-recompute
        snap = KolaboasiSnapshot.latest(sumber=sumber)
        if snap and not force:
            data = snap.data
            # Filter ulang max_nodes di sisi server jika perlu
            if len(data.get('nodes', [])) > max_nodes:
                nodes = data['nodes'][:max_nodes]
                node_ids = {n['id'] for n in nodes}
                edges = [e for e in data.get('edges', [])
                         if e['source'] in node_ids and e['target'] in node_ids]
                data = {**data, 'nodes': nodes, 'edges': edges,
                        'cached': True,
                        'cached_at': snap.created_at.isoformat()}
            else:
                data = {**data, 'cached': True,
                        'cached_at': snap.created_at.isoformat()}
            return Response(data)

        # Recompute (admin or no snapshot)
        if not request.user.is_staff and snap:
            # Non-admin tidak bisa force recompute, kembalikan cache
            return Response({**snap.data, 'cached': True,
                             'cached_at': snap.created_at.isoformat()})

        try:
            import io as _io
            from utils.sinta.build_kolaboasi_graph import build_graph
            # Redirect stdout ke StringIO agar print() di build_graph tidak
            # crash dengan UnicodeEncodeError pada judul yang mengandung karakter
            # non-ASCII (mis. '…') di lingkungan server dengan locale ASCII.
            _old_stdout = sys.stdout
            sys.stdout = _io.StringIO()
            try:
                result = build_graph(sumber=sumber, min_bobot=min_bobot,
                                     max_nodes=max_nodes)
            finally:
                sys.stdout = _old_stdout
            if result.get('ready'):
                KolaboasiSnapshot.save_snapshot(result, sumber=sumber,
                                                min_bobot=min_bobot)
            return Response(result)
        except Exception as e:
            return Response({'ready': False, 'error': str(e)}, status=500)

    @action(detail=False, methods=['get'], url_path='stats',
            permission_classes=[AllowAny])
    def stats(self, request):
        sumber = request.query_params.get('sumber', 'all')
        snap   = KolaboasiSnapshot.latest(sumber=sumber)
        if not snap:
            return Response({'ready': False,
                             'message': 'Belum ada snapshot. Hit /graph/ dulu.'})
        d = snap.data
        return Response({
            'ready':           d.get('ready', False),
            'sumber':          d.get('sumber'),
            'cached_at':       snap.created_at.isoformat(),
            'stats':           d.get('stats', {}),
            'komunitas_list':  d.get('komunitas_list', []),
            'top_pairs':       d.get('top_pairs', []),
            'top_degree':      d.get('top_degree', []),
            'top_betweenness': d.get('top_betweenness', []),
            'top_pt':          d.get('top_pt', []),
        })


@api_view(['GET'])
@permission_classes([AllowAny])
def proxy_image_b64(request):
    """Fetch external image URL server-side, return as base64 data URI (bypass browser CORS)."""
    import urllib.request, base64 as b64mod
    url = request.query_params.get('url', '').strip()
    if not url or not url.startswith('http'):
        return Response('')
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; PTMA-Bot/1.0)'
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            ct = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
            data = b64mod.b64encode(resp.read()).decode()
            return Response(f'data:{ct};base64,{data}')
    except Exception:
        return Response('')


# ── Sinkronisasi Jadwal ──────────────────────────────────────────────────────

import os
import signal
import subprocess
import sys
from pathlib import Path
from django.utils import timezone

from .models import SinkronisasiJadwal


def _is_process_alive(pid):
    """Cek apakah proses dengan PID masih berjalan."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _jadwal_to_dict(j):
    return {
        'id': j.id,
        'tipe_sync': j.tipe_sync,
        'tipe_sync_label': j.get_tipe_sync_display(),
        'mode_pt': j.mode_pt,
        'pt_list': [{'id': p.id, 'nama': p.nama, 'singkatan': p.singkatan, 'kode_pt': p.kode_pt}
                    for p in j.pt_list.all()],
        'tipe_jadwal': j.tipe_jadwal,
        'tipe_jadwal_label': j.get_tipe_jadwal_display(),
        'hari_mulai': j.hari_mulai,
        'hari_mulai_label': dict(SinkronisasiJadwal.HARI_CHOICES).get(j.hari_mulai, ''),
        'jam_mulai': j.jam_mulai.strftime('%H:%M') if j.jam_mulai else '',
        'hari_selesai': j.hari_selesai,
        'hari_selesai_label': dict(SinkronisasiJadwal.HARI_CHOICES).get(j.hari_selesai, ''),
        'jam_selesai': j.jam_selesai.strftime('%H:%M') if j.jam_selesai else '',
        'is_active': j.is_active,
        'sinta_days': j.sinta_days,
        'sinta_limit': j.sinta_limit,
        'status_terakhir': j.status_terakhir,
        'pesan_terakhir': j.pesan_terakhir,
        'pid': j.pid,
        'last_run': j.last_run.isoformat() if j.last_run else None,
        'created_at': j.created_at.isoformat(),
    }


class IsSuperAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and getattr(request.user, 'role', '') == 'superadmin'


@api_view(['GET', 'POST'])
@permission_classes([IsSuperAdmin])
def sync_jadwal_list(request):
    """List semua jadwal (GET) atau buat jadwal baru (POST)."""
    if request.method == 'GET':
        jadwals = SinkronisasiJadwal.objects.prefetch_related('pt_list').all()
        return Response([_jadwal_to_dict(j) for j in jadwals])

    # POST — buat jadwal baru
    d = request.data
    try:
        jadwal = SinkronisasiJadwal.objects.create(
            tipe_sync    = d.get('tipe_sync', 'prodi_dosen'),
            mode_pt      = d.get('mode_pt', 'semua'),
            tipe_jadwal  = d.get('tipe_jadwal', 'harian'),
            hari_mulai   = int(d.get('hari_mulai', 0)),
            jam_mulai    = d.get('jam_mulai', '23:00'),
            hari_selesai = int(d.get('hari_selesai', 6)),
            jam_selesai  = d.get('jam_selesai', '05:00'),
            is_active    = bool(d.get('is_active', True)),
            sinta_days   = int(d.get('sinta_days', 30)),
            sinta_limit  = int(d.get('sinta_limit', 500)),
            created_by   = request.user,
        )
        pt_ids = d.get('pt_ids', [])
        if pt_ids:
            jadwal.pt_list.set(PerguruanTinggi.objects.filter(id__in=pt_ids))
        return Response({'id': jadwal.id, 'detail': 'Jadwal berhasil disimpan.'}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsSuperAdmin])
def sync_jadwal_detail(request, pk):
    """Update (PUT) atau hapus (DELETE) jadwal sinkronisasi."""
    try:
        jadwal = SinkronisasiJadwal.objects.get(pk=pk)
    except SinkronisasiJadwal.DoesNotExist:
        return Response({'detail': 'Tidak ditemukan.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'DELETE':
        jadwal.delete()
        return Response({'detail': 'Jadwal dihapus.'})

    d = request.data
    jadwal.tipe_sync    = d.get('tipe_sync', jadwal.tipe_sync)
    jadwal.mode_pt      = d.get('mode_pt', jadwal.mode_pt)
    jadwal.tipe_jadwal  = d.get('tipe_jadwal', jadwal.tipe_jadwal)
    jadwal.hari_mulai   = int(d.get('hari_mulai', jadwal.hari_mulai))
    jadwal.jam_mulai    = d.get('jam_mulai', jadwal.jam_mulai)
    jadwal.hari_selesai = int(d.get('hari_selesai', jadwal.hari_selesai))
    jadwal.jam_selesai  = d.get('jam_selesai', jadwal.jam_selesai)
    jadwal.is_active    = bool(d.get('is_active', jadwal.is_active))
    jadwal.sinta_days   = int(d.get('sinta_days', jadwal.sinta_days))
    jadwal.sinta_limit  = int(d.get('sinta_limit', jadwal.sinta_limit))
    jadwal.save()
    pt_ids = d.get('pt_ids')
    if pt_ids is not None:
        jadwal.pt_list.set(PerguruanTinggi.objects.filter(id__in=pt_ids))
    return Response({'detail': 'Jadwal diperbarui.'})


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def sync_pt_list(request):
    """Daftar semua PT untuk dropdown pemilihan (id, nama, singkatan, kode_pt)."""
    pts = PerguruanTinggi.objects.values('id', 'nama', 'singkatan', 'kode_pt').order_by('nama')
    return Response(list(pts))


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def sync_status(request, pk):
    """Status terkini satu jadwal — dengan zombie detection."""
    try:
        jadwal = SinkronisasiJadwal.objects.prefetch_related('pt_list').get(pk=pk)
    except SinkronisasiJadwal.DoesNotExist:
        return Response({'detail': 'Tidak ditemukan.'}, status=status.HTTP_404_NOT_FOUND)

    # Zombie detection: proses tandai berjalan tapi sudah mati
    if jadwal.status_terakhir == 'berjalan' and jadwal.pid:
        if not _is_process_alive(jadwal.pid):
            jadwal.status_terakhir = 'error'
            jadwal.pesan_terakhir  = f'Proses (PID {jadwal.pid}) berhenti tidak normal.'
            jadwal.pid = None
            jadwal.save(update_fields=['status_terakhir', 'pesan_terakhir', 'pid'])

    return Response({
        'id':               jadwal.id,
        'status_terakhir':  jadwal.status_terakhir,
        'pesan_terakhir':   jadwal.pesan_terakhir,
        'pid':              jadwal.pid,
        'last_run':         jadwal.last_run.isoformat() if jadwal.last_run else None,
    })


@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def sync_jalankan(request, pk):
    """Jalankan proses sync untuk jadwal ini sebagai subprocess."""
    try:
        jadwal = SinkronisasiJadwal.objects.get(pk=pk)
    except SinkronisasiJadwal.DoesNotExist:
        return Response({'detail': 'Tidak ditemukan.'}, status=status.HTTP_404_NOT_FOUND)

    # Cegah double-run
    if jadwal.status_terakhir == 'berjalan' and jadwal.pid:
        if _is_process_alive(jadwal.pid):
            return Response(
                {'detail': f'Proses sync masih berjalan (PID {jadwal.pid}).'},
                status=status.HTTP_409_CONFLICT,
            )

    script_path = (
        Path(__file__).resolve().parent.parent.parent
        / 'utils' / 'pddikti' / 'sync_runner.py'
    )
    if not script_path.exists():
        return Response({'detail': f'Script tidak ditemukan: {script_path}'}, status=500)

    cmd = [sys.executable, str(script_path), '--jadwal_id', str(pk)]
    if request.data.get('dry_run'):
        cmd.append('--dry-run')

    log_path = script_path.parent / f'sync_run_{pk}.log'
    proc_env = os.environ.copy()
    proc_env.setdefault('TMPDIR', '/tmp')

    proc = subprocess.Popen(
        cmd,
        stdout=open(log_path, 'w'),
        stderr=subprocess.STDOUT,
        cwd=str(script_path.parent),
        env=proc_env,
        start_new_session=True,
    )

    jadwal.status_terakhir = 'berjalan'
    jadwal.pid             = proc.pid
    jadwal.pesan_terakhir  = 'Proses dimulai...'
    jadwal.last_run        = timezone.now()
    jadwal.save(update_fields=['status_terakhir', 'pid', 'pesan_terakhir', 'last_run'])

    return Response({'detail': 'Proses sync dimulai.', 'pid': proc.pid})


@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def sync_hentikan(request, pk):
    """Hentikan proses sync yang sedang berjalan (SIGTERM)."""
    try:
        jadwal = SinkronisasiJadwal.objects.get(pk=pk)
    except SinkronisasiJadwal.DoesNotExist:
        return Response({'detail': 'Tidak ditemukan.'}, status=status.HTTP_404_NOT_FOUND)

    if jadwal.status_terakhir != 'berjalan' or not jadwal.pid:
        return Response({'detail': 'Tidak ada proses yang sedang berjalan.'}, status=400)

    try:
        os.kill(jadwal.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass  # Sudah mati

    jadwal.status_terakhir = 'error'
    jadwal.pesan_terakhir  = f'Proses dihentikan manual (PID {jadwal.pid}).'
    jadwal.pid             = None
    jadwal.save(update_fields=['status_terakhir', 'pesan_terakhir', 'pid'])

    return Response({'detail': 'Proses dihentikan.'})
