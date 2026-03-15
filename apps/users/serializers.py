"""Serializers for Users app"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    pt_nama = serializers.CharField(source='perguruan_tinggi.nama', read_only=True)
    pt_singkatan = serializers.CharField(source='perguruan_tinggi.singkatan', read_only=True)
    role_display = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'role_display', 'perguruan_tinggi', 'pt_nama', 'pt_singkatan',
            'nomor_telepon', 'foto', 'is_verified', 'last_active', 'date_joined'
        ]
        read_only_fields = ['last_active', 'date_joined']

    def get_role_display(self, obj):
        return obj.get_role_display()
