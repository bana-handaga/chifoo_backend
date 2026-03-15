"""Users app - Custom User Model dan Authentication"""

from django.contrib.auth.models import AbstractUser
from django.db import models
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
