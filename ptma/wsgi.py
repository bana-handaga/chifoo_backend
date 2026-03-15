"""WSGI config for PTMA project."""
import os
from django.core.wsgi import get_wsgi_application

# Default ke production; passenger_wsgi.py akan override ini
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ptma.settings.production')
application = get_wsgi_application()
