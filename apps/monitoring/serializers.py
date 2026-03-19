"""Serializers for Monitoring app"""

from rest_framework import serializers
from .models import (
    KategoriIndikator, Indikator, PeriodePelaporan,
    LaporanPT, IsiLaporan, Notifikasi,
    SnapshotLaporan, SnapshotPerPT,
)


class IndikatorSerializer(serializers.ModelSerializer):
    tipe_display = serializers.SerializerMethodField()

    class Meta:
        model = Indikator
        fields = '__all__'

    def get_tipe_display(self, obj):
        return obj.get_tipe_data_display()


class KategoriIndikatorSerializer(serializers.ModelSerializer):
    indikator = IndikatorSerializer(many=True, read_only=True)
    total_indikator = serializers.SerializerMethodField()

    class Meta:
        model = KategoriIndikator
        fields = ['id', 'nama', 'deskripsi', 'urutan', 'icon', 'indikator', 'total_indikator']

    def get_total_indikator(self, obj):
        return obj.indikator.filter(is_active=True).count()


class PeriodePelaporanSerializer(serializers.ModelSerializer):
    status_display = serializers.SerializerMethodField()
    total_laporan = serializers.SerializerMethodField()
    laporan_submitted = serializers.SerializerMethodField()

    class Meta:
        model = PeriodePelaporan
        fields = '__all__'

    def get_status_display(self, obj):
        return obj.get_status_display()

    def get_total_laporan(self, obj):
        return obj.laporan.count()

    def get_laporan_submitted(self, obj):
        return obj.laporan.filter(status__in=['submitted', 'approved']).count()


class IsiLaporanSerializer(serializers.ModelSerializer):
    indikator_nama = serializers.CharField(source='indikator.nama', read_only=True)
    indikator_kode = serializers.CharField(source='indikator.kode', read_only=True)
    indikator_tipe = serializers.CharField(source='indikator.tipe_data', read_only=True)
    indikator_satuan = serializers.CharField(source='indikator.satuan', read_only=True)

    class Meta:
        model = IsiLaporan
        fields = '__all__'


class LaporanPTListSerializer(serializers.ModelSerializer):
    pt_nama = serializers.CharField(source='perguruan_tinggi.nama', read_only=True)
    pt_singkatan = serializers.CharField(source='perguruan_tinggi.singkatan', read_only=True)
    pt_organisasi = serializers.CharField(source='perguruan_tinggi.organisasi_induk', read_only=True)
    periode_nama = serializers.CharField(source='periode.nama', read_only=True)
    status_display = serializers.SerializerMethodField()

    class Meta:
        model = LaporanPT
        fields = [
            'id', 'pt_nama', 'pt_singkatan', 'pt_organisasi', 'periode_nama',
            'status', 'status_display', 'persentase_pengisian', 'skor_total',
            'submitted_at', 'created_at', 'updated_at'
        ]

    def get_status_display(self, obj):
        return obj.get_status_display()


class LaporanPTDetailSerializer(serializers.ModelSerializer):
    isi = IsiLaporanSerializer(many=True, read_only=True)
    status_display = serializers.SerializerMethodField()
    pt_detail = serializers.SerializerMethodField()

    class Meta:
        model = LaporanPT
        fields = '__all__'

    def get_status_display(self, obj):
        return obj.get_status_display()

    def get_pt_detail(self, obj):
        return {
            'id': obj.perguruan_tinggi.id,
            'nama': obj.perguruan_tinggi.nama,
            'singkatan': obj.perguruan_tinggi.singkatan,
            'organisasi_induk': obj.perguruan_tinggi.organisasi_induk,
            'kota': obj.perguruan_tinggi.kota,
            'akreditasi': obj.perguruan_tinggi.akreditasi_institusi,
        }


class NotifikasiSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notifikasi
        fields = '__all__'


class SnapshotPerPTSerializer(serializers.ModelSerializer):
    pt_id       = serializers.IntegerField(source='perguruan_tinggi_id')
    pt_kode     = serializers.CharField(source='perguruan_tinggi.kode_pt')
    pt_nama     = serializers.CharField(source='perguruan_tinggi.nama')
    pt_singkatan = serializers.CharField(source='perguruan_tinggi.singkatan')

    class Meta:
        model  = SnapshotPerPT
        fields = [
            'pt_id', 'pt_kode', 'pt_nama', 'pt_singkatan',
            'total_prodi', 'prodi_per_jenjang',
            'total_dosen', 'dosen_pria', 'dosen_wanita',
            'dosen_per_jabatan', 'dosen_per_pendidikan',
            'dosen_per_status', 'dosen_per_ikatan',
            'mhs_tren',
        ]


class SnapshotLaporanSerializer(serializers.ModelSerializer):
    per_pt = SnapshotPerPTSerializer(many=True, read_only=True)

    class Meta:
        model  = SnapshotLaporan
        fields = ['id', 'dibuat_pada', 'keterangan', 'total_pt', 'per_pt']


class SnapshotLaporanListSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SnapshotLaporan
        fields = ['id', 'dibuat_pada', 'keterangan', 'total_pt']
