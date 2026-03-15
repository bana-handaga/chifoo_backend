"""Admin configuration for Users app"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'get_full_name', 'role', 'perguruan_tinggi', 'is_active', 'is_verified']
    list_filter = ['role', 'is_active', 'is_verified', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    fieldsets = UserAdmin.fieldsets + (
        ('Informasi PTMA', {
            'fields': ('role', 'perguruan_tinggi', 'nomor_telepon', 'foto', 'is_verified')
        }),
    )
