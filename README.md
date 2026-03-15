# PTMA Monitor — Backend (Django REST Framework)

## Persyaratan
- Python 3.11+
- MySQL / MariaDB

## Instalasi Production (cPanel Hosting)

1. Upload folder ini ke server hosting
2. Buat file `.env` dari `.env.example` dan isi dengan data hosting
3. Aktifkan virtualenv dari cPanel > Setup Python App
4. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
5. Jalankan migrasi:
   ```
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py createsuperuser
   ```
6. Restart Python App dari cPanel

## Instalasi Development Lokal

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Struktur URL API

| Method | URL | Keterangan |
|--------|-----|-----------|
| POST | /api/auth/login/ | Login |
| POST | /api/auth/logout/ | Logout |
| GET | /api/auth/profile/ | Profil user |
| GET/POST | /api/perguruan-tinggi/ | Daftar PT |
| GET | /api/perguruan-tinggi/{id}/ | Detail PT |
| GET | /api/perguruan-tinggi/statistik/ | Statistik nasional |
| GET | /api/wilayah/ | Daftar wilayah |
| GET | /api/laporan-pt/ | Daftar laporan |
| POST | /api/laporan-pt/{id}/submit/ | Submit laporan |
| POST | /api/laporan-pt/{id}/approve/ | Approve laporan |
| POST | /api/laporan-pt/{id}/reject/ | Reject laporan |
| GET | /api/admin/ | Django Admin |
