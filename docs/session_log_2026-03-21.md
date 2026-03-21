# Session Log — 21 Maret 2026

**Proyek:** chifoo_backend (Django DRF)
**Fokus:** Scrape data afiliasi SINTA untuk 162 Perguruan Tinggi Muhammadiyah/Aisyiyah (PTMA)

---

## Ringkasan Aktivitas

Sesi ini melanjutkan pekerjaan scraping data SINTA afiliasi dari sesi-sesi sebelumnya.
Pekerjaan utama mencakup penyelesaian scrape tiga jenis data tridharma (publikasi, penelitian, pengabdian)
dan pendokumentasian hasilnya.

---

## 1. Data Publikasi Scopus Tahunan (`?view=` default)

**Status:** Sudah selesai di sesi sebelumnya, sesi ini hanya mendokumentasikan hasilnya.

### Output
- **138 file** di `utils/sinta/outs/publications/{kode}_pubhistory.json`
- Ringkasan: `utils/sinta/outs/sinta_scrape_publications.md`

### Statistik
| Metrik | Nilai |
|---|---|
| PT dengan data | 138 / 162 |
| Rentang tahun | 2011 – 2026 |
| Total publikasi (2011–2025) | 35,250 |
| Puncak tahunan | 5,476 (2024) |
| Top PT | UMY (4,575), UMS (4,310), UAD (3,917) |

### Teknik Ekstraksi
- Chart: `id="scopus-chart-articles"` — eCharts inline JS
- Block size: 5000 chars (3000 tidak cukup untuk array series)

---

## 2. Data Penelitian (Researches) Tahunan (`?view=researches`)

**Script baru:** `utils/sinta/scrape_sinta_researches.py`

### Output
- **158 file** di `utils/sinta/outs/researches/{kode}_research.json`
- Ringkasan: `utils/sinta/outs/sinta_scrape_researches.md`

### Struktur JSON
```json
{
  "kode_pt": "061008",
  "sinta_id": "27",
  "nama": "Universitas Muhammadiyah Surakarta",
  "research_radar": {
    "article": 2676,
    "conference": 1512,
    "others": 162
  },
  "research_history": {
    "2013": 54,
    "2014": 68,
    "...": "...",
    "2024": 1518
  },
  "scraped_at": "2026-03-21 19:39:20"
}
```

### Statistik
| Metrik | Nilai |
|---|---|
| PT dengan data | 138 / 162 |
| Rentang tahun | 2006 – 2026 |
| Total penelitian (2011–2025) | 81,211 |
| Puncak tahunan | 15,169 (2023) |
| Radar global | Article 66%, Conference 30%, Others 4% |
| Top PT | UMM (7,620), UM Surabaya (7,325), UMS (6,815) |

### Teknik Ekstraksi
- Chart 1: `id="research-radar"` → breakdown Article/Conference/Others
- Chart 2: `id="research-chart-articles"` → tren tahunan
- Halaman berbeda dari default: `?view=researches`

---

## 3. Data Pengabdian Masyarakat (Services) Tahunan (`?view=services`)

**Script baru:** `utils/sinta/scrape_sinta_services.py`

### Output
- **158 file** di `utils/sinta/outs/services/{kode}_service.json`
- Ringkasan: `utils/sinta/outs/sinta_scrape_services.md`

### Struktur JSON
```json
{
  "kode_pt": "061008",
  "sinta_id": "27",
  "nama": "Universitas Muhammadiyah Surakarta",
  "service_history": {
    "2015": 201,
    "2016": 127,
    "...": "...",
    "2024": 2280
  },
  "scraped_at": "2026-03-21 20:00:00"
}
```

### Statistik
| Metrik | Nilai |
|---|---|
| PT dengan data | 123 / 162 |
| Rentang tahun | 2006 – 2026 |
| Total pengabdian (2006–2025) | 86,040 |
| Puncak tahunan | 22,582 (2024) |
| Top PT | UM Sidoarjo (20,982), UM Surabaya (11,342), UMS (9,797) |

### Catatan Teknis
- Halaman `?view=services` **tidak memiliki radar chart** (berbeda dengan researches)
- Hanya satu chart: `id="service-chart-articles"`

---

## 4. Perbandingan Tridharma PTMA (2024)

| Jenis Output | Total 2024 | Rasio vs Scopus |
|---|---:|---:|
| Scopus Publikasi | 5,476 | 1× |
| Penelitian (Researches) | 12,711 | 2.3× |
| Pengabdian (Services) | 22,582 | 4.1× |

> Pengabdian masyarakat merupakan output tridharma terbanyak di SINTA untuk PTMA.

---

## 5. WCU Analysis — Paper per Subject per Year

**Script baru:** `utils/sinta/scrape_sinta_wcu.py`

### Output
- **158 file** di `utils/sinta/outs/wcu/{kode}_wcu.json`
- Ringkasan: `utils/sinta/outs/sinta_scrape_wcu.md`

### Struktur JSON
```json
{
  "kode_pt": "061008",
  "sinta_id": "27",
  "nama": "Universitas Muhammadiyah Surakarta",
  "paper_per_subject": {
    "arts_humanities":           {"2014": 2, "2015": 1, "...": "..."},
    "engineering_technology":    {"2014": 21, "...": "..."},
    "life_sciences_medicine":    {"...": "..."},
    "natural_sciences":          {"...": "..."},
    "social_sciences_management":{"...": "..."},
    "overall":                   {"2014": 30, "...", "2023": 52}
  },
  "scraped_at": "2026-03-21 20:20:10"
}
```

### Statistik
| Metrik | Nilai |
|---|---|
| PT dengan data Scival | **8** / 162 |
| Rentang tahun | 2014 – 2023 |
| Sumber data | Scival (Elsevier) |
| Top PT | UMY (1,971), UAD (1,905), UMS (1,412) |

### Bug Fix
- `getElementById('wcu_research_output1')` — salah, mengarah ke blok inisialisasi DOM (atas halaman, tanpa data)
- Fix: cari `option_wcu_research_output1\s*=\s*\{` — muncul lebih bawah bersama data aktual chart

---

## 6. Klasterisasi PT SINTA 2026 (`?view=matricscluster2026`)

**Script baru:** `utils/sinta/scrape_sinta_cluster.py`

### Output
- **158 file** di `utils/sinta/outs/cluster/{kode}_cluster.json`
- Ringkasan: `utils/sinta/outs/sinta_scrape_cluster.md`

### Struktur JSON
```json
{
  "kode_pt": "061008",
  "cluster_name": "Cluster Mandiri",
  "total_score": 42.17,
  "scores": {
    "publication":       {"total_raw": 1150.66, "total_ternormal": 64.76, "total_weighted": 16.19},
    "hki":               {"...": "..."},
    "kelembagaan":       {"...": "..."},
    "research":          {"...": "..."},
    "community_service": {"...": "..."},
    "sdm":               {"total_raw": 1.83, "total_ternormal": 74.94, "total_weighted": 11.24}
  },
  "items": {
    "AI1": {"section": "publication", "name": "ARTIKEL JURNAL INTERNASIONAL Q1", "weight": 40, "value": 0.301, "total": 12.047},
    "...": "..."
  }
}
```

### Statistik
| Cluster | Jumlah PT |
|---|---:|
| Cluster Mandiri | 5 |
| Cluster Utama | 28 |
| Cluster Madya | 27 |
| Cluster Pratama | 47 |
| Belum terklaster | 51 |

### Catatan Teknis
- Format angka Indonesia: `1.234,56` → `parse_id_number()` → `1234.56`
- 67 item kode per PT (AI1, AN1–AN6, KI1–KI9, APS1, JO1–JO6, P1, PM1, DOS1, dst.)
- Kode valid: regex `^[A-Z]{1,4}\d{1,3}$` untuk filter baris non-data

---

## 7. Database Schema — Model Baru

**Migration:** `universities/0009_sintacluster_sintawcutahunan_sintatrendtahunan_and_more.py`

| Model | Tabel | Keterangan |
|---|---|---|
| `SintaTrendTahunan` | `universities_sintatrendtahunan` | Tren tahunan unified (scopus/research/service) + radar research |
| `SintaWcuTahunan` | `universities_sintawcutahunan` | Paper per 5 subject Scival per tahun |
| `SintaCluster` | `universities_sintacluster` | Klasterisasi: nama cluster + 6 skor kategori |
| `SintaClusterItem` | `universities_sintaclusteritem` | 67 item kode per PT |

### SintaTrendTahunan
- `jenis` TextChoices: `scopus` / `research` / `service`
- `unique_together`: `(afiliasi, jenis, tahun)`
- Field radar khusus jenis=research: `research_article`, `research_conference`, `research_others`

### SintaCluster
- OneToOne ke `SintaAfiliasi`
- Fields weighted score: `score_publication` (25%), `score_hki` (10%), `score_kelembagaan` (15%), `score_research` (15%), `score_community_service` (15%), `score_sdm` (15%)
- Fields ternormal score: `ternormal_*` (6 field)
- Ordered by `-total_score`

---

## 8. Import ke Database

**Script import:**
- `utils/sinta/sp_import_sinta_trend.py` — import publications/research/services → `SintaTrendTahunan`
- `utils/sinta/sp_import_sinta_wcu.py` — import WCU → `SintaWcuTahunan`
- `utils/sinta/sp_import_sinta_cluster.py` — import cluster → `SintaCluster` + `SintaClusterItem`

### Hasil Import
| Script | Rows Created | Keterangan |
|---|---:|---|
| `sp_import_sinta_trend.py` | **4,651** | scopus: 2,176 · research: 1,425 · service: 1,050 |
| `sp_import_sinta_cluster.py` | **106** SintaCluster + ~7,100 SintaClusterItem | 51 PT tanpa cluster |
| `sp_import_sinta_wcu.py` | **104** | 8 PT × 13 tahun |

2 PT skip (kode 171018 & 173136 — tidak ada `SintaAfiliasi` di DB).

---

## 9. Jurnal SINTA per PT

**Script baru:** `utils/sinta/scrape_sinta_journals.py`
**Import:** `utils/sinta/sp_import_sinta_journals.py`

### Teknik Ekstraksi

- Halaman listing: `journals/index/{sinta_id}?page={n}` — paginasi 10 jurnal/halaman
- Logo: dari `img src` Google Scholar (`scholar.googleusercontent.com`) — perlu `User-Agent` + `Referer: https://scholar.google.com/`
- `scholar_user_id` diambil dari class div wrapper logo atau dari `url_scholar`
- Jurnal tanpa Google Scholar → `logo_base64 = ""` (fallback ke default SINTA)
- Tidak butuh login SINTA

### Statistik Scrape

| Metrik | Nilai |
|---|---|
| PT dengan jurnal | **88** / 162 |
| Total jurnal | **1,018** |
| Dengan logo | **831** (81.6%) |
| File output | 158 file |

### Distribusi Akreditasi

| S1 | S2 | S3 | S4 | S5 | S6 |
|---:|---:|---:|---:|---:|---:|
| 21 | 89 | 211 | 352 | 318 | 27 |

### Import ke DB

```
SintaJurnal — migration: 0010_sintajurnal.py
```

---

## 10. Struktur File Output Lengkap

```
utils/sinta/
├── scrape_sinta_afiliasi.py       # Scraper profil + publikasi Scopus
├── scrape_sinta_researches.py     # Scraper penelitian
├── scrape_sinta_services.py       # Scraper pengabdian
├── scrape_sinta_wcu.py            # Scraper WCU Scival
├── scrape_sinta_cluster.py        # Scraper klasterisasi 2026
├── scrape_sinta_journals.py       # Scraper jurnal per PT (BARU)
├── sp_import_sinta_afiliasi.py    # Import profil → DB
├── sp_import_sinta_trend.py       # Import trend tahunan → DB
├── sp_import_sinta_wcu.py         # Import WCU → DB
├── sp_import_sinta_cluster.py     # Import klasterisasi → DB
├── sp_import_sinta_journals.py    # Import jurnal → DB (BARU)
└── outs/
    ├── sinta_afiliasi.json              # Gabungan semua profil (162 PT)
    ├── sinta_scrape_publications.md     # Ringkasan scrape publikasi
    ├── sinta_scrape_researches.md       # Ringkasan scrape penelitian
    ├── sinta_scrape_services.md         # Ringkasan scrape pengabdian
    ├── sinta_scrape_wcu.md              # Ringkasan scrape WCU
    ├── sinta_scrape_cluster.md          # Ringkasan scrape klasterisasi
    ├── sinta_scrape_journals.md         # Ringkasan scrape jurnal (BARU)
    ├── affprofile/                      # 162 file profil individual
    │   └── {kode}_sinta_afiliasi.json
    ├── publications/                    # 138 file publikasi Scopus tahunan
    │   └── {kode}_pubhistory.json
    ├── researches/                      # 158 file penelitian tahunan
    │   └── {kode}_research.json
    ├── services/                        # 158 file pengabdian tahunan
    │   └── {kode}_service.json
    ├── wcu/                             # 158 file WCU (8 dengan data)
    │   └── {kode}_wcu.json
    ├── cluster/                         # 158 file klasterisasi (107 dengan data)
    │   └── {kode}_cluster.json
    └── journals/                        # 158 file jurnal (88 dengan data) (BARU)
        └── {kode}_journals.json
```

---

## 11. Model Database (Status Akhir)

| Model | Migration | Record di DB |
|---|---|---|
| `SintaAfiliasi` | 0008 | 156 |
| `SintaTrendTahunan` | 0009 | 4,651 |
| `SintaWcuTahunan` | 0009 | 104 |
| `SintaCluster` | 0009 | 106 |
| `SintaClusterItem` | 0009 | ~7,100 |
| `SintaJurnal` | 0010 | **976** |

---

## 12. Pekerjaan Berikutnya (Backlog)

- [x] API endpoint DRF — jurnal per PT (`SintaJurnal`) ← selesai di seksi 14
- [x] Halaman frontend Jurnal SINTA ← selesai di seksi 14–16
- [ ] API endpoint DRF — tren tridharma per PT (`SintaTrendTahunan`)
- [ ] API endpoint DRF — ranking klasterisasi (`SintaCluster`)
- [ ] API endpoint DRF — WCU bidang keilmuan (`SintaWcuTahunan`)
- [ ] Analisis korelasi: cluster score vs Scopus score
- [ ] Analisis bidang unggulan: engineering vs social per PT (dari data WCU)
- [ ] Scrape logo universitas (base64) — dokumentasi ada di `docs/sinta_scrape_afiliasi.md` §5.4

---

## 13. Referensi

| Dokumen | Path |
|---|---|
| Dokumentasi scraping SINTA | `docs/sinta_scrape_afiliasi.md` |
| Ringkasan publikasi | `utils/sinta/outs/sinta_scrape_publications.md` |
| Ringkasan penelitian | `utils/sinta/outs/sinta_scrape_researches.md` |
| Ringkasan pengabdian | `utils/sinta/outs/sinta_scrape_services.md` |
| Ringkasan WCU | `utils/sinta/outs/sinta_scrape_wcu.md` |
| Ringkasan klasterisasi | `utils/sinta/outs/sinta_scrape_cluster.md` |
| Ringkasan jurnal | `utils/sinta/outs/sinta_scrape_journals.md` |
| Daftar PTMA | `utils/ext/namapt_list.json` |

---

## 14. Backend API — Endpoint SintaJurnal (DRF)

**Proyek:** `chifoo_backend`
**Waktu:** 21 Maret 2026

### File yang Diubah

| File | Perubahan |
|---|---|
| `apps/universities/serializers.py` | Tambah `SintaJurnalSerializer`, `SintaJurnalListSerializer` |
| `apps/universities/views.py` | Tambah `SintaJurnalViewSet`, `PT20Pagination` |
| `apps/universities/urls.py` | Register router `sinta-jurnal/` |

### Serializer

**`SintaJurnalListSerializer`** — dipakai untuk action `list`:
- Semua field kecuali `logo_base64` (dihilangkan agar response list ringan)
- Field tambahan: `perguruan_tinggi_nama`, `perguruan_tinggi_singkatan`, `perguruan_tinggi_kode`

**`SintaJurnalSerializer`** — dipakai untuk action `retrieve`:
- Semua field termasuk `logo_base64`

### ViewSet

```python
class SintaJurnalViewSet(PublicReadAdminWriteMixin, viewsets.ReadOnlyModelViewSet):
    queryset = SintaJurnal.objects.select_related('perguruan_tinggi').order_by('-impact', 'nama')
    pagination_class = PT20Pagination        # page_size=20, max=200
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = {
        'akreditasi':       ['exact', 'in'],
        'is_scopus':        ['exact'],
        'is_garuda':        ['exact'],
        'perguruan_tinggi': ['exact'],
    }
    search_fields = ['nama', 'p_issn', 'e_issn', 'afiliasi_teks',
                     'perguruan_tinggi__nama', 'perguruan_tinggi__singkatan']
    ordering_fields = ['impact', 'h5_index', 'sitasi_total', 'sitasi_5yr', 'nama', 'akreditasi']
```

### Endpoint Tambahan: `/sinta-jurnal/stats/`

```
GET /api/sinta-jurnal/stats/
GET /api/sinta-jurnal/stats/?perguruan_tinggi=42
```

Response:
```json
{
  "total": 976,
  "scopus": 23,
  "garuda": 794,
  "distribusi_akreditasi": [
    {"akreditasi": "S1", "jumlah": 21},
    {"akreditasi": "S2", "jumlah": 89},
    ...
  ]
}
```

### Endpoint List — Parameter Query

| Parameter | Contoh | Keterangan |
|---|---|---|
| `search` | `?search=geografi` | Cari nama, ISSN, PT |
| `akreditasi` | `?akreditasi=S1` | Filter grade |
| `akreditasi__in` | `?akreditasi__in=S1,S2` | Multi-grade |
| `is_scopus` | `?is_scopus=true` | Scopus indexed |
| `is_garuda` | `?is_garuda=true` | Garuda indexed |
| `perguruan_tinggi` | `?perguruan_tinggi=42` | Filter by PT id |
| `ordering` | `?ordering=-impact` | Urutan |
| `page` | `?page=2` | Halaman |
| `page_size` | `?page_size=50` | Jumlah per halaman (maks 200) |

---

## 15. Frontend — Service & Routing

**Proyek:** `chifoo_frontend` (Angular 17)
**Waktu:** 21 Maret 2026

### File yang Diubah

| File | Perubahan |
|---|---|
| `src/app/services/api.service.ts` | Tambah 3 method SINTA Jurnal |
| `src/app/app.module.ts` | Import + declare + route `sinta/jurnal` |
| `src/app/components/sinta/sinta.component.ts` | Badge jurnal: "Jurnal" → "● Tersedia" (hijau) |

### Method API Baru (`api.service.ts`)

```typescript
getSintaJurnalList(params: any): Observable<any>
// GET /api/sinta-jurnal/?search=...&akreditasi=...&page=...

getSintaJurnalStats(ptId?: number): Observable<any>
// GET /api/sinta-jurnal/stats/

getSintaJurnalDetail(id: number): Observable<any>
// GET /api/sinta-jurnal/{id}/
```

### Routing Baru

```typescript
{ path: 'sinta/jurnal', component: SintaJurnalComponent }
```

Navigasi dari halaman SINTA hub: klik kartu "Jurnal Ilmiah" → `/sinta/jurnal`

---

## 16. Frontend — Halaman SintaJurnalComponent

**File baru:** `src/app/components/sinta/sinta-jurnal.component.ts`

### Fitur Halaman

#### Header
- Gradient cyan (#0891b2) konsisten dengan warna kelompok Media Ilmiah
- Breadcrumb "‹ Kembali ke PTMA di SINTA" → `/sinta`

#### Stats Bar
Muncul di atas filter setelah data dimuat:

| Chip | Isi |
|---|---|
| Total Jurnal | Jumlah seluruh jurnal (976) |
| Scopus Indexed | Jumlah jurnal terindeks Scopus (23) |
| Garuda Indexed | Jumlah jurnal terindeks Garuda (794) |
| S1–S6 | Distribusi per grade (6 chip) |

#### Filter Bar
- **Search** — debounced 400ms, cari nama jurnal/ISSN/PT
- **Akreditasi** — dropdown S1–S6
- **Scopus** — semua / scopus indexed / non-scopus
- **Garuda** — semua / garuda indexed / non-garuda
- **PT** — dropdown semua PTMA aktif (diload dari `/perguruan-tinggi/`)
- **Urutan** — impact ↓, impact ↑, H5-index ↓, total sitasi ↓, nama A–Z, akreditasi

#### Journal Grid
Responsif: 1 kolom (mobile) → 2 kolom (≥640px) → 3 kolom (≥1024px)

**Kartu jurnal** berisi:
- Logo jurnal (64×64, dari `logo_base64`) dengan fallback `onerror`
- Badge grade warna-warni di bawah logo:
  - S1 → ungu (#7c3aed)
  - S2 → biru (#2563eb)
  - S3 → cyan (#0891b2)
  - S4 → hijau (#059669)
  - S5 → kuning (#d97706)
  - S6 → merah (#dc2626)
- Nama jurnal, singkatan PT, afiliasi
- P-ISSN / E-ISSN (diformat `NNNN-NNNN` via `IssnPipe`)
- Subject area (badge ungu muda)
- Metrik: Impact · H5-Index · Sitasi 5yr · Total Sitasi
- Badge indeks: Scopus (biru) · Garuda (hijau)
- Tautan: Website · Scholar · Garuda (masing-masing warna berbeda)

#### Pagination
- Tombol ‹ / › dengan info halaman dan total count
- `window.scrollTo(top)` saat ganti halaman

### Pipe Tambahan

**`IssnPipe`** — dideklarasi dalam file yang sama:
```typescript
@Pipe({ name: 'issn' })
export class IssnPipe implements PipeTransform {
  transform(value: string): string {
    return value.replace(/(\d{4})(\d{4})/, '$1-$2');
    // "08520682" → "0852-0682"
  }
}
```

### Struktur Component

```
SintaJurnalComponent
├── ngOnInit()
│   ├── loadStats()      → GET /sinta-jurnal/stats/
│   ├── loadPtOptions()  → GET /perguruan-tinggi/?page_size=200
│   └── loadJournals()   → GET /sinta-jurnal/?...
├── Filter events
│   ├── onSearchInput()  → debounce 400ms → loadJournals()
│   ├── applyFilter()    → reset page=1 → loadJournals()
│   └── resetFilter()    → clear semua → loadJournals()
└── Pagination
    └── goPage(n)        → loadJournals() + scrollTo(top)
```

---

## 17. Status Frontend (Setelah Sesi Ini)

| Halaman | Route | Status |
|---|---|---|
| SINTA Hub | `/sinta` | ✅ Aktif |
| Afiliasi PT | `/sinta/afiliasi` | 🔧 Placeholder |
| Departemen | `/sinta/departemen` | 🔧 Placeholder |
| Author/Penulis | `/sinta/author` | 🔧 Placeholder |
| Artikel Ilmiah | `/sinta/artikel` | 🔧 Placeholder |
| Penelitian | `/sinta/penelitian` | 🔧 Placeholder |
| Pengabdian | `/sinta/pengabdian` | 🔧 Placeholder |
| IPR | `/sinta/ipr` | 🔧 Placeholder |
| Buku | `/sinta/buku` | 🔧 Placeholder |
| **Jurnal Ilmiah** | **`/sinta/jurnal`** | **✅ Aktif** |

---

## 18. Pekerjaan Berikutnya (Backlog — Diperbarui)

- [ ] Halaman `/sinta/afiliasi` — tabel ranking SINTA per PT, chart tren
- [ ] Halaman `/sinta/artikel` — tabel publikasi Scopus, chart tren per PT
- [ ] API endpoint DRF — tren tridharma per PT (`SintaTrendTahunan`)
- [ ] API endpoint DRF — ranking klasterisasi (`SintaCluster`)
- [ ] API endpoint DRF — WCU bidang keilmuan (`SintaWcuTahunan`)
- [ ] Analisis korelasi: cluster score vs Scopus score
- [ ] Scrape logo universitas (base64) untuk `PerguruanTinggi`
