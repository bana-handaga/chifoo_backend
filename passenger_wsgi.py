"""
passenger_wsgi.py
=================
Entry point untuk cPanel Python App (Phusion Passenger / LiteSpeed).
File ini WAJIB ada di root folder aplikasi Django.

Path virtualenv disesuaikan dengan konfigurasi di server:
  PassengerPython "/home/birotium/virtualenv/ptma-backend/3.12/bin/python"
"""

import os
import sys

# Path ke Python interpreter di virtualenv cPanel
# Harus sama persis dengan nilai PassengerPython di .htaccess
INTERP = os.path.join(
    os.environ.get('HOME', '/home/birotium'),
    'virtualenv', 'ptma-backend', '3.12', 'bin', 'python'
)

if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# Tambahkan root project ke Python path
sys.path.insert(0, os.path.dirname(__file__))

# Gunakan settings production
os.environ['DJANGO_SETTINGS_MODULE'] = 'ptma.settings.production'

# PyMySQL sebagai pengganti mysqlclient (pure Python, tidak butuh library C)
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass  # mysqlclient tersedia, tidak perlu PyMySQL

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
