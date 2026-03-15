"""PTMA Monitoring - URL Configuration"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.users.urls')),
    path('api/', include('apps.universities.urls')),
    path('api/', include('apps.monitoring.urls')),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 
