"""Serializers for Universities app"""

from rest_framework import serializers
from django.db.models import Sum
from .models import Wilayah, PerguruanTinggi, ProgramStudi, DataMahasiswa, DataDosen, SintaJurnal, SintaAfiliasi, SintaTrendTahunan, SintaWcuTahunan, SintaCluster, SintaDepartemen, SintaAuthor, SintaAuthorTrend


class WilayahSerializer(serializers.ModelSerializer):
    total_pt = serializers.SerializerMethodField()

    class Meta:
        model = Wilayah
        fields = ['id', 'kode', 'nama', 'provinsi', 'total_pt']

    def get_total_pt(self, obj):
        return obj.perguruan_tinggi.filter(is_active=True).count()


def _get_periode_aktif():
    """Ambil periode pelaporan aktif (dipanggil berulang, tabel kecil)."""
    from apps.monitoring.models import PeriodePelaporan
    return PeriodePelaporan.objects.filter(status='aktif').order_by('-tahun', 'semester').first()


class ProgramStudiSerializer(serializers.ModelSerializer):
    mahasiswa_aktif_periode = serializers.SerializerMethodField()
    dosen_tetap_periode = serializers.SerializerMethodField()

    class Meta:
        model = ProgramStudi
        fields = [
            'id', 'kode_prodi', 'nama', 'jenjang', 'jenjang_display',
            'akreditasi', 'akreditasi_display',
            'no_sk_akreditasi', 'tanggal_kedaluarsa_akreditasi',
            'is_active', 'mahasiswa_aktif_periode', 'dosen_tetap_periode',
        ]
        extra_kwargs = {
            'jenjang_display': {'source': 'get_jenjang_display', 'read_only': True},
            'akreditasi_display': {'source': 'get_akreditasi_display', 'read_only': True},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['jenjang_display'] = instance.get_jenjang_display()
        data['akreditasi_display'] = instance.get_akreditasi_display()
        pt = instance.perguruan_tinggi
        data['perguruan_tinggi_nama'] = (pt.singkatan or pt.nama) if pt else ''
        return data

    def _get_ta(self):
        periode = _get_periode_aktif()
        if not periode:
            return None, None
        ta = (f"{periode.tahun - 1}/{periode.tahun}" if periode.semester == 'genap'
              else f"{periode.tahun}/{periode.tahun + 1}")
        return ta, periode.semester

    def get_mahasiswa_aktif_periode(self, obj):
        ta, sem = self._get_ta()
        if not ta:
            return 0
        dm = obj.data_mahasiswa.filter(tahun_akademik=ta, semester=sem).first()
        return dm.mahasiswa_aktif if dm else 0

    def get_dosen_tetap_periode(self, obj):
        ta, sem = self._get_ta()
        if not ta:
            return 0
        dd = obj.data_dosen.filter(tahun_akademik=ta, semester=sem).first()
        return dd.dosen_tetap if dd else 0


class DataMahasiswaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataMahasiswa
        fields = '__all__'


class DataDosenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataDosen
        fields = '__all__'


class PerguruanTinggiListSerializer(serializers.ModelSerializer):
    wilayah_nama = serializers.CharField(source='wilayah.nama', read_only=True)
    total_prodi = serializers.SerializerMethodField()
    total_mahasiswa = serializers.SerializerMethodField()
    total_dosen = serializers.SerializerMethodField()

    class Meta:
        model = PerguruanTinggi
        fields = [
            'id', 'kode_pt', 'nama', 'singkatan', 'jenis',
            'organisasi_induk', 'kota', 'provinsi', 'wilayah_nama',
            'akreditasi_institusi', 'nomor_sk_akreditasi',
            'tanggal_kadaluarsa_akreditasi', 'is_active',
            'total_prodi', 'total_mahasiswa', 'total_dosen', 'logo', 'website'
        ]

    def get_total_prodi(self, obj):
        return obj.program_studi.filter(is_active=True).count()

    def _get_tahun_semester(self, periode_aktif):
        if periode_aktif.semester == 'genap':
            return f"{periode_aktif.tahun - 1}/{periode_aktif.tahun}"
        return f"{periode_aktif.tahun}/{periode_aktif.tahun + 1}"

    def get_total_mahasiswa(self, obj):
        periode_aktif = _get_periode_aktif()
        if not periode_aktif:
            return 0
        tahun_akademik = self._get_tahun_semester(periode_aktif)
        total = (
            obj.data_mahasiswa
            .filter(
                program_studi__is_active=True,
                tahun_akademik=tahun_akademik,
                semester=periode_aktif.semester,
            )
            .aggregate(total=Sum('mahasiswa_aktif'))['total']
        )
        return total or 0

    def get_total_dosen(self, obj):
        periode_aktif = _get_periode_aktif()
        if not periode_aktif:
            return 0
        tahun_akademik = self._get_tahun_semester(periode_aktif)
        total = (
            obj.data_dosen
            .filter(
                tahun_akademik=tahun_akademik,
                semester=periode_aktif.semester,
            )
            .aggregate(total=Sum('dosen_tetap'))['total']
        )
        return total or 0


class PerguruanTinggiDetailSerializer(serializers.ModelSerializer):
    wilayah = WilayahSerializer(read_only=True)
    wilayah_id = serializers.PrimaryKeyRelatedField(
        queryset=Wilayah.objects.all(), source='wilayah', write_only=True
    )
    program_studi = ProgramStudiSerializer(many=True, read_only=True)
    data_mahasiswa = serializers.SerializerMethodField()
    data_dosen = serializers.SerializerMethodField()
    jenis_display = serializers.SerializerMethodField()
    organisasi_display = serializers.SerializerMethodField()
    akreditasi_display = serializers.SerializerMethodField()
    periode_aktif_label = serializers.SerializerMethodField()

    class Meta:
        model = PerguruanTinggi
        fields = '__all__'

    def get_jenis_display(self, obj):
        return obj.get_jenis_display()

    def get_organisasi_display(self, obj):
        return obj.get_organisasi_induk_display()

    def get_akreditasi_display(self, obj):
        return obj.get_akreditasi_institusi_display()

    def get_data_mahasiswa(self, obj):
        """Agregat per tahun_akademik+semester, dengan rincian per_prodi."""
        AGG_FIELDS = [
            'mahasiswa_baru', 'mahasiswa_aktif', 'mahasiswa_lulus',
            'mahasiswa_dropout', 'mahasiswa_pria', 'mahasiswa_wanita',
        ]
        totals = list(
            obj.data_mahasiswa
            .filter(program_studi__is_active=True)
            .values('tahun_akademik', 'semester')
            .annotate(**{f: Sum(f) for f in AGG_FIELDS})
            .order_by('-tahun_akademik', 'semester')
        )
        detail_qs = (
            obj.data_mahasiswa
            .filter(program_studi__is_active=True)
            .select_related('program_studi')
            .order_by('-tahun_akademik', 'semester', 'program_studi__nama')
        )
        from collections import defaultdict
        per_periode = defaultdict(list)
        for d in detail_qs:
            key = (d.tahun_akademik, d.semester)
            per_periode[key].append({
                'prodi_id': d.program_studi_id,
                'prodi_nama': d.program_studi.nama if d.program_studi else '—',
                'prodi_jenjang': d.program_studi.get_jenjang_display() if d.program_studi else '',
                **{f: getattr(d, f) for f in AGG_FIELDS},
            })
        for row in totals:
            row['per_prodi'] = per_periode.get((row['tahun_akademik'], row['semester']), [])
        return totals

    def get_data_dosen(self, obj):
        """Agregat per tahun_akademik+semester, dengan rincian per_prodi."""
        AGG_FIELDS = [
            'dosen_tetap', 'dosen_tidak_tetap', 'dosen_s3', 'dosen_s2', 'dosen_s1',
            'dosen_guru_besar', 'dosen_lektor_kepala', 'dosen_lektor',
            'dosen_asisten_ahli', 'dosen_bersertifikat',
        ]
        # Agregat total per periode
        totals = list(
            obj.data_dosen
            .values('tahun_akademik', 'semester')
            .annotate(**{f: Sum(f) for f in AGG_FIELDS})
            .order_by('-tahun_akademik', 'semester')
        )
        # Rincian per prodi (semua record mentah)
        detail_qs = (
            obj.data_dosen
            .select_related('program_studi')
            .order_by('-tahun_akademik', 'semester', 'program_studi__nama')
        )
        # Kelompokkan per (tahun_akademik, semester)
        from collections import defaultdict
        per_periode = defaultdict(list)
        for d in detail_qs:
            key = (d.tahun_akademik, d.semester)
            ps = d.program_studi
            per_periode[key].append({
                'prodi_id':      d.program_studi_id,
                'prodi_nama':    ps.nama if ps else '—',
                'prodi_kode':    ps.kode_prodi if ps else '',
                'prodi_jenjang': ps.get_jenjang_display() if ps else '',
                'pt_kode':       obj.kode_pt,
                'pt_nama':       obj.singkatan or obj.nama,
                **{f: getattr(d, f) for f in AGG_FIELDS},
            })
        # Gabungkan
        for row in totals:
            row['per_prodi'] = per_periode.get((row['tahun_akademik'], row['semester']), [])
        return totals

    def get_periode_aktif_label(self, obj):
        periode = _get_periode_aktif()
        return periode.nama if periode else None


class SintaJurnalSerializer(serializers.ModelSerializer):
    perguruan_tinggi_nama = serializers.SerializerMethodField()
    perguruan_tinggi_singkatan = serializers.SerializerMethodField()
    perguruan_tinggi_kode = serializers.SerializerMethodField()

    class Meta:
        model = SintaJurnal
        fields = [
            'id', 'sinta_id', 'nama', 'p_issn', 'e_issn',
            'akreditasi', 'subject_area', 'wcu_area', 'afiliasi_teks',
            'impact', 'h5_index', 'sitasi_5yr', 'sitasi_total',
            'is_scopus', 'is_garuda',
            'url_website', 'url_scholar', 'url_editor', 'url_garuda',
            'logo_base64', 'scraped_at',
            'perguruan_tinggi', 'perguruan_tinggi_nama',
            'perguruan_tinggi_singkatan', 'perguruan_tinggi_kode',
        ]

    def get_perguruan_tinggi_nama(self, obj):
        return obj.perguruan_tinggi.nama if obj.perguruan_tinggi else ''

    def get_perguruan_tinggi_singkatan(self, obj):
        return obj.perguruan_tinggi.singkatan if obj.perguruan_tinggi else ''

    def get_perguruan_tinggi_kode(self, obj):
        return obj.perguruan_tinggi.kode_pt if obj.perguruan_tinggi else ''


class SintaJurnalListSerializer(SintaJurnalSerializer):
    """Sama dengan SintaJurnalSerializer — logo disertakan untuk ditampilkan."""
    pass


# ─── SINTA Afiliasi ──────────────────────────────────────────────────────────

class SintaClusterMinSerializer(serializers.ModelSerializer):
    class Meta:
        model = SintaCluster
        fields = [
            'cluster_name', 'total_score', 'periode',
            'score_publication', 'score_hki', 'score_kelembagaan',
            'score_research', 'score_community_service', 'score_sdm',
        ]


class SintaTrendTahunanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SintaTrendTahunan
        fields = ['jenis', 'tahun', 'jumlah', 'research_article', 'research_conference', 'research_others']


class SintaWcuTahunanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SintaWcuTahunan
        fields = [
            'tahun', 'overall',
            'natural_sciences', 'engineering_technology',
            'life_sciences_medicine', 'social_sciences_management', 'arts_humanities',
        ]


class SintaAfiliasiListSerializer(serializers.ModelSerializer):
    """Serializer ringkas untuk daftar/ranking — tidak menyertakan logo & trend."""
    pt_nama       = serializers.CharField(source='perguruan_tinggi.nama', read_only=True)
    pt_singkatan  = serializers.CharField(source='perguruan_tinggi.singkatan', read_only=True)
    pt_kota       = serializers.CharField(source='perguruan_tinggi.kota', read_only=True)
    pt_provinsi   = serializers.CharField(source='perguruan_tinggi.provinsi', read_only=True)
    pt_kode       = serializers.CharField(source='perguruan_tinggi.kode_pt', read_only=True)
    pt_akreditasi = serializers.CharField(source='perguruan_tinggi.akreditasi_institusi', read_only=True)
    pt_logo       = serializers.SerializerMethodField()
    cluster       = SintaClusterMinSerializer(read_only=True)

    def get_pt_logo(self, obj):
        logo = obj.perguruan_tinggi.logo
        return logo.url if logo else ''

    class Meta:
        model = SintaAfiliasi
        fields = [
            'id', 'sinta_id', 'sinta_kode', 'nama_sinta', 'singkatan_sinta',
            'lokasi_sinta', 'sinta_profile_url',
            'jumlah_authors', 'jumlah_departments', 'jumlah_journals',
            'sinta_score_overall', 'sinta_score_3year',
            'sinta_score_productivity', 'sinta_score_productivity_3year',
            'scopus_dokumen', 'scopus_sitasi', 'scopus_dokumen_disitasi', 'scopus_sitasi_per_peneliti',
            'scopus_q1', 'scopus_q2', 'scopus_q3', 'scopus_q4', 'scopus_noq',
            'gscholar_dokumen', 'gscholar_sitasi', 'gscholar_dokumen_disitasi', 'gscholar_sitasi_per_peneliti',
            'wos_dokumen', 'wos_sitasi', 'wos_dokumen_disitasi', 'wos_sitasi_per_peneliti',
            'garuda_dokumen', 'garuda_sitasi', 'garuda_dokumen_disitasi', 'garuda_sitasi_per_peneliti',
            'sinta_last_update', 'scraped_at',
            'pt_nama', 'pt_singkatan', 'pt_kota', 'pt_provinsi', 'pt_kode', 'pt_akreditasi', 'pt_logo',
            'cluster',
        ]


class SintaAfiliasiDetailSerializer(SintaAfiliasiListSerializer):
    """Detail lengkap — termasuk logo, trend tahunan, dan data WCU."""
    trend_tahunan = SintaTrendTahunanSerializer(many=True, read_only=True)
    wcu_tahunan   = SintaWcuTahunanSerializer(many=True, read_only=True)

    class Meta(SintaAfiliasiListSerializer.Meta):
        fields = SintaAfiliasiListSerializer.Meta.fields + [
            'logo_base64', 'trend_tahunan', 'wcu_tahunan',
        ]


# ---------------------------------------------------------------------------
# SintaDepartemen
# ---------------------------------------------------------------------------

class SintaDepartemenSerializer(serializers.ModelSerializer):
    """Serializer untuk departemen (program studi) per PT di SINTA."""

    # Info PT induk
    afiliasi_id    = serializers.IntegerField(source='afiliasi.id', read_only=True)
    pt_singkatan   = serializers.CharField(source='afiliasi.perguruan_tinggi.singkatan', read_only=True)
    pt_nama        = serializers.CharField(source='afiliasi.perguruan_tinggi.nama', read_only=True)
    pt_kode        = serializers.CharField(source='afiliasi.sinta_kode', read_only=True)
    sinta_id_pt    = serializers.CharField(source='afiliasi.sinta_id', read_only=True)

    class Meta:
        model  = SintaDepartemen
        fields = [
            'id',
            'afiliasi_id', 'sinta_id_pt', 'pt_kode', 'pt_singkatan', 'pt_nama',
            'nama', 'jenjang', 'kode_dept', 'url_profil',
            'sinta_score_overall', 'sinta_score_3year',
            'jumlah_authors',
        ]


# ---------------------------------------------------------------------------
# SintaAuthor
# ---------------------------------------------------------------------------

class SintaAuthorTrendSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SintaAuthorTrend
        fields = ['jenis', 'tahun', 'jumlah']


class SintaAuthorListSerializer(serializers.ModelSerializer):
    """Serializer ringkas untuk daftar/ranking author."""
    pt_singkatan  = serializers.CharField(source='afiliasi.perguruan_tinggi.singkatan', read_only=True, default='')
    pt_kode       = serializers.CharField(source='afiliasi.sinta_kode', read_only=True, default='')
    dept_nama     = serializers.CharField(source='departemen.nama', read_only=True, default='')
    dept_jenjang  = serializers.CharField(source='departemen.jenjang', read_only=True, default='')

    class Meta:
        model  = SintaAuthor
        fields = [
            'id', 'sinta_id', 'nama', 'url_profil', 'foto_url',
            'pt_kode', 'pt_singkatan', 'dept_nama', 'dept_jenjang',
            'sinta_score_overall', 'sinta_score_3year',
            'scopus_artikel', 'scopus_sitasi', 'scopus_h_index',
            'gscholar_h_index', 'bidang_keilmuan',
        ]


class SintaAuthorDetailSerializer(SintaAuthorListSerializer):
    """Detail lengkap termasuk semua statistik dan tren."""
    trend = SintaAuthorTrendSerializer(many=True, read_only=True)

    class Meta(SintaAuthorListSerializer.Meta):
        fields = SintaAuthorListSerializer.Meta.fields + [
            'affil_score', 'affil_score_3year',
            'scopus_cited_doc', 'scopus_i10_index', 'scopus_g_index',
            'gscholar_artikel', 'gscholar_sitasi', 'gscholar_cited_doc',
            'gscholar_i10_index', 'gscholar_g_index',
            'wos_artikel', 'wos_sitasi', 'wos_cited_doc',
            'wos_h_index', 'wos_i10_index', 'wos_g_index',
            'scopus_q1', 'scopus_q2', 'scopus_q3', 'scopus_q4', 'scopus_noq',
            'research_conference', 'research_articles', 'research_others',
            'scraped_at', 'trend',
        ]
