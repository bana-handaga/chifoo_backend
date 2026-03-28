"""Users app - Custom User Model dan Authentication"""

import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from apps.universities.models import PerguruanTinggi


class User(AbstractUser):
    """Custom User untuk PTMA Monitoring"""

    class Role(models.TextChoices):
        SUPERADMIN = 'superadmin', 'Super Admin (PP Muhammadiyah)'
        ADMIN_WILAYAH = 'admin_wilayah', 'Admin Wilayah'
        OPERATOR_PT = 'operator_pt', 'Operator PT'
        VIEWER = 'viewer', 'Viewer'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    perguruan_tinggi = models.ForeignKey(
        PerguruanTinggi, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='users'
    )
    nomor_telepon = models.CharField(max_length=20, blank=True)
    foto = models.ImageField(upload_to='user_photos/', null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    last_active = models.DateTimeField(null=True, blank=True)
    mfa_enabled = models.BooleanField(default=False, verbose_name='MFA Email aktif')

    class Meta:
        verbose_name = 'Pengguna'
        verbose_name_plural = 'Pengguna'

    def __str__(self):
        return f"{self.get_full_name()} ({self.role})"

    @property
    def is_operator_pt(self):
        return self.role == self.Role.OPERATOR_PT

    @property
    def is_admin(self):
        return self.role in [self.Role.SUPERADMIN, self.Role.ADMIN_WILAYAH]


class MfaOtp(models.Model):
    """OTP sementara untuk verifikasi login MFA via Email"""
    user = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='mfa_otps'
    )
    session_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'OTP MFA'
        verbose_name_plural = 'OTP MFA'

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at
