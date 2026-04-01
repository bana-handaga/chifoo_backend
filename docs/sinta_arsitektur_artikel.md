# Arsitektur Data Artikel SINTA — Desain, Keputusan, dan Technical Debt

**Tanggal dibuat:** 2026-04-01  
**Konteks:** Diskusi desain saat menambahkan fitur sync afiliasi GScholar

---

## 1. Latar Belakang

SINTA menampilkan daftar artikel ilmiah di **tiga konteks berbeda**:

| Konteks | URL SINTA | Keterangan |
|---|---|---|
| **Author** | `/authors/profile/{sinta_id}/?view=googlescholar` | Artikel per dosen/peneliti |
| **Departemen** | `/departments/profile/{dept_id}/...` | Artikel per program studi |
| **Afiliasi** | `/affiliations/profile/{sinta_id}/?view=googlescholar` | Artikel per perguruan tinggi |

Secara konseptual, artikel yang muncul di ketiga halaman tersebut **merujuk dokumen yang sama** — sebuah paper ditulis oleh seorang author, yang bekerja di suatu departemen, yang bernaung di bawah suatu afiliasi.

Pertanyaan yang muncul: **Haruskah data artikel ini disatukan dalam satu tabel yang sama?**

---

## 2. Model yang Saat Ini Ada

### 2.1 SintaScopusArtikel + SintaScopusArtikelAuthor

```
SintaScopusArtikel              (28.569 baris per 2026-04-01)
  eid           → Scopus EID unik global (contoh: 2-s2.0-85018240220)
  judul, tahun, sitasi, kuartil, jurnal_nama, jurnal_url, scopus_url
  scraped_at

SintaScopusArtikelAuthor        (41.911 baris per 2026-04-01)
  artikel       → FK ke SintaScopusArtikel
  author        → FK ke SintaAuthor
  urutan_penulis, total_penulis, nama_singkat
```

**Sumber scraping:** `/authors/profile/{sinta_id}/?view=scopus` per author.  
**Deduplication:** menggunakan `eid` (Scopus Electronic Identifier) yang **unik secara global**.  
Satu artikel yang ditulis oleh 3 author PTMA hanya muncul **satu baris** di `SintaScopusArtikel`, 
dan **tiga baris** di `SintaScopusArtikelAuthor`.

---

### 2.2 SintaAuthorPublication

```
SintaAuthorPublication          (941 baris per 2026-04-01)
  author        → FK ke SintaAuthor
  sumber        → 'gscholar' | 'scopus' | 'wos'
  pub_id        → URL artikel atau ID ad-hoc
  judul, penulis, jurnal, tahun, sitasi, url
  scraped_at
  unique_together: (author, sumber, pub_id)
```

**Sumber scraping:** `/authors/profile/{sinta_id}/?view=googlescholar` per author.  
**Isi saat ini:** Sebagian besar `sumber='gscholar'` — 10 artikel GScholar terbaru per author,  
diisi saat tombol **Sync Author** ditekan (bukan batch sync rutin).

---

### 2.3 SintaAfiliasiGScholarArtikel  *(baru, 2026-04-01)*

```
SintaAfiliasiGScholarArtikel    (0 baris — belum ada sync)
  afiliasi      → FK ke SintaAfiliasi
  pub_id        → URL artikel atau ID ad-hoc
  judul, penulis, jurnal, tahun, sitasi, url
  scraped_at
  unique_together: (afiliasi, pub_id)
  Hanya menyimpan artikel 2 tahun terakhir
```

**Sumber scraping:** `/affiliations/profile/{sinta_id}/?view=googlescholar` per PT.  
**Diisi oleh:** `sync_sinta_afiliasi_runner.py`.

---

### 2.4 SintaTrendTahunan (afiliasi)

```
SintaTrendTahunan
  afiliasi      → FK ke SintaAfiliasi
  jenis         → 'scopus' | 'research' | 'service' | 'gs_pub' | 'gs_cite'
  tahun, jumlah
  unique_together: (afiliasi, jenis, tahun)
```

Menyimpan **agregat tahunan** (bukan detail artikel). `gs_pub` dan `gs_cite` ditambahkan
bersamaan dengan `SintaAfiliasiGScholarArtikel`.

---

## 3. Mengapa Tidak Disatukan?

### 3.1 Scopus vs Google Scholar: Kualitas Identifier Berbeda

| | Scopus | Google Scholar |
|---|---|---|
| **Identifier** | EID (`2-s2.0-*`) — **unik global** | URL artikel GScholar atau ad-hoc — **tidak unik antar konteks** |
| **Deduplication** | Mudah dan andal | Sulit/tidak mungkin tanpa title matching |
| **Metadata** | Terstandarisasi (kuartil, DOI, jurnal resmi) | Bervariasi (bisa berbeda scrape ke scrape) |

Artikel Scopus yang sama dapat diidentifikasi dengan pasti di halaman author, departemen, maupun afiliasi — EID-nya sama. Karena itu `SintaScopusArtikel` sudah benar didesain sebagai tabel terpusat dengan relasi M2M ke author.

Google Scholar **tidak memiliki ID global yang reliabel**. URL yang muncul di halaman author bisa berbeda dengan URL di halaman afiliasi untuk artikel yang sama. Menggabungkan keduanya ke satu tabel hanya memindahkan masalah deduplication tanpa menyelesaikannya.

### 3.2 Scope Scraping Berbeda

| Sumber | Scope | Trigger |
|---|---|---|
| `SintaAuthorPublication` (gscholar) | 10 artikel terbaru per author | Tombol Sync Author |
| `SintaAfiliasiGScholarArtikel` | Semua artikel 2 tahun terakhir per PT | `sync_sinta_afiliasi_runner` |

Menggabungkan keduanya berarti harus mengelola kondisi: "artikel ini ada karena scrape author" vs "artikel ini ada karena scrape afiliasi", yang menambah kompleksitas tanpa manfaat nyata untuk use-case yang ada.

### 3.3 Beban Migrasi Tidak Sebanding Manfaatnya

Penyatuan tabel GScholar akan membutuhkan:
- Migration besar (rename + struktur M2M baru)
- Update semua endpoint API yang melayani data artikel
- Update semua runner dan scraper
- Pengujian ulang menyeluruh

Sementara data GScholar di dua konteks (author vs afiliasi) **tidak dikonsumsi bersama** di frontend — tampilan popup author berbeda dari tampilan popup afiliasi.

---

## 4. Desain Ideal (Future Reference)

Jika suatu saat deduplication GScholar menjadi kebutuhan nyata (misal: ingin menghitung total artikel unik PT dari hasil gabungan semua author), desain yang disarankan:

```
SintaArtikelGScholar            ← satu tabel artikel GScholar unik
  title_hash    → SHA256 dari judul ternormalisasi (sebagai surrogate key)
  judul, jurnal, tahun, sitasi, url
  scraped_at

SintaArtikelGScholarKonteks     ← dari mana artikel ini ditemukan
  artikel       → FK ke SintaArtikelGScholar
  konteks       → 'author' | 'afiliasi' | 'departemen'
  ref_id        → sinta_id dari konteks yang bersangkutan
  pub_id_asal   → URL/ID asli dari sumber scrape
```

Deduplication dilakukan dengan fuzzy title matching atau title hash, bukan ID.  
**Ini belum diimplementasikan dan tidak mendesak.**

---

## 5. Ringkasan Keputusan Arsitektur

| Keputusan | Alasan |
|---|---|
| **Scopus: satu tabel terpusat** (`SintaScopusArtikel` + M2M) | EID unik global memungkinkan dedup yang andal |
| **GScholar: tabel terpisah per konteks** | Tidak ada ID global yang reliabel; scope scraping berbeda |
| **Tidak menggabungkan GScholar author + afiliasi** | Manfaat minimal, beban migrasi besar, frontend tidak butuh gabungan |
| **Tren tahunan GScholar: di `SintaTrendTahunan`** | Cukup sebagai agregat; jenis `gs_pub` / `gs_cite` ditambahkan |

---

## 6. File yang Relevan

| File | Keterangan |
|---|---|
| `apps/universities/models.py` | Semua model: `SintaScopusArtikel`, `SintaScopusArtikelAuthor`, `SintaAuthorPublication`, `SintaAfiliasiGScholarArtikel`, `SintaTrendTahunan` |
| `utils/sinta/sync_sinta_author_runner.py` | Scrape GScholar artikel per author → `SintaAuthorPublication` |
| `utils/sinta/sync_sinta_afiliasi_runner.py` | Scrape GScholar artikel per PT → `SintaAfiliasiGScholarArtikel` + `SintaTrendTahunan` |
| `utils/sinta/scrape_sinta_scopus_articles.py` | Scrape Scopus artikel per author (lama, file-based) |
| `utils/sinta/sp_import_sinta_scopus_articles.py` | Import hasil scrape Scopus dari JSON ke `SintaScopusArtikel` |
| `apps/universities/migrations/0028_sinta_afiliasi_gscholar.py` | Migration yang membuat `SintaAfiliasiGScholarArtikel` dan menambah choices GScholar ke `SintaTrendTahunan` |
