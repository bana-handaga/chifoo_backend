# Session Log — 2026-03-24

## Topik 1: Status & Eksekusi Scraping Artikel Scopus

### Status Awal
| Keterangan | Jumlah |
|------------|--------|
| Total author Scopus di DB | 6,664 |
| Sudah discrape (file JSON) | 4,675 (70.2%) |
| Belum discrape | 1,989 (29.8%) |
| Total file JSON | 4,682 |
| Not Found (0 artikel) | 10 |
| Total artikel terscrape | 35,486 |

### Proses yang Dijalankan

#### Import JSON → DB (paralel 2 instance)
Script: `utils/sinta/sp_import_sinta_scopus_articles.py`

Ditambahkan parameter `--offset` ke script importer agar bisa dijalankan paralel:
```python
parser.add_argument("--offset", type=int, default=0)
# ...
if args.offset:
    files = files[args.offset:]
```

Dijalankan 2 instance bersamaan:
```bash
python utils/sinta/sp_import_sinta_scopus_articles.py --offset 0 --limit 2360
python utils/sinta/sp_import_sinta_scopus_articles.py --offset 2360
```

#### Scraping Author Baru (paralel 2 instance)
Script: `utils/sinta/scrape_sinta_scopus_articles.py` (sudah punya `--offset`)

> **Catatan:** `--offset` menghitung dari semua author di DB (6,664), bukan hanya yang belum discrape.
> Author yang sudah punya file JSON akan otomatis di-skip oleh `find_existing()`.
> Pembagian harus mempertimbangkan distribusi unscraped di seluruh list.

```bash
# Instance 1: author index 995–3,829
python utils/sinta/scrape_sinta_scopus_articles.py --offset 995 --limit 2835

# Instance 2: author index 3,830–6,663
python utils/sinta/scrape_sinta_scopus_articles.py --offset 3830
```

#### Hasil Instance 1 Scraper
```
Selesai: 411 scraped, 1 not_found, 2423 dilewati, 0 error.
```

### Pelajaran
- Import dan scraping bisa berjalan **bersamaan** tanpa konflik (scraper nulis JSON, importer baca JSON).
- Pembagian `--offset` untuk scraper harus dari **total author di DB**, bukan jumlah yang belum discrape.

---

## Topik 2: Problem 401 dari Domain `pt.biroti-ums.id`

### Gejala
Frontend yang diakses dari `https://pt.biroti-ums.id` mendapat error:
```
Failed to load resource: the server responded with a status of 401
```

### Investigasi

#### Alur Autentikasi Frontend
- Token disimpan di `localStorage` dengan key `ptma_token` (`auth.service.ts:9`)
- `AuthInterceptor` membaca token dari `AuthService.getToken()` dan menambahkan header `Authorization: Token xxx` ke setiap request
- Saat app init, `auth.service.ts:55` memanggil `/api/auth/me/` untuk refresh data user — endpoint ini membutuhkan token

#### Root Cause
`localStorage` bersifat **domain-specific**. Token yang tersimpan di domain lain (misal saat login di `chifoo.biroti-ums.id`) **tidak tersedia** di `pt.biroti-ums.id`. Akibatnya request ke endpoint `IsAuthenticated` mengembalikan 401.

#### Konfigurasi Relevan
| Setting | Nilai |
|---------|-------|
| Default permission | `IsAuthenticated` (base.py:109) |
| Auth backend | `TokenAuthentication` + `SessionAuthentication` |
| CORS production | Dari env var `CORS_ALLOWED_ORIGINS` (production.py:137) |
| API URL production | `https://chifoo.biroti-ums.id/api` (environment.prod.ts) |

#### Endpoint yang Membutuhkan Auth
- `/api/auth/me/` — dipanggil saat app init
- `/api/laporan-pt/` — `IsAuthenticated`
- `/api/isi-laporan/` — `IsAuthenticated`
- `/api/notifikasi/` — `IsAuthenticated`
- `/api/users/` — `IsAuthenticated`

Endpoint publik (AllowAny untuk GET): semua ViewSet berbasis `PublicReadAdminWriteMixin` (universities, monitoring read-only).

### Solusi

**Kemungkinan 1 — User belum login:**
User harus login dari domain `pt.biroti-ums.id` karena localStorage berbeda per domain.

**Kemungkinan 2 — Domain belum di CORS_ALLOWED_ORIGINS:**
Cek di server production:
```bash
echo $CORS_ALLOWED_ORIGINS
```
Jika belum ada, tambahkan:
```
CORS_ALLOWED_ORIGINS=https://chifoo.biroti-ums.id,https://pt.biroti-ums.id
```
Lalu restart Django.

---

## Topik 3: Scraping Artikel Scopus — Selesai 100%

### Hasil Akhir
| Keterangan | Jumlah |
|------------|--------|
| Author Scopus di DB | 6,664 |
| Sudah discrape | **6,664 (100%)** |
| Total file JSON | 6,664 |
| Not Found (0 artikel) | 17 |
| Total artikel terscrape | 43,551 |

### Import ke DB
Dijalankan 3 instance paralel dengan `python -u` (unbuffered agar output ter-flush):
```bash
python -u utils/sinta/sp_import_sinta_scopus_articles.py --offset 0    --limit 2220
python -u utils/sinta/sp_import_sinta_scopus_articles.py --offset 2220 --limit 2220
python -u utils/sinta/sp_import_sinta_scopus_articles.py --offset 4440
```

**Hasil DB:**
- `SintaScopusArtikel`: **28,569 artikel unik** (dari 43,551 raw — sisanya duplikat EID antar-author)
- `ArtikelAuthor`: **41,911 relasi**

### Pelajaran Penting
- Gunakan `python -u` saat run background agar output tidak ter-buffer
- `update_or_create` by EID aman dijalankan paralel (tidak duplikat)
- Selisih ~15,000 antara raw vs DB adalah duplikat artikel kolaborasi multi-author

---

## Topik 4: Scraping Penelitian Author (view=researches)

### Latar Belakang
Data penelitian dosen (judul, ketua, skema, dana, anggota) tersedia di:
```
https://sinta.kemdiktisaintek.go.id/authors/profile/{sinta_id}/?view=researches
```
Setiap halaman menampilkan max ~10 penelitian, tidak ada pagination.

### Struktur Data Per Item
| Field | Contoh |
|-------|--------|
| `judul` | Potensi Cookies Tepung Biji Nangka... |
| `leader_nama` | Sudrajah Warajati Kisnawaty |
| `skema` | Penelitian Kompetitif Nasional ( PFR ) |
| `skema_kode` | PFR / RIKOM / PID / HIT |
| `tahun` | 2025 |
| `dana` | Rp. 110.330.000 |
| `status` | Approved |
| `sumber` | BIMA / INTERNAL |
| `personils` | list nama + sinta_id anggota |

### Model DB Baru (migration 0020)
```python
SintaPenelitian         # unique by (judul, tahun, skema_kode)
SintaPenelitianAuthor   # M2M: penelitian ↔ SintaAuthor, field is_leader
```

### Script Baru
- `utils/sinta/scrape_sinta_author_researches.py` — scraper per author
- `utils/sinta/sp_import_sinta_author_researches.py` — importer JSON → DB

### Dijalankan 2 Instance Paralel
```bash
python utils/sinta/scrape_sinta_author_researches.py --offset 0     --limit 8930
python utils/sinta/scrape_sinta_author_researches.py --offset 8930
```

### Status Akhir Sesi
| Keterangan | Jumlah |
|------------|--------|
| Author di DB | 17,861 |
| Sudah discrape | 15,167 (84.9%) |
| Belum discrape | 2,694 |
| Tidak ada penelitian | 2,873 |
| Total penelitian terscrape | 76,459 |

---

## Topik 5: Fitur Frontend — Daftar Artikel Scopus

### Perubahan `sinta-artikel.component.ts`

#### 1. Penulis PTMA di Tiap Artikel
API `sinta-scopus-artikel` ditambah field `penulis_ptma[]`:
```json
{
  "author_id": 1263,
  "nama": "AGUS SUDARYANTO",
  "pt_singkatan": "UMS",
  "urutan_penulis": 1394,
  "total_penulis": 1598
}
```
Tampil di bawah tiap artikel: `AGUS SUDARYANTO (UMS), SETYANINGRUM RAHMAWATY (UMS)`

#### 2. Popup Profil Author
Klik nama penulis → popup overlay menampilkan:
- Foto, nama, PT, departemen, bidang keilmuan
- SINTA Score (overall + 3 tahun)
- Tabel stats: Scopus / Google Scholar / WoS (artikel, sitasi, H-index)
- Distribusi kuartil Q1–Q4
- Link ke profil SINTA lengkap

Tutup: klik overlay atau tombol ✕

#### 3. Filter Author dengan Autocomplete
- Input search author (debounce 300ms) → query `/api/sinta-author/?search=xxx`
- Dropdown max 8 hasil: nama + PT singkatan
- Pilih → filter aktif (nama tampil biru + tombol ✕)
- Bisa dikombinasikan dengan filter judul, kuartil, tahun

### Backend Changes
- `prefetch_related` diperluas ke `author__afiliasi__perguruan_tinggi`
- `penulis_ptma` ditambah field `pt_singkatan`

### Catatan Deploy
```bash
# Di server production setelah pull:
python manage.py migrate         # migration 0020
python manage.py createcachetable  # jika belum (database cache)
```

---

## Topik 6: Scraping Pengabdian Masyarakat Author (view=services)

### Latar Belakang
Data pengabdian masyarakat dosen (community service) tersedia di:
```
https://sinta.kemdiktisaintek.go.id/authors/profile/{sinta_id}/?view=services
```
Halaman ini memerlukan **login** untuk melihat semua item melalui pagination.
Tanpa login hanya tampil 10 item terbaru (no pagination).
Setelah login, tersedia pagination `?page=N` dengan 10 item per halaman.

### Struktur HTML Per Item
Sama dengan `?view=researches` — menggunakan CSS class `.ar-list-item`:
| CSS Class | Data |
|-----------|------|
| `.ar-title` | Judul pengabdian |
| `.ar-meta` (Leader) | Nama ketua + skema (`.ar-pub`) |
| `.ar-meta` (Personils) | Anggota (link ke profil author) |
| `.ar-year` | Tahun |
| `.ar-quartile` | Dana (Rp.), status (`.text-success`), sumber (`.text-info`) |

### Tren Tahunan
Tersedia via JS chart `service-chart-articles` pada halaman yang sama:
```js
xAxis.data: ['2018','2019',...], series[0].data: [2,3,...]
```
→ Di-parse dan disimpan ke `SintaAuthorTrend` dengan `jenis='service'`.

### Model DB Baru (migration 0021)
```python
SintaPengabdian         # unique by (judul, tahun, skema_kode)
SintaPengabdianAuthor   # M2M: pengabdian ↔ SintaAuthor, field is_leader
```
Tren tahunan menggunakan model yang sudah ada: `SintaAuthorTrend (jenis='service')`.

### Script Baru
| Script | Fungsi |
|--------|--------|
| `utils/sinta/scrape_sinta_author_services.py` | Scraper per author, multi-page, login |
| `utils/sinta/sp_import_sinta_author_services.py` | Import JSON → DB (pengabdian + tren) |

### Catatan Penting: Login URL
Login SINTA yang benar (berbeda dari scraper lama):
```python
# SALAH (404):
LOGIN_URL = f"{BASE_URL}/logins/pclogin"

# BENAR:
LOGIN_URL = f"{BASE_URL}/logins/do_login"
# + fetch GET /logins dulu untuk session cookie sebelum POST
```

### Flow Scraper (Multi-Page)
```python
# 1. Login
# 2. Fetch page=1 → parse items + service_history chart + get_last_page()
# 3. Loop page 2..last → parse items tambahan
# 4. Simpan semua ke JSON
```

### Output JSON
```json
{
  "sinta_id": "5975482",
  "scraped_at": "...",
  "total_scraped": 16,
  "service_history": {"2017": 2, "2018": 3, ...},
  "services": [
    {
      "judul": "PELATIHAN ANALISIS KELAYAKAN...",
      "leader_nama": "...",
      "skema": "PKM PID ( PKM-PID )",
      "skema_kode": "PKM-PID",
      "tahun": 2024,
      "dana": "Rp. 5.000.000",
      "status": "Approved",
      "sumber": "INTERNAL",
      "personils": [{"nama": "...", "sinta_id": "..."}]
    }
  ]
}
```

### Status Awal Scraping
| Keterangan | Jumlah |
|------------|--------|
| Author di DB | 17,861 |
| Sudah discrape | 2 (test) |
| Belum discrape | 17,859 |

### Catatan Deploy
```bash
# Di server production setelah pull:
python manage.py migrate         # migration 0021
```

---

## Topik 7: Update Scraper Penelitian — Tambah Tren Tahunan & Multi-Page

### Masalah
Scraper `scrape_sinta_author_researches.py` (sesi kemarin) tidak menangkap:
1. **Tren tahunan** (`research_history`) dari JS chart `research-chart-articles`
2. **Pagination** — halaman `?view=researches` juga bisa >1 halaman jika login (sama seperti services)
3. Login URL salah (`/logins/pclogin` → harusnya `/logins/do_login`)

### Perubahan Script

#### `scrape_sinta_author_researches.py`
- Fix `LOGIN_URL` → `/logins/do_login` + GET `/logins` dulu untuk session cookie
- Fix `is_session_expired()` → cek `action="...do_login"` dalam HTML
- Tambah `parse_research_history()` — parse JS chart `research-chart-articles`
- Tambah `get_last_page()` — baca pagination
- Update `run()` — loop page 2..last, save `research_history` ke JSON

#### `sp_import_sinta_author_researches.py`
- Tambah `import_research_history()` — simpan ke `SintaAuthorTrend(jenis='research')`
- Update `import_file()` — return tuple `(p_count, r_count, t_count)`
- Skip empty hanya jika tidak ada `researches` DAN tidak ada `research_history`

### Re-Scrape dengan --force
Dijalankan 2 instance paralel (`--force` karena file lama tidak punya `research_history`):
```bash
python -u utils/sinta/scrape_sinta_author_researches.py --force --offset 0    --limit 8931
python -u utils/sinta/scrape_sinta_author_researches.py --force --offset 8931
```

Contoh output baru:
```
[1/8931] 6005631 ok (50 penelitian [5p], tren=0 tahun)
[3/8931] 23026   ok (25 penelitian [3p], tren=8 tahun)
```
→ Artinya halaman memiliki 5 halaman (50 item), tren terdeteksi.

### Catatan Penting
- Chart JS SINTA untuk penelitian: `research-chart-articles` (berbeda dari `service-chart-articles`)
- `?view=researches` juga berpaginasi saat login — sebelumnya hanya scrape page 1
- File JSON lama perlu di-re-scrape (`--force`) karena tidak ada `research_history`

---

## Topik 8: Halaman Frontend Pengabdian Masyarakat — Rilis Pertama

### Latar Belakang
Sebelumnya halaman `/sinta/pengabdian` hanya menampilkan placeholder "Segera Hadir".
Seluruh infrastruktur backend (model, scraper, importer) sudah siap sejak 2026-03-23.
Hari ini, halaman penuh dibangun dan dirilis.

### File Baru / Diubah

| File | Jenis | Keterangan |
|------|-------|------------|
| `apps/universities/views.py` | Ubah | Tambah `SintaPengabdianViewSet` di akhir file |
| `apps/universities/urls.py` | Ubah | Daftarkan `sinta-pengabdian` ke router |
| `chifoo_frontend/…/sinta-pengabdian.component.ts` | Baru | Komponen Angular halaman penuh |
| `chifoo_frontend/…/app.module.ts` | Ubah | Import komponen baru, pisah dari `pages.ts` |
| `chifoo_frontend/…/pages.ts` | Ubah | Hapus placeholder `SintaPengabdianComponent` |
| `chifoo_frontend/…/sinta.component.ts` | Ubah | Badge "Segera Hadir" → "● Tersedia" |

### Endpoint Backend Baru

| Method | URL | Keterangan |
|--------|-----|------------|
| GET | `/api/sinta-pengabdian/` | Daftar paginated (filter: tahun, skema_kode, sumber, search) |
| GET | `/api/sinta-pengabdian/stats/` | Statistik agregat (tren, skema, sumber, ketua) |

### Struktur Halaman Frontend (`/sinta/pengabdian`)
```
Header biru 🤝 + 4 summary cards (total kegiatan, dosen, skema, tahun terbaru)
Accordion 1 — Tren & Statistik
  ├─ Line chart tren (tab: Author Trend | Judul Unik)
  ├─ Bar list Top Skema
  └─ Donut chart Sumber Dana
Accordion 2 — Top 10 Ketua Pengabdian
Accordion 3 — Daftar Kegiatan (filter + tabel + expand tim + pagination)
```

### Status Data Saat Rilis
| Keterangan | Jumlah |
|------------|--------|
| `SintaPengabdian` (judul unik di DB) | 9,413 |
| `SintaPengabdianAuthor` (relasi) | 10,692 |
| Author unik terlibat | 837 |
| `SintaAuthorTrend (jenis='service')` | 41,290 |
| Import masih berjalan | Ya (paralel 2 instance) |

---

## Topik 9: Perbaikan Data & Validasi Tahun Importer

### Masalah Ditemukan
Saat memeriksa data tren di `SintaAuthorTrend (jenis='service')`, ditemukan 3 record dengan tahun tidak valid:

| ID | Tahun Salah | Penyebab | Tindakan |
|----|------------|----------|----------|
| 420322 | `20232` | Typo scraping ("2023" + karakter ekstra) | Dikoreksi → `2023` |
| 318152 | `2027` | Tahun melebihi batas wajar | Dihapus |
| 318001 | `2028` | Tahun melebihi batas wajar | Dihapus |

**Perbaikan DB dijalankan langsung via Django shell:**
```python
# Koreksi typo
SintaAuthorTrend.objects.filter(id=420322).update(tahun=2023)

# Hapus future year
SintaAuthorTrend.objects.filter(jenis='service', tahun__gt=2026).delete()
```

**Verifikasi pasca-perbaikan:**
```
Rentang tahun service: min=1999, max=2026
Record tahun > 2026 : 0
```

### Perbaikan Importer — Validasi Tahun

Diterapkan ke dua importer: `sp_import_sinta_author_services.py` dan `sp_import_sinta_author_researches.py`.

**Sebelum:**
```python
tahun = r.get("tahun")
# ← tidak ada validasi, langsung dipakai
```

**Sesudah:**
```python
CURRENT_YEAR = 2026
tahun_raw = r.get("tahun")
if tahun_raw is not None:
    try:
        tahun = int(str(tahun_raw))   # tangkap typo seperti "20232"
    except (ValueError, TypeError):
        tahun = None
    else:
        if tahun > CURRENT_YEAR or tahun < 1990:
            tahun = None              # tolak future year & tahun tidak masuk akal
else:
    tahun = None
```

Validasi yang sama diterapkan pada blok `service_history` / `research_history` (tren tahunan):
```python
CURRENT_YEAR = 2026
try:
    tahun_int = int(str(yr_str))
except (ValueError, TypeError):
    continue
if tahun_int > CURRENT_YEAR or tahun_int < 1990:
    continue     # skip, tidak disimpan ke SintaAuthorTrend
```

### Perbaikan Frontend — Label Tahun Chart Terlalu Rapat

**Masalah:** Dengan data dari 1999–2026 (28 titik), label tahun di X-axis chart saling bertumpuk.

**Solusi — Method `lcLabelPoints()` baru:**
```typescript
lcLabelPoints(data): Point[] {
  const pts = this.lcPoints(data);
  if (pts.length <= 12) return pts;         // ≤ 12 titik: tampil semua
  const step = Math.ceil(pts.length / 12);
  return pts.filter((_, i) =>
    i === 0 || i === pts.length - 1 || i % step === 0
  );
}
```
- Maksimal **12 label** di X-axis
- Titik pertama dan terakhir selalu ditampilkan
- Font size dikurangi `10` → `9` px (SVG units)

### Catatan
- Validasi `tahun > CURRENT_YEAR` menggunakan konstanta `CURRENT_YEAR = 2026` — perlu diupdate manual tiap tahun (atau ganti dengan `datetime.date.today().year`)
- Data penelitian di `SintaAuthorTrend (jenis='research')` belum dicek — perlu diverifikasi tersendiri setelah re-scrape selesai

---

## Topik 10: Perbaikan UX — Accordion Default Tertutup

### Perubahan
Di `sinta-pengabdian.component.ts`, ketiga accordion sebelumnya terbuka saat halaman pertama kali dimuat:
```typescript
// Sebelum
acc1Open = true;
acc2Open = true;
acc3Open = true;
```

Diubah agar semua accordion tertutup secara default:
```typescript
// Sesudah
acc1Open = false;
acc2Open = false;
acc3Open = false;
```

### Alasan
Halaman memuat data statistik (chart, top ketua) dan daftar (tabel paginasi) sekaligus saat init.
Accordion tertutup secara default mengurangi visual clutter dan memberi pengguna kontrol penuh
tentang bagian mana yang ingin mereka lihat terlebih dahulu.

---

## Topik 11: Halaman Frontend Penelitian — Rilis Pertama

### Latar Belakang
Setelah halaman Pengabdian Masyarakat selesai (Topik 8), halaman `/sinta/penelitian`
masih menampilkan placeholder "Segera Hadir". Infrastruktur backend (model `SintaPenelitian`,
`SintaPenelitianAuthor`, scraper, importer, tren `jenis='research'`) telah siap sejak Topik 4 & 7.
Halaman penuh dibangun dan dirilis dalam sesi ini.

### File Baru / Diubah

| File | Jenis | Keterangan |
|------|-------|------------|
| `apps/universities/views.py` | Ubah | Import `SintaPenelitian, SintaPenelitianAuthor`; tambah `SintaPenelitianViewSet` |
| `apps/universities/urls.py` | Ubah | Daftarkan `sinta-penelitian` ke router |
| `chifoo_frontend/…/sinta-penelitian.component.ts` | **Baru** | Komponen Angular halaman penuh |
| `chifoo_frontend/…/app.module.ts` | Ubah | Import `SintaPenelitianComponent` dari file baru (bukan `pages.ts`) |
| `chifoo_frontend/…/pages.ts` | Ubah | Hapus placeholder `SintaPenelitianComponent` |
| `chifoo_frontend/…/sinta.component.ts` | Ubah | Badge "Segera Hadir" → "● Tersedia" untuk card Penelitian |

### Endpoint Backend Baru

| Method | URL | Keterangan |
|--------|-----|------------|
| GET | `/api/sinta-penelitian/` | Daftar paginated (filter: `tahun`, `skema_kode`, `sumber`, `search`) |
| GET | `/api/sinta-penelitian/stats/` | Statistik agregat |

### Payload `/api/sinta-penelitian/stats/`
```json
{
  "total_penelitian": 42318,
  "total_author": 5210,
  "tren_research": [{"tahun": 2010, "jumlah": 120}, ...],
  "tren_judul":    [{"tahun": 2010, "jumlah": 98}, ...],
  "top_skema":     [{"skema": "Penelitian Kompetitif Nasional (PFR)", "jumlah": 3210}, ...],
  "top_sumber":    [{"sumber": "BIMA", "jumlah": 22140}, ...],
  "top_ketua":     [{"author_id": 1263, "leader_nama": "...", "pt_singkatan": "UMS", "jumlah": 47}, ...],
  "tahun_list":    [2026, 2025, ...],
  "sumber_list":   ["BIMA", "INTERNAL", ...],
  "skema_kode_list": [{"skema_kode": "PFR", "skema": "...", "jumlah": 3210}, ...]
}
```

### Struktur Halaman Frontend (`/sinta/penelitian`)
```
Header hijau 🔬 + 4 summary cards (total penelitian, dosen terlibat, skema, tahun terbaru)
Accordion 1 — Tren & Statistik (default: tertutup)
  ├─ Line chart tren (tab: Author Trend (jenis='research') | Judul Unik)
  ├─ Bar list Top Skema Penelitian
  └─ Donut chart Distribusi Sumber Dana
Accordion 2 — Top 10 Ketua Penelitian (default: tertutup)
  └─ Tiap baris klikable → popup profil author
Accordion 3 — Daftar Kegiatan Penelitian (default: tertutup)
  ├─ Filter: search teks, dropdown tahun, dropdown sumber dana
  ├─ Tabel: #, Judul, Skema, Tahun, Dana, Sumber, Tim
  │    └─ Klik baris → expand tim (chip per author, klik → popup profil)
  └─ Paginasi (20 per halaman, max 200)
```

### Perbedaan dari Halaman Pengabdian

| Aspek | Pengabdian | Penelitian |
|-------|-----------|-----------|
| Warna tema | Biru `#0284c7` | Hijau `#059669` |
| Icon header | 🤝 | 🔬 |
| Tren API key | `tren_service` | `tren_research` |
| `jenis` SintaAuthorTrend | `'service'` | `'research'` |
| Highlight baris expand | `#f0f9ff` (biru muda) | `#ecfdf5` (hijau muda) |
| Chip author warna default | `#e0f2fe` / `#0369a1` | `#d1fae5` / `#065f46` |
| Tab tren default | `'service'` | `'research'` |

### TitleCase Pipe
Komponen ini **tidak** mendefinisikan ulang `TitleCaseIdPipe`. Pipe `titleCaseId` yang
sudah dideklarasikan di `app.module.ts` (dari `sinta-pengabdian.component.ts`) digunakan
langsung di template. Judul kegiatan, nama ketua, dan nama author di popup tampil dengan
kombinasi huruf besar-kecil standar Indonesia (acronym whitelist ~100 entri).

### Author Popup
Identik dengan halaman Pengabdian — memanggil `/api/sinta-author/{id}/` dan menampilkan:
foto, nama, PT, departemen, bidang keilmuan, SINTA Score, tabel statistik publikasi
(Scopus/GScholar/WoS), distribusi kuartil, output riset, sparkline tren, link profil SINTA.
Urutan sparkline di popup dibalik: Penelitian (hijau) tampil di atas, Pengabdian (biru) di bawah.

### Catatan Teknis
- `SintaPenelitianAuthor.penelitian_authors` adalah `related_name` yang digunakan
  untuk `prefetch_related` di ViewSet
- `top_ketua` di stats menggunakan `SintaPenelitianAuthor.objects.filter(is_leader=True)`
  agar mendapat `author_id` (bukan hanya string nama ketua dari field `leader_nama`)
- Semua accordion default tertutup (konsisten dengan keputusan di Topik 10)

---

## Topik 12: Phase 1 — Analisis Jaringan Kolaborasi (Co-Authorship Network)

### Latar Belakang
Inisiasi fitur deteksi jaringan kerjasama antar peneliti/dosen berbasis data yang sudah
ada di DB: `SintaPenelitianAuthor`, `SintaPengabdianAuthor`, dan `SintaScopusArtikelAuthor`.
Dua peneliti terhubung jika muncul bersama dalam satu item (penelitian / pengabdian / artikel).

### Library yang Digunakan
| Library | Versi | Fungsi |
|---------|-------|--------|
| `networkx` | 3.6.1 | Representasi graf, spring_layout, betweenness_centrality, density |
| `python-louvain` (community) | 0.16 | Deteksi komunitas (Louvain algorithm) |

Kedua library sudah terinstal di environment production.

### Model Baru: `KolaboasiSnapshot` (migration 0022)

```python
class KolaboasiSnapshot(models.Model):
    sumber     = models.CharField(max_length=20, default='all')
    min_bobot  = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    data       = models.JSONField()
    MAX_HISTORY = 3

    @classmethod
    def save_snapshot(cls, data, sumber='all', min_bobot=1):
        # FIFO — hapus snapshot lama jika > MAX_HISTORY
        snap = cls.objects.create(sumber=sumber, min_bobot=min_bobot, data=data)
        old = cls.objects.filter(sumber=sumber).order_by('-created_at')[cls.MAX_HISTORY:]
        cls.objects.filter(pk__in=old).delete()
        return snap

    @classmethod
    def latest(cls, sumber='all'):
        return cls.objects.filter(sumber=sumber).first()
```

Pola cache FIFO identik dengan `RisetLdaDeskripsi` / `RisetAnalisisSnapshot`.

### Script Pembangun Graf: `utils/sinta/build_kolaboasi_graph.py`

#### Alur Komputasi
```
1. SQL self-join per tabel M2M → pasangan (author_a, author_b) per sumber
2. Akumulasi edge_weight (int) + edge_sources (set) untuk setiap pasangan
3. Filter edge dengan weight < min_bobot
4. Bangun nx.Graph + hapus isolated nodes
5. Hitung degree centrality
6. Hitung betweenness_centrality (k=500 approximation agar cepat)
7. Louvain community detection (random_state=42, reproducible)
8. Filter top-N nodes berdasarkan degree (default max_nodes=500)
9. Ambil metadata author dari DB (nama, PT, sinta_score, sinta_id)
10. spring_layout pada subgraph top nodes, normalisasi ke [0.02, 0.98]
11. Serialize nodes, edges, komunitas stats, top_pairs, top_pt
12. Simpan ke KolaboasiSnapshot
```

#### SQL Self-Join (pasangan co-author)
```sql
SELECT a.author_id, b.author_id
FROM   universities_sintapenelitianauthor a
JOIN   universities_sintapenelitianauthor b
       ON a.penelitian_id = b.penelitian_id
      AND a.author_id < b.author_id
```
Digunakan `a.id < b.id` constraint untuk menghindari duplikat simetris.
Lebih efisien dari ORM untuk self-join pada tabel besar.

#### Struktur Output JSON (disimpan ke `KolaboasiSnapshot.data`)
```json
{
  "ready": true,
  "sumber": "all",
  "min_bobot": 1,
  "elapsed_sec": 9.5,
  "stats": {
    "total_nodes": 6485,
    "total_edges": 10435,
    "total_komunitas": 639,
    "display_nodes": 500,
    "display_edges": ...,
    "density": 0.000496,
    "avg_degree": 3.22
  },
  "nodes": [{"id":..,"nama":..,"pt":..,"degree":..,"betweenness":..,"komunitas":..,"color":..,"x":..,"y":..}],
  "edges": [{"source":..,"target":..,"weight":..,"sources":[..]}],
  "komunitas_list": [{"id":..,"size":..,"pt_dom":..,"color":..}],
  "top_pairs": [...],
  "top_degree": [...],
  "top_betweenness": [...],
  "top_pt": [...]
}
```

#### Hasil Test Run (seluruh sumber, min_bobot=1, max_nodes=500)
| Metrik | Nilai |
|--------|-------|
| Total nodes (full graph) | 6,485 |
| Total edges (full graph) | 10,435 |
| Komunitas terdeteksi | 639 |
| Graph density | 0.000496 |
| Avg degree | 3.22 |
| Waktu komputasi | **9.5 detik** |
| Top pair | ILYAS MASUDIN (UMM) ↔ DIAN PALUPI RESTUPUTRI (UMM): **56×** |

### Backend: `KolaboasiViewSet`

```python
class KolaboasiViewSet(PublicReadAdminWriteMixin, viewsets.ViewSet):
    @action(detail=False, methods=['get'], url_path='graph')
    def graph(self, request):
        # Query params: sumber, min_bobot, max_nodes, rebuild
        # Cek cache → serve atau trigger build_graph()
        ...

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        # Ringkasan stats dari snapshot terbaru
        ...
```

URL terdaftar: `GET /api/sinta-kolaborasi/graph/` dan `GET /api/sinta-kolaborasi/stats/`

### File yang Dibuat / Diubah

| File | Jenis | Keterangan |
|------|-------|------------|
| `apps/universities/models.py` | Ubah | Tambah `KolaboasiSnapshot` |
| `apps/universities/migrations/0022_add_kolaboasi_snapshot.py` | Baru | Migration otomatis |
| `apps/universities/views.py` | Ubah | Import model baru; tambah `KolaboasiViewSet` |
| `apps/universities/urls.py` | Ubah | Daftarkan `sinta-kolaborasi` ke router |
| `utils/sinta/build_kolaboasi_graph.py` | **Baru** | Script builder graf NetworkX |
| `chifoo_frontend/…/sinta-kolaborasi.component.ts` | **Baru** | Komponen Angular visualisasi jaringan |

### Komponen Frontend `sinta-kolaborasi.component.ts`

**Tema:** Ungu `#7c3aed`, icon 🕸️

**Visualisasi utama:** SVG canvas interaktif
- Node radius skala dengan `degree`; warna berdasarkan komunitas Louvain
- Edge width skala dengan `weight`; warna berdasarkan sumber (scopus=amber, penelitian=hijau, pengabdian=biru)
- Hover tooltip node (nama, PT, degree, betweenness, komunitas)
- Klik node → popup profil author (sama seperti halaman Penelitian & Pengabdian)
- Posisi node dari `spring_layout` backend (pre-computed, tidak ada simulasi di frontend)

**Filter bar:** sumber, min_bobot, max_nodes, filter PT

**Panel statistik:**
- 4 stat cards (total nodes, edges, komunitas, density)
- Top pasangan kolaborasi (top_pairs)
- Top 15 nodes by degree
- Top 15 nodes by betweenness centrality
- Daftar komunitas dengan dominansi PT
- Bar chart top PT by total kolaborasi

---

## Topik 13: Menu Top-Level "NetworkX"

### Permintaan
Buat item menu tersendiri sejajar dengan "SINTA" di navigasi utama,
dengan label "NetworkX", yang mengarah ke halaman visualisasi jaringan kolaborasi
(`SintaKolaboasiComponent`).

### Perubahan

#### `app.module.ts`
```typescript
// Import baru
import { SintaKolaboasiComponent } from './components/sinta/sinta-kolaborasi.component';

// Route baru (di dalam children LayoutComponent)
{ path: 'network-x', component: SintaKolaboasiComponent },

// Declarations
SintaKolaboasiComponent,
```

#### `layout.component.ts` — Desktop Nav
```html
<!-- Setelah item SINTA -->
<a routerLink="/network-x" routerLinkActive="active">
  <svg class="nav-icon" viewBox="0 0 24 24" fill="currentColor">
    <path d="M17 12a5 5 0 1 0-4.48 4.97V18h-2v2h2v1h2v-1h2v-2h-2v-1.03..."/>
  </svg>
  <span class="nav-label">NetworkX</span>
</a>
```

#### `layout.component.ts` — Mobile Bottom Tabs
Item "NetworkX" yang sama ditambahkan di tab bar bawah (identik dengan desktop).

### Struktur Navigasi Akhir
```
Dashboard | Pendidikan Tinggi | SINTA | NetworkX
```
- Route: `/network-x`
- Komponen: `SintaKolaboasiComponent`
- Icon: graf jaringan (SVG network/hub icon)
- Tersedia di desktop topbar dan mobile bottom tab bar

---

## Topik 14: Peningkatan Halaman NetworkX — 3D, Tiga Tampilan, Multi-PT Filter

### Perubahan yang Dilakukan

#### 1. Tombol Recreate Filter
Filter Sumber Data, Min. Kolaborasi, dan Tampilkan (max nodes) tidak lagi auto-trigger reload.
Tombol **"↻ Terapkan Filter"** muncul dengan animasi pulse ungu saat komposisi filter berbeda
dari data yang sedang ditampilkan. Kembali ke "✓ Diterapkan" setelah data berhasil dimuat.

Implementasi:
- `loadedSumber`, `loadedMinBobot`, `loadedMaxNodes` — track params yang sudah dimuat
- `filtersDirty: boolean` — getter cek apakah filter berubah
- `applyFilters()` → `loadGraph(false)` — gunakan cache jika ada

#### 2. Visualisasi 3D Interaktif
Graf dirender dalam perspektif 3D penuh menggunakan pure SVG (tanpa library WebGL/Three.js).

**Backend (`build_kolaboasi_graph.py`):**
- `nx.spring_layout(..., dim=3)` — posisi node dalam 3 dimensi
- Koordinat z dinormalisasi ke [0.02, 0.98] dan disimpan ke snapshot

**Frontend:**
- `project3D(x, y, z)` — rotasi matrix (Y-axis → X-axis) + perspective projection
- `projMap: Map<number, ProjPos>` — cache proyeksi agar tidak recompute tiap render
- Depth sort: node jauh di-render lebih dulu (`szB - szA` descending)
- Node radius × scale perspektif (node dekat = lebih besar)
- Drag mouse/touch untuk memutar (`rotX`, `rotY` += dx/dy × 0.006)
- Tombol **↺ Reset** dan **⟳ Auto** (requestAnimationFrame loop)

#### 3. Tiga Pilihan Tampilan

Toggle button di header graph:

| Tombol | Mode | Background | Keterangan |
|--------|------|------------|------------|
| 🌌 3D  | `'3d'` | Gelap `#0f0f1a` | Rotatable 3D, depth effect, drag |
| 🗺️ 2D | `'2d'` | Terang `#f8fafc` | Spring layout flat, label lebih banyak |
| 🏘️ Klaster | `'cluster'` | Putih `#fafafa` | Node dikelompokkan per komunitas Louvain |

Mode **Klaster**: `computeClusterPositions()` menempatkan center komunitas pada lingkaran besar
(radius 39% canvas), node dalam tiap komunitas pada lingkaran kecil di sekitar center.
Lingkaran komunitas digambar transparan dengan label PT dominan.

#### 4. Sparkline Tren Tahunan di Popup Profil Author
Ditambahkan 4 sparkline sebelum tombol "Lihat profil SINTA lengkap":
- 🟠 Artikel Scopus (`jenis='scopus'`, amber)
- 🔵 Artikel G.Scholar (`jenis='gscholar_pub'`, biru)
- 🔬 Penelitian (`jenis='research'`, hijau)
- 🤝 Pengabdian (`jenis='service'`, langit)

Method baru: `trenData()`, `sparkPts()`, `sparkPath()`, `sparkArea()` — identik dengan
implementasi di halaman Penelitian dan Pengabdian.

#### 5. Fix UnicodeEncodeError sumber Pengabdian
**Root cause:** Judul pengabdian mengandung karakter `…` (U+2026). Di server production
dengan locale ASCII, `print()` dalam `build_graph()` raise `UnicodeEncodeError`.

**Fix di `views.py`:**
```python
_old_stdout = sys.stdout
sys.stdout = io.StringIO()
try:
    result = build_graph(...)
finally:
    sys.stdout = _old_stdout
```
Stdout dialihkan ke `StringIO` selama `build_graph()` berjalan — output print diabaikan
(tidak diperlukan di web server context), error encoding tidak terjadi.

**Fix di `build_kolaboasi_graph.py`:**
```python
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
```
Untuk keamanan saat dijalankan via CLI.

#### 6. Multi-PT Filter (Pilih Beberapa PT)
Filter PT diganti dari single `<select>` menjadi **custom dropdown dengan checkbox**:

- Klik trigger button → dropdown terbuka
- Search box untuk cari PT
- Checkbox per PT — bisa pilih banyak sekaligus
- PT yang dipilih tampil sebagai **chips** (tag berwarna ungu) dengan tombol × untuk hapus
- Tombol "Hapus semua" dan "Selesai"
- Klik di luar dropdown → tutup otomatis

**Logika filter:**
- `selectedPts: Set<string>` — set PT yang dipilih
- Jika `selectedPts.size === 0` → tampilkan semua node
- Jika ada PT dipilih → node di luar PT dipilih di-dim (opacity 0.15, warna abu)
- Edge hanya tampil jika **kedua** endpoint berasal dari PT yang dipilih

### File yang Diubah
| File | Perubahan |
|------|-----------|
| `chifoo_frontend/…/sinta-kolaborasi.component.ts` | Semua perubahan di atas |
| `chifoo_backend/apps/universities/views.py` | Fix stdout redirect + import sys |
| `chifoo_backend/utils/sinta/build_kolaboasi_graph.py` | dim=3 spring_layout + stdout reconfigure + koordinat z |
