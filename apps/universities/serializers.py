"""Serializers for Universities app"""

from rest_framework import serializers
from django.db.models import Sum
from .models import Wilayah, PerguruanTinggi, ProgramStudi, DataMahasiswa, DataDosen


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
            per_periode[key].append({
                'prodi_id': d.program_studi_id,
                'prodi_nama': d.program_studi.nama if d.program_studi else '—',
                'prodi_jenjang': d.program_studi.get_jenjang_display() if d.program_studi else '',
                **{f: getattr(d, f) for f in AGG_FIELDS},
            })
        # Gabungkan
        for row in totals:
            row['per_prodi'] = per_periode.get((row['tahun_akademik'], row['semester']), [])
        return totals

    def get_periode_aktif_label(self, obj):
        periode = _get_periode_aktif()
        return periode.nama if periode else None
