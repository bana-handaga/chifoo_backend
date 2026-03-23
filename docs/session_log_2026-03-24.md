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
