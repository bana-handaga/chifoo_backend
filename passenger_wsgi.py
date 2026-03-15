"""
passenger_wsgi.py
=================
Entry point untuk cPanel Python App (Phusion Passenger).
File ini WAJIB ada di root folder aplikasi Django.

PENTING: Sesuaikan nilai INTERP dengan path virtualenv di server Anda.
Lihat path yang tepat di cPanel > Setup Python App > tombol "Enter virtualenv"
"""

import os
import sys

# Path ke Python interpreter di virtualenv cPanel
# Format: /home/CPANEL_USERNAME/virtualenv/NAMA_APP/VERSI_PYTHON/bin/python3
# Ganti 'usercpanel' dengan username cPanel Anda
INTERP = os.path.join(
    os.environ.get('HOME', '/home/usercpanel'),
    'virtualenv', 'ptma-backend', '3.11', 'bin', 'python3'
)

if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# Tambahkan root project ke Python path
sys.path.insert(0, os.path.dirname(__file__))

# Gunakan settings production
os.environ['DJANGO_SETTINGS_MODULE'] = 'ptma.settings.production'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
