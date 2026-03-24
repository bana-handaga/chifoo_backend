# Logbook Pengembangan — Halaman Pengabdian Masyarakat
**Dibuat:** 2026-03-24
**Fitur:** Halaman informasi Pengabdian Masyarakat di submenu SINTA (`/sinta/pengabdian`)
**Status:** 🟡 Tahap Awal — Backend selesai, Frontend selesai, Validasi data selesai, Import sedang berjalan

---

## Daftar Isi
1. [Latar Belakang](#1-latar-belakang)
2. [Infrastruktur yang Sudah Ada](#2-infrastruktur-yang-sudah-ada)
3. [Status Data Hari Ini (2026-03-24)](#3-status-data-hari-ini-2026-03-24)
4. [Yang Dibangun Hari Ini](#4-yang-dibangun-hari-ini)
5. [Alur Data (Pipeline)](#5-alur-data-pipeline)
6. [Rencana Pengembangan](#6-rencana-pengembangan)
7. [Referensi Teknis](#7-referensi-teknis)

---

## 1. Latar Belakang

Halaman **Pengabdian Masyarakat** adalah bagian dari kelompok menu **II — Output Riset & Pengabdian** di bawah navigasi utama **SINTA** (`/sinta`). Halaman ini menampilkan rekap kegiatan *Community Services* dosen PTMA (Perguruan Tinggi Muhammadiyah–Aisyiyah) yang tercatat di platform SINTA Kemdiktisaintek.

Data pengabdian di SINTA meliputi:
- Judul kegiatan pengabdian
- Ketua dan anggota tim
- Skema pengabdian (KKN, PKM, PKMIPT, dll.)
- Tahun, dana, status, dan sumber pendanaan

Sebelum 2026-03-24, halaman ini hanya menampilkan placeholder **"Segera Hadir"**. Mulai hari ini, halaman penuh telah selesai dibangun.

---

## 2. Infrastruktur yang Sudah Ada

Semua infrastruktur backend (model, scraper, importer) selesai dibangun pada sesi **2026-03-23**.

### 2.1 Model Database

**File:** `apps/universities/models.py`
**Migration:** `0021_sinta_pengabdian` (applied: 2026-03-23 16:01)

#### `SintaPengabdian`
| Field | Tipe | Keterangan |
|-------|------|------------|
| `judul` | CharField(1000) | Judul kegiatan pengabdian |
| `leader_nama` | CharField(200) | Nama ketua |
| `skema` | CharField(300) | Nama skema (teks lengkap) |
| `skema_kode` | CharField(20) | Kode skema (misal: KKN, PKM-IPT) |
| `tahun` | PositiveSmallIntegerField | Tahun pelaksanaan |
| `dana` | CharField(50) | Nominal dana (format teks Rp.) |
| `status` | CharField(50) | Status (Approved, dll.) |
| `sumber` | CharField(50) | Sumber dana (INTERNAL, BIMA, dll.) |
| `scraped_at` | DateTimeField(auto_now) | Waktu scrape terakhir |

Unique constraint: `(judul, tahun, skema_kode)` — mencegah duplikasi.

#### `SintaPengabdianAuthor`
Relasi M2M antara `SintaPengabdian` dan `SintaAuthor`:
| Field | Tipe | Keterangan |
|-------|------|------------|
| `pengabdian` | FK → SintaPengabdian | Kegiatan pengabdian |
| `author` | FK → SintaAuthor | Dosen PTMA |
| `is_leader` | BooleanField | True jika sebagai ketua |

#### `SintaAuthorTrend` (field `jenis='service'`)
Model yang sudah ada sejak sebelumnya. Menyimpan tren tahunan per author:
```
SintaAuthorTrend(author=X, jenis='service', tahun=2023, jumlah=5)
```
→ Artinya author X memiliki 5 kegiatan pengabdian di tahun 2023.

---

### 2.2 Scraper

**File:** `utils/sinta/scrape_sinta_author_services.py`

- **Sumber:** `https://sinta.kemdiktisaintek.go.id/authors/profile/{sinta_id}/?view=services`
- **Auth:** Memerlukan **login** SINTA untuk mengakses pagination (tanpa login hanya 10 item)
- **Login URL:** `POST /logins/do_login` (didahului GET `/logins` untuk session cookie)
- **Output:** `utils/sinta/outs/author_services/{kode_pt}/{sinta_id}_services.json`
- **Multi-page:** Loop dari `page=1` hingga `get_last_page()` (10 item per halaman)

**Struktur JSON output:**
```json
{
  "sinta_id": "5975482",
  "scraped_at": "2026-03-24T...",
  "total_scraped": 16,
  "service_history": { "2017": 2, "2018": 3, "2019": 4, "2020": 7 },
  "services": [
    {
      "judul": "PELATIHAN ANALISIS KELAYAKAN...",
      "leader_nama": "Ahmad Kusuma",
      "skema": "PKM PID ( PKM-PID )",
      "skema_kode": "PKM-PID",
      "tahun": 2024,
      "dana": "Rp. 5.000.000",
      "status": "Approved",
      "sumber": "INTERNAL",
      "personils": [
        { "nama": "Budi Santoso", "sinta_id": "6112233" }
      ]
    }
  ]
}
```

**Field `service_history`** diparse dari chart JavaScript di halaman:
```js
// Di HTML:
xAxis.data: ['2018','2019','2020','2021']
series[0].data: [3,5,7,10]
```

---

### 2.3 Importer

**File:** `utils/sinta/sp_import_sinta_author_services.py`

- Membaca semua file JSON dari `outs/author_services/**/*.json`
- Import ke `SintaPengabdian` (upsert by `judul+tahun+skema_kode`)
- Import ke `SintaPengabdianAuthor` (relasi ke SintaAuthor by `sinta_id`)
- Import `service_history` ke `SintaAuthorTrend(jenis='service')` via `update_or_create`

---

## 3. Status Data Hari Ini (2026-03-24)

### 3.1 Status Scraping

| Keterangan | Jumlah |
|------------|--------|
| Total SintaAuthor di DB | 17,861 |
| File JSON services terscrape | **17,861 (100%)** |
| Scraping selesai sejak | 2026-03-24 (pagi) |

Scraping sudah **100% selesai** — semua 17,861 author sudah punya file JSON.

---

### 3.2 Status Import ke DB (sedang berjalan)

Saat logbook ini ditulis, import sedang berjalan dalam **2 instance paralel**:
```bash
python -u utils/sinta/sp_import_sinta_author_services.py   # instance 1
python -u utils/sinta/sp_import_sinta_author_services.py   # instance 2
```

**Data yang sudah terimport (snapshot 2026-03-24 sore):**

| Keterangan | Jumlah |
|------------|--------|
| `SintaPengabdian` (judul unik) | 9,413 |
| `SintaPengabdianAuthor` (relasi dosen) | 10,692 |
| Author unik terlibat | 837 |
| `SintaAuthorTrend (jenis='service')` | 41,290 record |
| Author dengan data tren service | 11,462 |

Import masih berlangsung — angka akan terus bertambah.

---

### 3.3 Distribusi Data yang Sudah Masuk

**Tren judul pengabdian per tahun (snapshot):**
| Tahun | Judul Unik |
|-------|-----------|
| 2013 | 8 |
| 2014 | 5 |
| 2015 | 5 |
| 2016 | 17 |
| 2017 | 13 |
| 2018 | 44 |
| 2019 | 125 |
| 2020 | 550 |
| 2021 | 874 |
| 2022 | 1,500 |
| 2023 | 1,662 |
| 2024 | 1,613 |
| 2025 | 509 |
| 2026 | 7 |

Tren menunjukkan **lonjakan signifikan mulai 2020** — selaras dengan kebijakan Kemdikbud yang mendorong pengabdian masyarakat dosen.

**Top Skema (snapshot):**
| Skema | Kode | Jumlah |
|-------|------|--------|
| HIBAH KKN | KKN | 2,755 |
| PKM | (beragam) | ~2,000+ |
| PENGABDIAN KEPADA MASYARAKAT | PKMIPT | 819 |

**Sumber Dana:**
| Sumber | Jumlah |
|--------|--------|
| INTERNAL | 6,706 (97.6%) |
| BIMA | 129 (1.9%) |
| SIMLITABMAS | 37 (0.5%) |

> **Catatan penting:** Dominasi INTERNAL menunjukkan bahwa mayoritas pengabdian PTMA dibiayai oleh perguruan tinggi sendiri, bukan dari hibah pemerintah. Ini bisa jadi insight menarik untuk ditampilkan di halaman.

---

## 4. Yang Dibangun Hari Ini

### 4.1 Backend — `SintaPengabdianViewSet`

**File:** `apps/universities/views.py`
**Didaftarkan di:** `apps/universities/urls.py`

#### Endpoints yang Tersedia
| Method | URL | Keterangan |
|--------|-----|------------|
| GET | `/api/sinta-pengabdian/` | Daftar paginated |
| GET | `/api/sinta-pengabdian/?tahun=2023` | Filter tahun |
| GET | `/api/sinta-pengabdian/?skema_kode=KKN` | Filter kode skema |
| GET | `/api/sinta-pengabdian/?sumber=INTERNAL` | Filter sumber dana |
| GET | `/api/sinta-pengabdian/?search=kata` | Cari judul/ketua |
| GET | `/api/sinta-pengabdian/stats/` | Statistik agregat |

#### Response `/api/sinta-pengabdian/stats/`
```json
{
  "total_pengabdian": 6868,
  "total_author": 747,
  "tren_service": [{ "tahun": 2018, "jumlah": 120 }, ...],
  "tren_judul": [{ "tahun": 2020, "jumlah": 550 }, ...],
  "top_skema": [{ "skema": "HIBAH KKN", "jumlah": 2755 }, ...],
  "top_sumber": [{ "sumber": "INTERNAL", "jumlah": 6706 }, ...],
  "top_ketua": [{ "leader_nama": "Ahmad X", "jumlah": 12 }, ...],
  "tahun_list": [2026, 2025, 2024, ...],
  "sumber_list": ["BIMA", "INTERNAL", "SIMLITABMAS"],
  "skema_kode_list": [{ "skema_kode": "KKN", "skema": "HIBAH KKN", "jumlah": 2755 }, ...]
}
```

#### Response `/api/sinta-pengabdian/`
```json
{
  "count": 6868,
  "page": 1,
  "page_size": 20,
  "results": [
    {
      "id": 1,
      "judul": "PELATIHAN KEWIRAUSAHAAN...",
      "leader_nama": "Ahmad Kusuma",
      "skema": "HIBAH KKN ( KKN )",
      "skema_kode": "KKN",
      "tahun": 2024,
      "dana": "Rp. 5.000.000",
      "status": "Approved",
      "sumber": "INTERNAL",
      "authors": [
        { "author_id": 12, "nama": "Ahmad Kusuma", "sinta_id": "123", "pt_singkatan": "UMS", "is_leader": true },
        { "author_id": 45, "nama": "Budi Santoso", "sinta_id": "456", "pt_singkatan": "UAD", "is_leader": false }
      ]
    }
  ]
}
```

---

### 4.2 Frontend — `SintaPengabdianComponent`

**File baru:** `chifoo_frontend/src/app/components/sinta/sinta-pengabdian.component.ts`

**Route:** `/sinta/pengabdian`

#### Struktur Halaman
```
sp-wrap
├── sp-back              ← Breadcrumb "‹ Kembali ke PTMA di SINTA"
├── sp-header            ← Banner biru "🤝 Pengabdian Masyarakat PTMA"
├── sp-cards (4 card)    ← Total Kegiatan | Dosen Terlibat | Skema | Tahun Terbaru
│
├── ACCORDION 1: Tren & Statistik
│   ├── Tren tabs        ← "Jumlah Kegiatan (Author Trend)" | "Jumlah Judul Unik"
│   ├── Line chart SVG   ← Tren per tahun (pure SVG, tanpa library)
│   ├── Bar list         ← Top Skema Pengabdian
│   └── Donut chart      ← Distribusi Sumber Dana (pure SVG)
│
├── ACCORDION 2: Top 10 Ketua Pengabdian
│   └── Ranked list
│
└── ACCORDION 3: Daftar Kegiatan Pengabdian
    ├── Filter bar       ← Search + Dropdown Tahun + Dropdown Sumber Dana + Reset
    ├── Table (klikable) ← #, Judul, Skema, Tahun, Dana, Sumber, Tim
    │   └── Expand row   ← Klik baris → chip nama anggota tim
    └── Pagination       ← ‹ halaman X/Y › + total count
```

#### Fitur Interaktif
- **Expand row** — klik baris tabel untuk melihat semua anggota tim dengan chip warna berbeda (ketua = kuning, anggota = biru)
- **Filter kombinasi** — search teks + dropdown tahun + dropdown sumber dana
- **Debounce search** — delay 400ms saat mengetik, tidak spam request
- **Donut chart** — pie chart distribusi sumber dana dibuat pure SVG (tanpa library Chart.js)
- **Line chart** — tren per tahun dibuat pure SVG dengan grid, dots, labels, dan area fill

---

### 4.3 Perubahan File Lain

| File | Perubahan |
|------|-----------|
| `sinta.component.ts` | Badge "Segera Hadir" → "● Tersedia" di card Pengabdian Masyarakat |
| `app.module.ts` | Import `SintaPengabdianComponent` dari file baru (bukan `pages.ts`) |
| `pages.ts` | Hapus placeholder `SintaPengabdianComponent`, hapus import `Router` yang tidak terpakai |

---

## 5. Alur Data (Pipeline)

```
SINTA Website
  └─ sinta.kemdiktisaintek.go.id/authors/profile/{id}/?view=services
       │
       ▼ (scrape_sinta_author_services.py — dengan login)
JSON Files
  └─ utils/sinta/outs/author_services/{kode_pt}/{sinta_id}_services.json
       │
       ▼ (sp_import_sinta_author_services.py)
Database
  ├── SintaPengabdian (judul unik)
  ├── SintaPengabdianAuthor (relasi ke SintaAuthor)
  └── SintaAuthorTrend (jenis='service', tren tahunan)
       │
       ▼ (Django REST Framework)
API Endpoints
  └── /api/sinta-pengabdian/
  └── /api/sinta-pengabdian/stats/
       │
       ▼ (Angular HTTP)
Frontend Component
  └── /sinta/pengabdian
       ├── Statistik & Tren
       ├── Top Ketua
       └── Daftar Kegiatan (dengan filter & pagination)
```

---

## 6. Rencana Pengembangan

### Prioritas Tinggi

#### [A] Selesaikan Import Data
- **Status:** Sedang berjalan (2 instance paralel)
- **Target:** Semua 17,861 file JSON terimpor
- **Estimasi:** Beberapa jam ke depan
- **Setelah selesai:** Verifikasi jumlah `SintaPengabdian` dan `SintaPengabdianAuthor` di DB

#### [B] Link ke Profil Author
- Saat ini chip nama anggota tim hanya menampilkan teks
- **Rencana:** Tambahkan klik ke profil author (`/sinta/author?id=X`)
- Sama seperti fitur popup di `sinta-artikel.component.ts`
- **File:** `sinta-pengabdian.component.ts` — bagian `sp-authors` section

#### [C] Statistik per Perguruan Tinggi
- Tambahkan breakdown pengabdian per PT (seperti di sinta-afiliasi)
- **Backend:** Tambahkan endpoint `/api/sinta-pengabdian/by-pt/`
  ```sql
  SELECT pt.singkatan, COUNT(DISTINCT p.id)
  FROM sinta_pengabdian p
  JOIN sinta_pengabdian_author pa ON pa.pengabdian_id = p.id
  JOIN sinta_author a ON a.id = pa.author_id
  JOIN sinta_afiliasi af ON af.id = a.afiliasi_id
  JOIN perguruan_tinggi pt ON pt.id = af.perguruan_tinggi_id
  GROUP BY pt.singkatan
  ORDER BY COUNT DESC
  ```
- **Frontend:** Tambahkan barchart/tabel distribusi per PT di Accordion 1

#### [D] Badge "Segera Hadir" → "● Tersedia" di sinta.component.ts
- **Status:** SUDAH DILAKUKAN hari ini ✓

---

### Prioritas Menengah

#### [E] Normalisasi Data Skema
Data skema saat ini masih redundan karena inkonsistensi dari SINTA:
```
"PKM ( PKM IPT )"        # tanpa tanda hubung
"PKM ( PKM-IPT )"        # dengan tanda hubung
"PENGABDIAN KEPADA MASYARAKAT ( PKMIPT )"
```
- **Rencana:** Tambahkan kolom `skema_normalized` di model atau lakukan post-processing
- Atau: buat lookup table `skema_kode → nama_standar`
- Contoh mapping:
  ```
  KKN      → Kuliah Kerja Nyata (KKN)
  PKM      → Program Kemitraan Masyarakat (PKM)
  PKM-IPT  → PKM Ilmu Pengetahuan & Teknologi
  PKMIPT   → PKM Ilmu Pengetahuan & Teknologi
  PKPM     → PKM Pemberdayaan Masyarakat
  ```

#### [F] Filter Skema Kode di Frontend
- Dropdown filter skema kode sudah disiapkan di backend (`skema_kode_list`)
- Belum diimplementasi di frontend (hanya ada filter sumber dan tahun)
- **Rencana:** Tambahkan `<select>` skema di filter bar

#### [G] Tren per Skema (Stacked Bar Chart)
- Tampilkan kontribusi skema per tahun dalam stacked bar chart
- Mirip dengan chart distribusi kuartil di `sinta-artikel.component.ts`
- **Data:** Sudah tersedia via `/api/sinta-pengabdian/?tahun=X&skema_kode=Y`

#### [H] Export Data
- Tombol "Download CSV" untuk tabel daftar kegiatan
- Pakai `text/csv` dan `Blob` di browser, tanpa backend tambahan

---

### Prioritas Rendah (Jangka Panjang)

#### [I] Halaman Detail per Kegiatan
- Route: `/sinta/pengabdian/:id`
- Tampilkan detail lengkap: deskripsi, tim, output (jika ada), link SINTA
- **Kendala:** SINTA tidak menyimpan abstrak/deskripsi kegiatan pengabdian

#### [J] Peta Sebaran Pengabdian
- Visualisasi peta Indonesia dengan pin per wilayah
- Berdasarkan PT asal ketua/anggota
- **Dependency:** Data koordinat PT sudah ada di model `PerguruanTinggi` (latitude, longitude)

#### [K] Perbandingan Penelitian vs Pengabdian
- Tambahkan panel perbandingan di halaman Author (`/sinta/author`)
- Tabel: dosen X punya Y penelitian dan Z pengabdian
- **Dependency:** `SintaPenelitianComponent` perlu dibangun lebih dulu (masih placeholder)

#### [L] Integrasi Informasi Dana
- Dana saat ini berupa string teks: `"Rp. 5.000.000"`
- **Rencana:** Parse dan simpan sebagai `IntegerField` di model
- Butuh **migration baru** + script konversi data yang sudah ada
- Manfaat: bisa hitung total dana, rata-rata per kegiatan, distribusi range dana

#### [M] Notifikasi Data Baru
- Kirim notifikasi ke admin ketika data pengabdian baru terdeteksi
- **Dependency:** Sistem notifikasi sudah ada di `apps/monitoring/models.py`

---

## 7. Referensi Teknis

### File yang Relevan

| Kategori | Path |
|----------|------|
| **Model** | `chifoo_backend/apps/universities/models.py` (baris ~1035–1091) |
| **Migration** | `chifoo_backend/apps/universities/migrations/0021_sinta_pengabdian.py` |
| **ViewSet** | `chifoo_backend/apps/universities/views.py` — `SintaPengabdianViewSet` (akhir file) |
| **URL Router** | `chifoo_backend/apps/universities/urls.py` |
| **Scraper** | `chifoo_backend/utils/sinta/scrape_sinta_author_services.py` |
| **Importer** | `chifoo_backend/utils/sinta/sp_import_sinta_author_services.py` |
| **JSON Output** | `chifoo_backend/utils/sinta/outs/author_services/{kode_pt}/{sinta_id}_services.json` |
| **Frontend Component** | `chifoo_frontend/src/app/components/sinta/sinta-pengabdian.component.ts` |
| **Route** | `chifoo_frontend/src/app/app.module.ts` → `{ path: 'sinta/pengabdian', component: SintaPengabdianComponent }` |
| **Menu Card** | `chifoo_frontend/src/app/components/sinta/sinta.component.ts` |

---

### Perintah Berguna

```bash
# Cek jumlah data di DB
cd chifoo_backend
DJANGO_SETTINGS_MODULE=ptma.settings.base python -c "
import django; django.setup()
from apps.universities.models import SintaPengabdian, SintaPengabdianAuthor
print('Pengabdian:', SintaPengabdian.objects.count())
print('Author relasi:', SintaPengabdianAuthor.objects.count())
"

# Jalankan import (jika perlu diulang)
python -u utils/sinta/sp_import_sinta_author_services.py

# Cek proses import yang sedang berjalan
ps aux | grep sp_import | grep -v grep

# Test API endpoint
curl http://172.16.64.194:8000/api/sinta-pengabdian/stats/ | python -m json.tool
curl "http://172.16.64.194:8000/api/sinta-pengabdian/?page=1&page_size=5" | python -m json.tool
```

---

### Catatan Login SINTA

Scraper memerlukan login ke SINTA. URL login yang benar:
```python
# 1. Ambil session cookie dulu
GET https://sinta.kemdiktisaintek.go.id/logins

# 2. Login dengan POST
POST https://sinta.kemdiktisaintek.go.id/logins/do_login
# Body: email=xxx&password=xxx

# JANGAN gunakan /logins/pclogin (sudah 404)
```

---

### Perbedaan Penelitian vs Pengabdian di SINTA

| Aspek | Penelitian | Pengabdian |
|-------|-----------|------------|
| View parameter | `?view=researches` | `?view=services` |
| Chart JS ID | `research-chart-articles` | `service-chart-articles` |
| Model | `SintaPenelitian` | `SintaPengabdian` |
| Author Model | `SintaPenelitianAuthor` | `SintaPengabdianAuthor` |
| Trend jenis | `'research'` | `'service'` |
| Scraper | `scrape_sinta_author_researches.py` | `scrape_sinta_author_services.py` |
| Importer | `sp_import_sinta_author_researches.py` | `sp_import_sinta_author_services.py` |
| JSON folder | `outs/author_researches/` | `outs/author_services/` |

---

*Logbook ini akan diperbarui seiring perkembangan fitur.*
---

## 8. Riwayat Perubahan

| Tanggal | Versi | Perubahan |
|---------|-------|-----------|
| 2026-03-23 | v0.1 | Model DB, scraper, importer selesai |
| 2026-03-24 | v1.0 | Backend API + Frontend halaman penuh dirilis |
| 2026-03-24 | v1.1 | Fix data: koreksi tahun typo `20232`→`2023`, hapus `2027`/`2028`; tambah validasi tahun di kedua importer; fix label chart X-axis terlalu rapat |

*Terakhir diperbarui: 2026-03-24*
