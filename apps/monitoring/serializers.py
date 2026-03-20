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
    pt_id           = serializers.IntegerField(source='perguruan_tinggi_id')
    pt_kode         = serializers.CharField(source='perguruan_tinggi.kode_pt')
    pt_nama         = serializers.CharField(source='perguruan_tinggi.nama')
    pt_singkatan    = serializers.CharField(source='perguruan_tinggi.singkatan')
    pt_jenis        = serializers.CharField(source='perguruan_tinggi.jenis')
    pt_organisasi   = serializers.CharField(source='perguruan_tinggi.organisasi_induk')
    pt_akreditasi   = serializers.CharField(source='perguruan_tinggi.akreditasi_institusi')
    pt_aktif        = serializers.BooleanField(source='perguruan_tinggi.is_active')

    class Meta:
        model  = SnapshotPerPT
        fields = [
            'pt_id', 'pt_kode', 'pt_nama', 'pt_singkatan',
            'pt_jenis', 'pt_organisasi', 'pt_akreditasi', 'pt_aktif',
            # prodi
            'total_prodi',
            'prodi_aktif', 'prodi_non_aktif',
            'prodi_s1', 'prodi_s2', 'prodi_s3',
            'prodi_d3', 'prodi_d4', 'prodi_profesi', 'prodi_sp1',
            'prodi_jenjang_lainnya',
            # dosen ringkasan
            'total_dosen', 'dosen_with_detail', 'dosen_no_detail',
            'dosen_pria', 'dosen_wanita', 'dosen_gender_no_info',
            # jabatan
            'dosen_profesor', 'dosen_lektor_kepala', 'dosen_lektor',
            'dosen_asisten_ahli', 'dosen_jabatan_lainnya',
            # pendidikan
            'dosen_pend_s3', 'dosen_pend_s2', 'dosen_pend_s1',
            'dosen_pend_profesi', 'dosen_pend_lainnya',
            # status
            'dosen_aktif', 'dosen_tugas_belajar', 'dosen_ijin_belajar',
            'dosen_cuti', 'dosen_status_lainnya',
            # ikatan kerja
            'dosen_tetap', 'dosen_tidak_tetap', 'dosen_dtpk', 'dosen_ikatan_lainnya',
            # tren mahasiswa
            'mhs_label_1', 'mhs_sem_1',
            'mhs_label_2', 'mhs_sem_2',
            'mhs_label_3', 'mhs_sem_3',
            'mhs_label_4', 'mhs_sem_4',
            'mhs_label_5', 'mhs_sem_5',
            'mhs_label_6', 'mhs_sem_6',
            'mhs_label_7', 'mhs_sem_7',
        ]


class SnapshotLaporanSerializer(serializers.ModelSerializer):
    per_pt = SnapshotPerPTSerializer(many=True, read_only=True)

    class Meta:
        model  = SnapshotLaporan
        fields = ['id', 'dibuat_pada', 'keterangan', 'total_pt', 'total_pt_non_aktif', 'per_pt']


class SnapshotLaporanListSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SnapshotLaporan
        fields = ['id', 'dibuat_pada', 'keterangan', 'total_pt', 'total_pt_non_aktif']
