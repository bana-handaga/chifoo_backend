"""PTMA Monitoring - URL Configuration"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse, FileResponse, Http404
from django.views.static import serve
from pathlib import Path


def serve_frontend(request, path=''):
    """Serve Angular SPA: aset statis dari FRONTEND_DIR, fallback ke index.html."""
    frontend_dir = Path(settings.FRONTEND_DIR)
    # Coba serve file yang diminta (JS, CSS, assets, dll)
    if path:
        file_path = frontend_dir / path
        if file_path.is_file():
            return FileResponse(open(file_path, 'rb'))
    # Fallback ke index.html untuk semua route Angular
    index = frontend_dir / 'index.html'
    if not index.exists():
        raise Http404('Frontend belum di-build.')
    return FileResponse(open(index, 'rb'))


urlpatterns = [
    path('favicon.ico', lambda req: HttpResponse(status=204)),
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.users.urls')),
    path('api/', include('apps.universities.urls')),
    path('api/', include('apps.monitoring.urls')),
    # Serve media & static files Django
    re_path(r'^media/(?P<path>.*)$',  serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
    # Serve frontend Angular (catch-all — harus paling bawah)
    re_path(r'^(?P<path>.*)$', serve_frontend),
]
