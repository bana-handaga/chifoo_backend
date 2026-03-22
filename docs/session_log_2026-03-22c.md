# Session Log — Scraping Departemen & Author SINTA

> Tanggal  : 2026-03-22 (sesi ketiga)
> Scope    : Scraping data departemen dan author PTMA dari SINTA
> Repo     : chifoo_backend

---

## A. Latar Belakang

Data SINTA Afiliasi yang sudah ada hanya mencakup ringkasan per PT (`jumlah_departments`, skor agregat).
Pada sesi ini dibangun pipeline scraping lengkap untuk data departemen (program studi) dan author per departemen,
mencakup profil, statistik publikasi, dan tren tahunan.

---

## B. Struktur URL SINTA

| Halaman | URL Format | Keterangan |
|---|---|---|
| Daftar dept per PT | `/affiliations/departments/{sinta_id_pt}/{kode_pt}?page=N` | Pagination 10/halaman |
| Detail dept | `/departments/profile/{sinta_id_pt}/{uuid_pt}/{uuid_dept}` | UUID dari listing |
| Author list dept | `/departments/authors/{sinta_id_pt}/{uuid_pt}/{uuid_dept}?page=N` | Replace `/profile/` → `/authors/` |
| Detail author (default) | `/authors/profile/{sinta_id_author}` | Scopus artikel + kuartil + radar |
| Detail author (penelitian) | `/authors/profile/{sinta_id_author}/?view=researches` | Trend penelitian per tahun |
| Detail author (pengabdian) | `/authors/profile/{sinta_id_author}/?view=services` | Trend pengabdian per tahun |

---

## C. Pipeline Scraping Departemen

### C.1 · Scrape Daftar Departemen (`scrape_sinta_departments.py`)

**Input:** Database → semua `SintaAfiliasi` (154 PT, field `sinta_id` + `sinta_kode`)

**Proses per PT:**
1. Fetch halaman `/affiliations/departments/{sinta_id}/{kode_pt}`
2. Parse tiap `div.row.d-item`:
   - `div.tbl-content-meta span` → jenjang (S1/S2/S3/D3/D4/PRO/SP1)
   - `div.tbl-content-name > a` → nama + url_profil (UUID-based)
   - `div.tbl-content-meta-num` → kode_dept (numerik)
   - `span.profile-id.text-warning` → SINTA Score Overall
   - `span.profile-id.text-success` → SINTA Score 3Yr
   - `ul.au-list.dept-list` → preview authors + "N more" → jumlah_authors
3. Handle pagination (`ul.pagination`)
4. Simpan ke: `utils/sinta/outs/departments/{kode_pt}/departments.json`

**Output per PT (contoh 061008/UMS):**
```json
{
  "sinta_id_afiliasi": "27",
  "kode_pt": "061008",
  "nama_pt": "Universitas Muhammadiyah Surakarta",
  "jumlah_departments": 79,
  "departments": [
    {
      "jenjang": "S1",
      "nama": "Ilmu Gizi",
      "url_profil": "https://sinta.../departments/profile/27/{uuid1}/{uuid2}",
      "kode_dept": "13211",
      "sinta_score_overall": 31161,
      "sinta_score_3year": 25359,
      "jumlah_authors": 16
    }, ...
  ]
}
```

**Hasil:** 154 PT, 2.367 departemen total, 0 error

**Catatan duplikat:** Beberapa PT memiliki dua departemen dengan `kode_dept` yang sama (data identik).
Import script menangani ini dengan mengambil data terakhir (overwrite).

---

### C.2 · Scrape Detail Departemen (`scrape_sinta_dept_detail.py`)

**Input:** `departments.json` per PT → `url_profil` + `kode_dept`

**Proses per departemen:**
1. Fetch `/departments/profile/{sinta_id_pt}/{uuid1}/{uuid2}`
2. Parse:
   - `div.pr-num / div.pr-txt` → 4 SINTA Score (Overall, 3Yr, Productivity, Productivity 3Yr)
   - `div.stat-num / div.stat-text` → jumlah_authors
   - `table.stat-table` → Scopus/GScholar/WOS × artikel + sitasi
   - ECharts `#quartile-pie` → Q1, Q2, Q3, Q4, No-Q (parse JS multiline dengan `value:/name:` regex)
   - ECharts `#research-radar` → conference, articles, others
   - ECharts `#scopus-chart-articles` → trend Scopus per tahun (xAxis + series data)

**Catatan teknis ECharts:**
- Chart ID dicari via `getElementById('{id}')` bukan `id="{id}"` di HTML
- Array data bersifat multiline dengan trailing comma → strip whitespace + hapus `,]` sebelum JSON parse
- Window snippet 10KB dari posisi `getElementById` agar cukup menampung seluruh data array

**Output:** `utils/sinta/outs/departments/{kode_pt}/{kode_pt}_{kode_dept}_deptdetail.json`

```json
{
  "kode_pt": "061008",
  "kode_dept": "13211",
  "url_detail": "https://...",
  "sinta_score_overall": 31161,
  "sinta_score_3year": 25359,
  "sinta_score_productivity": 1948,
  "sinta_score_productivity_3year": 1585,
  "jumlah_authors": 16,
  "scopus_artikel": 80,
  "scopus_sitasi": 12717,
  "gscholar_artikel": 1283,
  "gscholar_sitasi": 21193,
  "wos_artikel": 29,
  "wos_sitasi": 3606,
  "scopus_q1": 31, "scopus_q2": 11, "scopus_q3": 24, "scopus_q4": 13, "scopus_noq": 1,
  "research_conference": 74,
  "research_articles": 5,
  "research_others": 1,
  "trend_scopus": [
    {"tahun": 2013, "jumlah": 3},
    {"tahun": 2019, "jumlah": 5},
    ...
  ]
}
```

**Hasil:** 2.310 di-scrape, 57 dilewati (sudah ada dari test), 0 error

---

### C.3 · Scrape Author List per Departemen (`scrape_sinta_dept_authors.py`)

**Input:** `departments.json` → `url_profil` per dept
**Konstruksi URL:** replace `/departments/profile/` → `/departments/authors/`

**Proses per halaman:**
- Parse `div.au-item`:
  - `div.profile-name > a` → nama + url_profil (contains sinta_id)
  - `img.avatar` → foto_url
  - `div.profile-dept > a` → dept_nama
  - `span.profile-id.text-warning` → Scopus H-Index (regex: `Scopus H-Index : N`)
  - `span.profile-id.text-success` → GS H-Index
  - `div.stat-num / div.stat-text` pairs → sinta_score_3yr, sinta_score, affil_score_3yr, affil_score
- Pagination: `ul.pagination` → loop sampai tidak ada halaman berikutnya

**Output:** `utils/sinta/outs/departments/{kode_pt}/{kode_pt}_{kode_dept}_author_list.json`

```json
{
  "kode_pt": "061008",
  "kode_dept": "13211",
  "url_authors": "https://...",
  "jumlah_authors": 16,
  "authors": [
    {
      "sinta_id": "6103375",
      "nama": "AAN SOFYAN",
      "url_profil": "https://sinta.kemdiktisaintek.go.id/authors/profile/6103375",
      "foto_url": "https://scholar.googleusercontent.com/...",
      "dept_nama": "Ilmu Gizi (S1)",
      "scopus_hindex": 3,
      "gs_hindex": 8,
      "sinta_score_3yr": 954,
      "sinta_score": 1742,
      "affil_score_3yr": 1138,
      "affil_score": 2047
    }, ...
  ]
}
```

**Hasil:** 2.312 di-scrape, 55 dilewati, 0 error, total ~18.500+ author records

---

## D. Rancangan Database Author (Belum Diimplementasi)

### D.1 · Model `SintaAuthor` — profil utama (1 row per author)

| Field | Tipe | Keterangan |
|---|---|---|
| `sinta_id` | CharField unique | ID author di SINTA |
| `nama` | CharField | Nama lengkap |
| `url_profil` | URLField | Link ke profil SINTA |
| `foto_url` | URLField | Google Scholar atau default |
| `bidang_keilmuan` | JSONField | List tag keahlian |
| `afiliasi` | FK → SintaAfiliasi | PT induk (redundan tapi cepat) |
| `departemen` | FK → SintaDepartemen | Prodi (nullable) |
| `sinta_score_overall` | BigIntegerField | — |
| `sinta_score_3year` | BigIntegerField | — |
| `affil_score` | BigIntegerField | — |
| `affil_score_3year` | BigIntegerField | — |
| `scopus_artikel` | IntegerField | — |
| `scopus_sitasi` | IntegerField | — |
| `scopus_cited_doc` | IntegerField | — |
| `scopus_h_index` | SmallIntegerField | — |
| `scopus_i10_index` | SmallIntegerField | — |
| `scopus_g_index` | SmallIntegerField | — |
| `gscholar_artikel` | IntegerField | — |
| `gscholar_sitasi` | IntegerField | — |
| `gscholar_cited_doc` | IntegerField | — |
| `gscholar_h_index` | SmallIntegerField | — |
| `gscholar_i10_index` | SmallIntegerField | — |
| `gscholar_g_index` | SmallIntegerField | — |
| `wos_artikel` | IntegerField | — |
| `wos_sitasi` | IntegerField | — |
| `wos_cited_doc` | IntegerField | — |
| `wos_h_index` | SmallIntegerField | — |
| `scopus_q1..q4, noq` | PositiveIntegerField ×5 | Distribusi kuartil |
| `research_conference` | IntegerField | Breakdown research radar |
| `research_articles` | IntegerField | — |
| `research_others` | IntegerField | — |
| `scraped_at` | DateTimeField auto_now | — |

### D.2 · Model `SintaAuthorTrend` — tren tahunan (terpisah)

| Field | Tipe | Keterangan |
|---|---|---|
| `author` | FK → SintaAuthor CASCADE | — |
| `jenis` | CharField choices | `scopus` / `research` / `service` |
| `tahun` | PositiveSmallIntegerField | — |
| `jumlah` | PositiveIntegerField | — |

`unique_together: (author, jenis, tahun)`

Estimasi: ~15 tahun × 3 jenis × 18.500 authors ≈ **830K rows** (hanya tahun dengan jumlah > 0)

### D.3 · Alasan desain

- Statistik flat di `SintaAuthor` (bukan tabel terpisah) → query author + stats = 1 tabel
- `bidang_keilmuan` sebagai JSONField → cukup untuk tampilan, tidak perlu filter kompleks
- FK ke `SintaAfiliasi` meski redundan → query "semua author PT X" tanpa JOIN ke dept
- Tren dipisah → jumlah tahun variabel, efisien storage

---

## E. Scraper Author Detail (`scrape_sinta_author_detail.py`)

### E.1 · Struktur

**Input:** Semua `*_author_list.json` → deduplikasi by `sinta_id` → **17.861 author unik**

**3 request per author:**
1. `GET /authors/profile/{sinta_id}` → identitas, 4 scores, stat-table, kuartil, radar, trend Scopus
2. `GET /authors/profile/{sinta_id}/?view=researches` → trend penelitian per tahun
3. `GET /authors/profile/{sinta_id}/?view=services` → trend pengabdian per tahun

**Output:** `utils/sinta/outs/authors/{sinta_id}_authordetail.json`

```json
{
  "sinta_id": "5985149",
  "url_profil": "https://sinta.kemdiktisaintek.go.id/authors/profile/5985149",
  "nama": "AGUS SETIAWAN",
  "foto_url": "https://scholar.googleusercontent.com/...",
  "sinta_id_pt": "27",
  "kode_dept": "13211",
  "bidang_keilmuan": ["Ilmu Gizi", "Kesehatan Masyarakat"],
  "sinta_score_overall": 1742,
  "sinta_score_3year": 954,
  "affil_score": 2047,
  "affil_score_3year": 1138,
  "scopus_artikel": 12, "scopus_sitasi": 145, "scopus_cited_doc": 10,
  "scopus_h_index": 5, "scopus_i10_index": 3, "scopus_g_index": 7,
  "gscholar_artikel": 87, "gscholar_sitasi": 612, "gscholar_cited_doc": 45,
  "gscholar_h_index": 8, "gscholar_i10_index": 6, "gscholar_g_index": 12,
  "wos_artikel": 2, "wos_sitasi": 18,
  "scopus_q1": 3, "scopus_q2": 2, "scopus_q3": 5, "scopus_q4": 1, "scopus_noq": 1,
  "research_conference": 5, "research_articles": 7, "research_others": 0,
  "trend_scopus":   [{"tahun": 2018, "jumlah": 2}, ...],
  "trend_research": [{"tahun": 2015, "jumlah": 3}, ...],
  "trend_service":  [{"tahun": 2016, "jumlah": 1}, ...]
}
```

### E.2 · Konfigurasi delay

| Parameter | Nilai | Keterangan |
|---|---|---|
| `DELAY` | 1.0 s | Jeda antar request dalam satu author |
| `DELAY_NEXT` | 0.8 s | Jeda sebelum author berikutnya |
| Total per author | ~3.3 s | 3 req × 1.0s + 0.8s overhead |
| Estimasi total | ~8–10 jam | 17.861 author |

### E.3 · Catatan teknis

- Server error 500 pada satu request (mis. `?view=researches`) ditangani gracefully: author tetap disimpan, field trend yang gagal dikosongkan
- Scrape bersifat resumable: jika file sudah ada dan `--force` tidak diberikan, author dilewati
- Jalankan di background: `nohup python -u utils/sinta/scrape_sinta_author_detail.py > /tmp/scrape_author_detail.log 2>&1 &`
- Monitor: `tail -f /tmp/scrape_author_detail.log` atau `python ... --status`

---

## F. Model Django SintaAuthor + SintaAuthorTrend

### F.1 · Model `SintaAuthor` (migration 0013)

| Field | Tipe | Keterangan |
|---|---|---|
| `sinta_id` | CharField unique | ID author di SINTA |
| `nama` | CharField | Nama lengkap |
| `url_profil` | URLField | Link ke profil SINTA |
| `foto_url` | URLField | Google Scholar atau default |
| `bidang_keilmuan` | JSONField | List tag keahlian |
| `afiliasi` | FK → SintaAfiliasi SET_NULL | PT induk (nullable) |
| `departemen` | FK → SintaDepartemen SET_NULL | Prodi (nullable) |
| `sinta_score_overall` | BigIntegerField | — |
| `sinta_score_3year` | BigIntegerField | — |
| `affil_score` | BigIntegerField | — |
| `affil_score_3year` | BigIntegerField | — |
| `scopus_artikel..g_index` | Int/SmallInt × 6 | Scopus stats |
| `gscholar_artikel..g_index` | Int/SmallInt × 6 | GScholar stats |
| `wos_artikel..g_index` | Int/SmallInt × 6 | WOS stats |
| `scopus_q1..noq` | PositiveIntegerField × 5 | Distribusi kuartil |
| `research_conference/articles/others` | IntegerField × 3 | Research radar |
| `scraped_at` | DateTimeField auto_now | — |

### F.2 · Model `SintaAuthorTrend`

| Field | Tipe | Keterangan |
|---|---|---|
| `author` | FK → SintaAuthor CASCADE | — |
| `jenis` | CharField choices | `scopus` / `research` / `service` |
| `tahun` | PositiveSmallIntegerField | — |
| `jumlah` | PositiveIntegerField | — |

`unique_together: (author, jenis, tahun)`

Estimasi: ~15 tahun × 3 jenis × 17.861 authors ≈ **~800K rows** (hanya tahun dengan jumlah > 0)

### F.3 · Alasan desain

- FK ke `SintaAfiliasi` meski bisa di-derive dari `departemen` → query "semua author PT X" tanpa JOIN ganda
- `bidang_keilmuan` sebagai JSONField → cukup untuk tampilan, tidak perlu filter kompleks
- Trend dipisah ke `SintaAuthorTrend` → jumlah tahun variabel, efisien storage
- `SET_NULL` pada FK → jika PT/dept dihapus, data author tidak ikut hilang

---

## G. Import Script `sp_import_sinta_authors.py`

**Input:** `utils/sinta/outs/authors/*_authordetail.json`

**Strategi:**
- `SintaAuthor`: `update_or_create` by `sinta_id` → aman re-run
- `SintaAuthorTrend`: hapus & insert ulang per author
- Relasi `afiliasi`: lookup via `sinta_id_pt` dari field JSON → match ke `SintaAfiliasi.sinta_id`
- Relasi `departemen`: lookup via `(kode_pt, kode_dept)` → preloaded dict untuk efisiensi

**Optimasi:** Preload semua 2.315 departemen + 155 PT ke dict sebelum loop → O(1) lookup per author

**Hasil tes (5 file):** 5 author + 78 trend rows, semua linked ke PT & departemen

---

## H. API Endpoint `sinta-author`

**Endpoint:** `GET /api/sinta-author/`

| Action | URL | Keterangan |
|---|---|---|
| List | `GET /api/sinta-author/` | Serializer ringkas |
| Detail | `GET /api/sinta-author/{id}/` | Lengkap + trend |
| Stats | `GET /api/sinta-author/stats/` | Agregat seluruh PTMA |

**Filter:** `afiliasi__sinta_kode`, `departemen`, `departemen__kode_dept`
**Search:** `nama`, `bidang_keilmuan`
**Ordering:** `sinta_score_overall`, `sinta_score_3year`, `scopus_artikel`, `scopus_h_index`

---

## I. Status per Komponen

| Komponen | Script | Status |
|---|---|---|
| Daftar departemen | `scrape_sinta_departments.py` | ✅ Selesai (154 PT, 2367 dept) |
| Import dept ke DB | `sp_import_sinta_departments.py` | ✅ 2315 rows |
| Detail departemen | `scrape_sinta_dept_detail.py` | ✅ Selesai (2367 file) |
| Author list per dept | `scrape_sinta_dept_authors.py` | ✅ Selesai (2312 file, ~18.5K authors) |
| Model SintaDepartemen | `apps/universities/models.py` | ✅ Migrasi 0012 |
| API sinta-departemen | `apps/universities/views.py` | ✅ `/api/sinta-departemen/` |
| Scraper author detail | `scrape_sinta_author_detail.py` | 🔄 Berjalan (~246/17.861, PID 360195) |
| Model SintaAuthor + Trend | `apps/universities/models.py` | ✅ Migrasi 0013 |
| Import script author | `sp_import_sinta_authors.py` | ✅ Siap (test 5 file OK) |
| API sinta-author | `apps/universities/views.py` | ✅ `/api/sinta-author/` |
| Import penuh author ke DB | — | ⏳ Tunggu scrape selesai |
| Frontend halaman Departemen | — | ⏳ Pending |
| Frontend halaman Author | — | ⏳ Pending |

---

## J. Kendala & Solusi

| Kendala | Penyebab | Solusi |
|---|---|---|
| ECharts data tidak ter-parse | `_extract_echarts_series` mencari `'{id}'` → menemukan HTML div bukan JS init | Cari `getElementById('{id}')` sebagai anchor |
| Array ECharts tidak ter-parse | Trailing comma sebelum `]` dalam multiline array | Regex `re.sub(r",\]", "]", ...)` sebelum json.loads |
| Window snippet terlalu kecil | `idx+3000` tidak cukup menampung array 16 tahun yang pretty-printed | Naikkan ke `idx+10000` |
| Duplicate kode_dept dalam satu PT | SINTA kadang mendaftarkan prodi yang sama dua kali | Import script: data terakhir menimpa (overwrite) |
| IntegrityError bulk_create | Duplicate entry dari JSON yang sama | `ignore_conflicts=True` + dedup before insert |
| Author list scraper nama file berubah | User minta format `{kode_pt}_{kode_dept}_author_list.json` | Update output path di scraper |
| Server 500 pada `?view=researches` | SINTA intermittently error pada beberapa author | Tangani gracefully: author tetap disimpan tanpa trend |
