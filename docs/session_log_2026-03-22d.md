# Session Log — Halaman Departemen SINTA (Backend + Frontend)

> Tanggal  : 2026-03-22 (sesi keempat)
> Scope    : Backend serializer/viewset + frontend halaman Departemen SINTA
> Repo     : chifoo_backend, chifoo_frontend

---

## A. Latar Belakang

Sesi sebelumnya (2026-03-22c) telah menyelesaikan:
- Scraping semua dept + dept detail + author list
- Model `SintaDepartemen`, `SintaAuthor`, `SintaAuthorTrend` + migration 0012–0013
- API endpoint dasar `/api/sinta-departemen/` dan `/api/sinta-author/`
- Frontend halaman Author SINTA (`sinta-author.component.ts`)

Pada sesi ini dibangun halaman Departemen SINTA secara lengkap, termasuk:
- Penambahan 17 field detail ke model `SintaDepartemen` (migration 0014)
- Re-import departemen dengan data detail dari `*_deptdetail.json`
- Serializer List + Detail dengan agregat author
- Frontend komponen `sinta-departemen.component.ts`

---

## B. Migration 0014 — Tambah 17 Field ke SintaDepartemen

### B.1 · Field yang ditambahkan

| Field | Tipe | Sumber Data |
|---|---|---|
| `sinta_score_productivity` | BigIntegerField | `*_deptdetail.json` |
| `sinta_score_productivity_3year` | BigIntegerField | `*_deptdetail.json` |
| `scopus_artikel` | IntegerField | `*_deptdetail.json` |
| `scopus_sitasi` | IntegerField | `*_deptdetail.json` |
| `gscholar_artikel` | IntegerField | `*_deptdetail.json` |
| `gscholar_sitasi` | IntegerField | `*_deptdetail.json` |
| `wos_artikel` | IntegerField | `*_deptdetail.json` |
| `wos_sitasi` | IntegerField | `*_deptdetail.json` |
| `scopus_q1`, `scopus_q2`, `scopus_q3`, `scopus_q4`, `scopus_noq` | PositiveIntegerField × 5 | `*_deptdetail.json` |
| `research_conference` | IntegerField | `*_deptdetail.json` |
| `research_articles` | IntegerField | `*_deptdetail.json` |
| `research_others` | IntegerField | `*_deptdetail.json` |
| `trend_scopus` | JSONField | `*_deptdetail.json` → list `[{tahun, jumlah}]` |

### B.2 · File migration

```
apps/universities/migrations/0014_add_dept_detail_fields.py
```

Semua field nullable (`default=0` / `default=list`) sehingga bisa diterapkan tanpa downtime data.

---

## C. Update Import Script `sp_import_sinta_departments.py`

### C.1 · Fungsi baru `load_detail_map(kode_pt)`

```python
def load_detail_map(kode_pt: str) -> dict:
    """
    Baca semua *_deptdetail.json untuk satu PT.
    Return dict: kode_dept → detail data.
    """
    detail_map = {}
    for f in (INPUT_DIR / kode_pt).glob(f"{kode_pt}_*_deptdetail.json"):
        try:
            d = json.loads(f.read_text())
            kode = d.get("kode_dept", "")
            if kode:
                detail_map[kode] = d
        except Exception:
            pass
    return detail_map
```

### C.2 · Merge detail ke setiap objek `SintaDepartemen`

Pada fungsi `import_file()`:
1. Panggil `load_detail_map(kode_pt)` sebelum loop
2. Untuk tiap departemen, ambil `det = detail_map.get(kode, {})`
3. Field detail di-set dari `det.get(...)`, fallback ke 0/`[]`

### C.3 · Hasil re-import

```
Memproses 154 file JSON...

  061008 (UMS): 79 lama → 79 baru, 79 dengan detail
  051013 (UAD): 79 lama → 79 baru, 77 dengan detail
  ...

Selesai: 2315 departemen diimport.
Total di database: 2315 departemen
```

---

## D. Backend — Serializer

### D.1 · `SintaDepartemenListSerializer`

Dipakai pada endpoint **list** (`GET /api/sinta-departemen/`).

Fields yang ditambah (dibanding sebelumnya):

```python
fields = [
    'id',
    'afiliasi_id', 'sinta_id_pt', 'pt_kode', 'pt_singkatan', 'pt_nama',
    'nama', 'jenjang', 'kode_dept', 'url_profil',
    'sinta_score_overall', 'sinta_score_3year',
    'sinta_score_productivity', 'sinta_score_productivity_3year',
    'jumlah_authors',
    'scopus_artikel', 'scopus_sitasi',
    'gscholar_artikel', 'gscholar_sitasi',
    'wos_artikel', 'wos_sitasi',
]
```

### D.2 · `SintaDepartemenDetailSerializer`

Dipakai pada endpoint **retrieve** (`GET /api/sinta-departemen/{id}/`).
Extends list + tambah:

| Field | Keterangan |
|---|---|
| `scopus_q1..q4, noq` | Distribusi kuartil |
| `research_conference/articles/others` | Research radar |
| `trend_scopus` | Array `[{tahun, jumlah}]` |
| `top_authors` | SerializerMethodField — top 5 by `sinta_score_overall` |
| `bidang_distribution` | SerializerMethodField — Counter bidang keilmuan, top 10 |
| `author_stats` | SerializerMethodField — agregat dari `SintaAuthor` FK |

**`author_stats` menghasilkan:**
```json
{
  "total_authors_linked": 5,
  "avg_sinta_score": 3241.2,
  "max_sinta_score": 8725,
  "total_scopus_artikel": 124,
  "total_scopus_sitasi": 4812,
  "avg_h_index": 7.2,
  "max_h_index": 15,
  "total_gscholar_artikel": 742,
  "total_wos_artikel": 38
}
```

> Catatan: `author_stats` saat ini nol untuk sebagian besar dept karena scraping author baru ~2399/17861 selesai. Data akan terisi seiring `sp_import_sinta_authors.py` dijalankan ulang.

### D.3 · Backward compatibility

Alias disediakan agar kode lain yang masih menggunakan nama lama tidak error:

```python
# serializers.py
SintaDepartemenSerializer = SintaDepartemenListSerializer

# views.py
SintaDepartemenSerializer = SintaDepartemenListSerializer  # legacy alias
```

---

## E. Backend — Viewset

### E.1 · `SintaDepartemenViewSet` — perubahan

```python
def get_serializer_class(self):
    if self.action == 'retrieve':
        return SintaDepartemenDetailSerializer
    return SintaDepartemenListSerializer

def get_queryset(self):
    qs = super().get_queryset()
    if self.action == 'retrieve':
        qs = qs.prefetch_related('authors')
    return qs
```

`prefetch_related('authors')` dipasang **hanya** pada retrieve untuk menghindari beban pada list endpoint.

### E.2 · Ordering field ditambah

```python
ordering_fields = [
    'sinta_score_overall', 'sinta_score_3year',
    'sinta_score_productivity', 'sinta_score_productivity_3year',
    'jumlah_authors', 'nama',
    'scopus_artikel', 'scopus_sitasi',
    'afiliasi__nama_sinta',
]
```

### E.3 · Tes API

```bash
# List
GET /api/sinta-departemen/?page_size=2&ordering=-sinta_score_overall
→ 2315 total, semua field baru tersedia

# Detail
GET /api/sinta-departemen/4769/
→ Fields: [..., trend_scopus, top_authors, bidang_distribution, author_stats]

# Stats
GET /api/sinta-departemen/stats/
→ {total_departemen: 2315, total_authors: 18543, avg: 2779, max: 136238}
```

---

## F. Frontend — `sinta-departemen.component.ts`

### F.1 · Interfaces

```typescript
interface TrendScopusItem { tahun: number; jumlah: number; }

interface TopAuthor {
  id, sinta_id, nama, foto_url,
  sinta_score_overall, scopus_artikel, scopus_h_index,
  bidang_keilmuan: string[]
}

interface AuthorStats {
  total_authors_linked, avg_sinta_score, max_sinta_score,
  total_scopus_artikel, total_scopus_sitasi,
  avg_h_index, max_h_index, total_gscholar_artikel, total_wos_artikel
}

interface DeptList { ... }        // 21 fields, dipakai pada list + card
interface DeptDetail extends DeptList { ... }  // + kuartil, radar, trend, top_authors, bidang, author_stats

interface DeptStats {
  total_departemen, total_authors,
  avg_score_overall, max_score_overall,
  distribusi_jenjang: [{jenjang, jumlah}]
}
```

### F.2 · Struktur layout halaman

```
.dp-wrap (max-width: 1400px)
├── .dp-back           — tombol kembali ke /sinta
├── .dp-hero           — hero banner dark gradient
│   ├── icon kalender  — SVG 36×36
│   └── judul + deskripsi
├── .dp-statsbar       — 5 chip stats (total dept, author, avg score, max score, sebaran jenjang)
├── .dp-toolbar
│   ├── .dp-search-wrap     — search full-width dengan icon + clear button
│   └── .dp-filter-row      — grid 4 kolom: PT | Jenjang | Sort | Tombol Reset
├── [loading / empty state]
├── .dp-grid            — CSS grid auto-fill minmax(270px, 1fr)
│   └── .dp-card × N   — klik → openDetail()
└── .dp-pagination      — ellipsis pagination

.dp-modal-backdrop (fixed overlay)
└── .dp-modal
    ├── .dp-modal__header   — jenjang badge + nama dept + PT + tombol ×
    └── .dp-modal__body
        ├── .dp-modal__scores   — 5 score cards (SINTA, 3yr, Produktivitas, Prod.3yr, Jumlah Author)
        ├── [author_stats]      — 6-cell grid agregat author
        ├── [publikasi per sumber] — tabel 3 baris: Scopus / GScholar / WOS
        ├── [kuartil bar]       — stacked proportional bar Q1/Q2/Q3/Q4/NoQ
        ├── [penelitian radar]  — 3 angka: Artikel / Prosiding / Lainnya
        ├── [trend chart]       — bar chart vertikal Scopus per tahun
        ├── [top authors]       — list 5 author: rank, foto, nama, bidang, skor
        ├── [bidang distribution] — horizontal bar per bidang keilmuan
        └── [link SINTA]        — tombol "Lihat Profil di SINTA"
```

### F.3 · CSS layout utama

| Selector | Rule | Keterangan |
|---|---|---|
| `.dp-wrap` | `max-width: 1400px; margin: 0 auto; padding: 1.25rem` | Konsisten dengan halaman SINTA lain |
| `.dp-filter-row` | `display: grid; grid-template-columns: 1fr 1fr 1fr auto` | Filter sejajar, lebar proporsional |
| `@media max-width: 600px` | `grid-template-columns: 1fr` | Kolom tunggal di mobile |
| `.dp-grid` | `grid-template-columns: repeat(auto-fill, minmax(270px, 1fr))` | Responsive tanpa breakpoint manual |

### F.4 · Helper functions

| Fungsi | Keterangan |
|---|---|
| `jenjangClass(j)` | Normalize jenjang → CSS class: `s1`, `s2`, `s3`, `d3`, `d4`, `profesi` |
| `kuartilSegments(d)` | Konversi Q1-Q4+NoQ ke array `{key, label, val, pct}` untuk stacked bar |
| `sortedTrend(trend)` | Sort trend array by `tahun` ascending |
| `trendBarHeight(jumlah, trend)` | Normalisasi 0–100% relatif terhadap max tahun |
| `authorInitials(nama, idx)` | SVG initials avatar jika `foto_url` kosong |
| `pageNumbers()` | Ellipsis pagination: `[1, ..., cur-1, cur, cur+1, ..., N]` |

### F.5 · Data loading

```typescript
ngOnInit() {
  this.loadStats();       // GET /api/sinta-departemen/stats/
  this.loadPtOptions();   // GET /api/sinta-afiliasi/?page_size=500
  this.loadDepts();       // GET /api/sinta-departemen/ (paginated)
}

openDetail(dept) {
  this.selected = dept;
  this.detailLoading = true;
  GET /api/sinta-departemen/{dept.id}/
  → this.detail = response
}
```

Search menggunakan `debounceTime(350)` via `Subject`.
Filter change (PT/jenjang/ordering) langsung reload.

---

## G. Update Halaman SINTA Utama

Badge **"Segera Hadir"** dihapus dari kartu **Departemen** di `sinta.component.ts`:

```html
<!-- Sebelum -->
<div class="sinta-card__title">Departemen</div>
<div class="sinta-card__desc">...</div>
<span class="sinta-badge sinta-badge--soon">Segera Hadir</span>

<!-- Sesudah -->
<div class="sinta-card__title">Departemen</div>
<div class="sinta-card__desc">...</div>
```

Halaman Author sudah dihapus badge-nya pada sesi sebelumnya.

---

## H. Registrasi Komponen

`SintaDepartemenComponent` dipindah dari placeholder di `pages.ts` ke file dedicated:

```
Sebelum: pages.ts → export class SintaDepartemenComponent {} (placeholder)
Sesudah: sinta-departemen.component.ts → export class SintaDepartemenComponent
```

`app.module.ts` diupdate:
```typescript
// Sebelum
import { SintaDepartemenComponent, ... } from './components/sinta/pages';

// Sesudah
import { ... } from './components/sinta/pages';  // tanpa SintaDepartemenComponent
import { SintaDepartemenComponent } from './components/sinta/sinta-departemen.component';
```

Route sudah terdefinisi di sesi sebelumnya:
```typescript
{ path: 'sinta/departemen', component: SintaDepartemenComponent }
```

---

## I. Build & Deploy

```bash
# Build production
npm run build:prod
# Output: dist/ptma-frontend/browser/main-*.js (1.6 MB)
# Warning: CSS budget exceeded (bukan error)

# Git commit
chifoo_backend: feat: halaman Departemen SINTA — detail fields, serializer, viewset
chifoo_frontend: feat: halaman Departemen SINTA — komponen Angular lengkap

# Push
git push origin main  # GitHub
git push gitlab main  # GitLab UMS
```

---

## J. Status Update Komponen

| Komponen | Status |
|---|---|
| Model `SintaDepartemen` (17 field detail) | ✅ Migration 0014 applied |
| Re-import departemen dengan detail | ✅ 2315 rows, 79 PT |
| `SintaDepartemenListSerializer` | ✅ 21 fields |
| `SintaDepartemenDetailSerializer` | ✅ + kuartil, trend, top_authors, author_stats |
| `SintaDepartemenViewSet` get_serializer_class | ✅ list/retrieve berbeda |
| Frontend `sinta-departemen.component.ts` | ✅ Lengkap |
| Badge "Segera Hadir" Departemen | ✅ Dihapus |
| Build production + push GitHub/GitLab | ✅ Commit `292bf04` + `a8b43b9` |
| `author_stats` terisi penuh | ⏳ Tunggu scraping author selesai (~2399/17861) |

---

## K. Catatan Teknis

### K.1 · `author_stats` vs `jumlah_authors` di SINTA

`jumlah_authors` dari SINTA mencerminkan jumlah dosen yang **terdaftar di dept** pada SINTA (bisa 14+).
`author_stats.total_authors_linked` adalah jumlah dosen yang **sudah di-scrape detail-nya dan di-import ke DB**.
Selama scraping belum selesai, `total_authors_linked` < `jumlah_authors`.

### K.2 · Trend chart Scopus

Trend disimpan sebagai JSONField di `SintaDepartemen.trend_scopus`:
```json
[{"tahun": 2013, "jumlah": 3}, {"tahun": 2014, "jumlah": 5}, ...]
```
Frontend mengurutkan ascending by `tahun` dan menormalkan tinggi bar relatif terhadap tahun terbanyak.

### K.3 · Kuartil bar

Ditampilkan sebagai proportional stacked bar menggunakan `flex` — setiap segmen diberikan `flex: <pct>`.
Teks nilai hanya muncul jika `pct > 5` agar tidak overflow.

### K.4 · Top authors + bidang distribution

Keduanya dihitung **on-the-fly** di `SintaDepartemenDetailSerializer`.
Jika performa menjadi masalah pada dept besar (>200 authors), pertimbangkan pre-compute saat import.

---

## L. Rencana Berikutnya

| Task | Prioritas |
|---|---|
| Jalankan ulang `sp_import_sinta_authors.py` setelah scrape selesai agar `author_stats` terisi | Tinggi |
| Deploy ke `public_html` production (tunggu FTP stabil) | Sedang |
| Halaman Author: filter per departemen dari halaman Departemen (cross-link) | Sedang |
| Halaman Artikel / Penelitian / Pengabdian | Rendah |
