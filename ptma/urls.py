"""PTMA Monitoring - URL Configuration"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.views.static import serve

urlpatterns = [
    path('favicon.ico', lambda req: HttpResponse(status=204)),
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.users.urls')),
    path('api/', include('apps.universities.urls')),
    path('api/', include('apps.monitoring.urls')),
    # Serve media files (aktif baik DEBUG=True maupun False)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
