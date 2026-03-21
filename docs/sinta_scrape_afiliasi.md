# SINTA Scrape — Profil Afiliasi Perguruan Tinggi

Dokumen ini mencatat seluruh rencana, desain, dan detail teknis scraping data afiliasi PTMA dari situs SINTA (Science and Technology Index).

---

## 1. Gambaran Umum

**Tujuan:** Mengambil data profil afiliasi (publikasi, skor SINTA, kuartil) untuk seluruh Perguruan Tinggi Muhammadiyah & Aisyiyah (PTMA) dari situs SINTA Kemdiktisaintek.

**Pendekatan:** `requests` + `BeautifulSoup` (lxml) — **tanpa Selenium**. Seluruh data tersedia di HTML respons statik (server-side rendering), termasuk data chart yang di-embed sebagai inline JavaScript eCharts.

**Script:** `utils/sinta/scrape_sinta_afiliasi.py`

**Input:** `utils/ext/namapt_list.json` (162 PT, field: `kode`, `target`, `keyword`)

**Output:** `utils/outs/sinta_afiliasi.json`

---

## 2. URL dan Alur Scraping

### 2.1 URL Kunci

| Tujuan | URL |
|---|---|
| Cari PT by kode PDDikti | `https://sinta.kemdiktisaintek.go.id/affiliations?q={kode_pt}&search=1` |
| Profil afiliasi | `https://sinta.kemdiktisaintek.go.id/affiliations/profile/{sinta_id}` |

### 2.2 Alur 2 Langkah

```
namapt_list.json
      │
      ▼
[Step 1] Cari SINTA ID
  GET /affiliations?q={kode_pt}&search=1
  → Cari href="/affiliations/profile/(\d+)" di semua tag <a>
  → Ambil sinta_id dari group(1)
      │
      ▼
[Step 2] Scrape Profil
  GET /affiliations/profile/{sinta_id}
  → Parse HTML dengan BeautifulSoup (lxml)
  → Ekstrak semua data (lihat §4)
      │
      ▼
  Auto-save ke sinta_afiliasi.json (per PT)
```

### 2.3 Session Management

- Satu `requests.Session` untuk seluruh proses
- Header tetap: `User-Agent` Firefox, `Accept-Language: id,en-US`, `Referer: sinta.kemdiktisaintek.go.id`
- Jeda antar request: **1.5 detik**
- Jeda antar PT: **2.0 detik**
- Timeout: **30 detik**
- Retry: **4 kali** dengan jeda **8 detik**

---

## 3. Struktur HTML Halaman Profil Afiliasi

### 3.1 Tab / View yang Tersedia

Halaman profil afiliasi memiliki 8 tab (sub-view). Default adalah tab **Articles**:

| Tab | URL Parameter | Data |
|---|---|---|
| Articles (default) | *(tidak ada)* | Publikasi Scopus, statistik, kuartil |
| Researches | `?view=researches` | Data penelitian |
| Community Services | `?view=services` | Pengabdian masyarakat |
| IPRs | `?view=iprs` | HKI/Paten |
| Books | `?view=books` | Buku |
| Networks | `?view=networks` | Jaringan kolaborasi |
| Metrics | `?view=matrics` | Metrik performa |
| Metrics Cluster 2026 | `?view=matricscluster2026` | Klaster metrik 2026 |

**Scraper saat ini hanya mengambil tab default (Articles).**

### 3.2 Selectors CSS Kunci

```
.univ-name > h3/h2/h1    → nama lengkap PT
.affil-abbrev             → singkatan PT
.affil-loc                → lokasi PT
.affil-code               → "ID : 27  CODE : 061008"

.stat-num / .stat-text    → kartu ringkasan (Authors, Departments, Journals)
.pr-num  / .pr-txt        → SINTA Score cards (4 varian)

table.stat-table          → tabel statistik 4 sumber × 4 metrik
  thead th.text-warning   → kolom Scopus
  thead th.text-success   → kolom Google Scholar
  thead th.text-primary   → kolom Web of Science  ← HIDDEN (d-none), tapi terbaca BeautifulSoup
  thead th.text-danger    → kolom Garuda

#quartile-pie             → container chart kuartil (data di inline JS)
#research-radar           → container chart research output (data di inline JS)
#scopus-chart-articles    → container chart tren artikel per tahun (data di inline JS)

.ar-list-item.mb-5        → tiap entri artikel Scopus
  .ar-title > a           → judul artikel + link Scopus
  .ar-quartile            → quartile artikel ("Q1 Journal", dst)
  .ar-pub                 → nama jurnal + link
  Creator : X             → nama penulis pertama
  .ar-year                → tahun
  .ar-cited               → jumlah sitasi

<small>Last update...     → timestamp update terakhir
```

### 3.3 Catatan WoS Hidden

Kolom Web of Science menggunakan class `d-none` (tersembunyi di browser) namun tetap ada di DOM:
```html
<th class="text-primary d-none">WOS</th>
<td class="text-primary d-none">92</td>
```
BeautifulSoup membaca semua elemen DOM tanpa memperhatikan CSS visibility, sehingga data WoS **ikut terambil** secara otomatis.

---

## 4. Data yang Diambil (Saat Ini)

### 4.1 Identitas

| Field JSON | Sumber | Contoh |
|---|---|---|
| `sinta_id` | `.affil-code` / URL | `"27"` |
| `sinta_kode` | `.affil-code` | `"061008"` |
| `nama` | `.univ-name > h3` | `"Universitas Muhammadiyah Surakarta"` |
| `singkatan` | `.affil-abbrev` | `"UMS"` |
| `lokasi` | `.affil-loc` | `"Sukoharjo, Jawa Tengah"` |
| `sinta_profile_url` | konstruksi URL | `"https://sinta.../profile/27"` |
| `sinta_last_update` | `<small>Last update...` | `"2025-12-15"` |
| `nama_input` | dari namapt_list.json | `"Universitas Muhammadiyah Surakarta"` |
| `kode_input` | dari namapt_list.json | `"061008"` |

### 4.2 Ringkasan

| Field JSON | CSS | Contoh |
|---|---|---|
| `jumlah_authors` | `.stat-num` + `.stat-text` | `908` |
| `jumlah_departments` | `.stat-num` + `.stat-text` | `79` |
| `jumlah_journals` | `.stat-num` + `.stat-text` | `47` |

### 4.3 SINTA Score

| Field JSON | Label di halaman | Contoh |
|---|---|---|
| `sinta_score_overall` | "SINTA Score Overall" | `1318091` |
| `sinta_score_3year` | "SINTA Score 3Yr" | `681583` |
| `sinta_score_productivity` | "SINTA Score Productivity" | `1662` |
| `sinta_score_productivity_3year` | "SINTA Score Productivity 3Yr" | `860` |

### 4.4 Statistik Publikasi (4 sumber × 4 metrik = 16 field)

Sumber: `scopus`, `gscholar`, `wos`, `garuda`

Metrik: `dokumen`, `sitasi`, `dokumen_disitasi`, `sitasi_per_peneliti`

Contoh field: `scopus_dokumen`, `gscholar_sitasi`, `wos_dokumen_disitasi`, `garuda_sitasi_per_peneliti`

Contoh data (UMS):

| | Scopus | GScholar | WoS | Garuda |
|---|---|---|---|---|
| Documents | 4.350 | 77.888 | 92 | 22.897 |
| Citation | 100.009 | 429.541 | 459 | 101 |
| Cited Doc | 2.891 | 39.260 | 29 | 73 |
| Cit/Res | 117,66 | 505,34 | 0,54 | 0,12 |

> **Format angka:** SINTA menggunakan titik sebagai pemisah ribuan dan koma sebagai desimal (format Indonesia). Helper `_parse_number()` menangani konversi ke float.

### 4.5 Distribusi Kuartil Scopus

| Field JSON | Contoh |
|---|---|
| `scopus_q1` | `667` |
| `scopus_q2` | `631` |
| `scopus_q3` | `922` |
| `scopus_q4` | `1445` |
| `scopus_noq` | `685` |

**Sumber data:** Inline JavaScript eCharts di halaman (bukan elemen HTML biasa):
```javascript
var quartilePie = echarts.init(document.getElementById('quartile-pie'), 'macarons');
optionQ = {
    series: [{
        data: [
            {value: 667, name: 'Q1'},
            {value: 631, name: 'Q2'},
            {value: 922, name: 'Q3'},
            {value: 1445, name: 'Q4'},
            {value: 685, name: 'No-Q'}
        ]
    }]
};
```

**Cara ekstraksi:** Regex pada raw page source:
```python
# Cari blok JS mulai dari 'quartilePie' atau 'optionQ'
m = re.search(r"quartilePie|optionQ|quartile.pie", raw, re.IGNORECASE)
quartile_block = raw[m.start():m.start() + 2000]

# Ekstrak semua {value: N, name: 'QX'}
pattern = re.compile(
    r'\{[^}]*value\s*:\s*(\d+)\s*,[^}]*name\s*:\s*[\'"]([^\'\"]+)[\'"][^}]*\}',
    re.IGNORECASE
)
```

---

## 5. Data yang BELUM Diambil (Rencana)

### 5.1 Research Output Radar (inline JS)

Chart radar di `#research-radar` menyimpan breakdown tipe output Scopus:

```javascript
var researchRadar = echarts.init(document.getElementById('research-radar'), 'macarons');
optionRadar = {
    radar: {
        indicator: [
            {name: 'Article', max: 2676},
            {name: 'Conference', max: 2676},
            {name: 'Others', max: 2676},
        ],
    },
    series: [{
        data: [{
            value: [2676, 1512, 162],  // Article, Conference, Others
            name: 'Output',
        }]
    }]
};
```

Field yang direncanakan: `scopus_article`, `scopus_conference`, `scopus_others`

Cara ekstraksi: Regex pada `optionRadar` block, ambil array `value: [...]`.

### 5.2 Tren Scopus Per Tahun (inline JS)

Chart line di `#scopus-chart-articles` menyimpan jumlah artikel per tahun:

```javascript
var myChart = echarts.init(document.getElementById('scopus-chart-articles'), 'macarons');
option = {
    xAxis: {
        data: ['2011', '2012', ..., '2026'],
    },
    series: [{
        data: [31, 27, 42, 50, 53, 89, 116, 196, 390, 430, 403, 362, 608, 831, 639, 43],
        type: 'line',
    }]
};
```

Field yang direncanakan: `scopus_tren_tahun` → `{"2011": 31, "2012": 27, ...}`

Cara ekstraksi: Regex pada `scopus-chart-articles` block, ambil array `data:` dari xAxis dan series.

### 5.3 Daftar Artikel Scopus Individual

Tiap artikel tersedia di halaman dengan struktur:
```html
<div class="ar-list-item mb-5">
    <div class="ar-title">
        <a href="https://www.scopus.com/record/display.uri?eid=2-s2.0-..." target="_blank">
            Judul Artikel
        </a>
    </div>
    <div class="ar-meta">
        <a class="ar-quartile">Q1 Journal</a>
        <a class="ar-pub" href="https://www.scopus.com/sourceid/...">Nama Jurnal</a>
        <a href="#!">Creator : Nama Penulis</a>
    </div>
    <div class="ar-meta">
        <a class="ar-year">2026</a>
        <a class="ar-cited">1 cited</a>
    </div>
</div>
```

Field per artikel: `judul`, `url_scopus`, `quartile`, `jurnal`, `url_jurnal`, `penulis`, `tahun`, `sitasi`

**Catatan:** Kemungkinan ada paginasi (halaman 1, 2, 3, ...). Perlu scraper terpisah dengan paginasi handling.

### 5.4 Logo Universitas

Setiap halaman profil afiliasi memuat logo universitas dengan URL:
```
/authorverification/public/images/affiliations/{sinta_id}.jpg
```
Contoh (UMS, sinta_id=27):
```html
<img src="/authorverification/public/images/affiliations/27.jpg"
     onerror="this.onerror=null;this.src='https://sinta.kemdiktisaintek.go.id/public/assets/img/author-small.png';"
     class="img-fluid round-corner mb-4 univ-logo-main">
```

**Rencana pengambilan:**
1. Ambil URL logo dari tag `<img class="univ-logo-main">` di halaman profil
2. Download binary logo dengan GET request
3. Encode ke base64: `base64.b64encode(content).decode()`
4. Simpan sebagai `"data:image/jpeg;base64,..."` di field `logo_base64`
5. Jika URL logo 404 → simpan string kosong (fallback di frontend)

### 5.5 Tab Lain (Researches, Books, IPRs, dst.)

Masing-masing tab (`?view=researches`, `?view=services`, dll.) memuat data berbeda. Rencana scrape masing-masing tab sebagai script atau fungsi terpisah.

---

## 6. Rencana Tabel Database

### 6.1 `SintaAfiliasi` (tabel utama)

Menyimpan satu baris per PT per periode scrape.

```
kode_pt               CharField(20)   PK / FK ke PerguruanTinggi
sinta_id              CharField(20)
sinta_kode            CharField(20)
nama                  CharField(200)
singkatan             CharField(50)
lokasi                CharField(200)
sinta_profile_url     URLField

jumlah_authors        IntegerField
jumlah_departments    IntegerField
jumlah_journals       IntegerField

sinta_score_overall       BigIntegerField
sinta_score_3year         BigIntegerField
sinta_score_productivity  IntegerField
sinta_score_productivity_3year IntegerField

scopus_dokumen            FloatField
scopus_sitasi             FloatField
scopus_dokumen_disitasi   FloatField
scopus_sitasi_per_peneliti FloatField

gscholar_dokumen          FloatField
gscholar_sitasi           FloatField
gscholar_dokumen_disitasi FloatField
gscholar_sitasi_per_peneliti FloatField

wos_dokumen               FloatField
wos_sitasi                FloatField
wos_dokumen_disitasi      FloatField
wos_sitasi_per_peneliti   FloatField

garuda_dokumen            FloatField
garuda_sitasi             FloatField
garuda_dokumen_disitasi   FloatField
garuda_sitasi_per_peneliti FloatField

scopus_q1                 IntegerField
scopus_q2                 IntegerField
scopus_q3                 IntegerField
scopus_q4                 IntegerField
scopus_noq                IntegerField

sinta_last_update         CharField(50)
scraped_at                DateTimeField   (auto_now_add)

logo_base64               TextField(blank=True)
                          # Logo universitas dari /authorverification/public/images/affiliations/{sinta_id}.jpg
                          # Di-download saat scrape, di-encode base64, disimpan sebagai string
                          # Format: "data:image/jpeg;base64,/9j/4AAQ..."
                          # Fallback: gunakan logo default SINTA jika URL 404
```

### 6.2 Field Rencana Tambahan di `SintaAfiliasi` (setelah §5 diimplementasi)

```
scopus_article            IntegerField   (dari research-radar JS)
scopus_conference         IntegerField   (dari research-radar JS)
scopus_others             IntegerField   (dari research-radar JS)
```

> **Catatan:** `scopus_tren_tahun` awalnya direncanakan sebagai `JSONField` di `SintaAfiliasi`,
> namun diputuskan menggunakan **tabel terpisah** (`SintaPublikasiTahunan`) agar mendukung
> query per tahun, agregasi lintas PT, dan ranking — lihat §6.3.

### 6.3 Tabel Terpisah: `SintaPublikasiTahunan`

Data tren publikasi per tahun disimpan dalam tabel relasional terpisah (bukan JSONField)
karena kebutuhan analitik: query per tahun, agregasi, ranking antar PT.

**Alasan memilih tabel terpisah vs JSONField:**

| Kebutuhan | JSONField | Tabel Terpisah |
|---|---|---|
| Chart per PT | ✅ | ✅ |
| Total PTMA per tahun | ❌ | ✅ |
| Ranking PT per tahun | ❌ | ✅ |
| Filter berdasarkan tahun | ❌ | ✅ |
| Schema extensible (tambah sumber) | ❌ | ✅ |

**Struktur tabel `universities_sintapublikasitahunan`:**

```
Kolom                   Tipe                      Keterangan
──────────────────────────────────────────────────────────────────────
id                      AutoField (PK)
afiliasi                FK → SintaAfiliasi         on_delete=CASCADE
tahun                   PositiveSmallIntegerField  rentang 2000–2030
scopus_dokumen          PositiveIntegerField       jumlah artikel Scopus tahun ini
                                                   sumber: chart #scopus-chart-articles
gscholar_dokumen        PositiveIntegerField       default=0  (belum tersedia di scraper)
wos_dokumen             PositiveIntegerField       default=0  (belum tersedia di scraper)
garuda_dokumen          PositiveIntegerField       default=0  (belum tersedia di scraper)
scraped_at              DateTimeField              auto_now=True

UNIQUE: (afiliasi, tahun)
INDEX : tahun, afiliasi
```

**Relasi antar tabel:**

```
PerguruanTinggi (kode_pt)
       │ OneToOneField
       ▼
  SintaAfiliasi
       │ ForeignKey (one-to-many)
       ▼
  SintaPublikasiTahunan
  ┌─────────────────────────────────────┐
  │ afiliasi_id │ tahun │ scopus_dokumen│
  ├─────────────────────────────────────┤
  │ 27 (UMS)    │ 2015  │ 89            │
  │ 27 (UMS)    │ 2016  │ 116           │
  │ 27 (UMS)    │ 2017  │ 196           │
  │ ...         │ ...   │ ...           │
  │ 2530 UNISMUH│ 2015  │ 12            │
  └─────────────────────────────────────┘
```

**Estimasi data:** 158 PT × rata-rata 15 tahun ≈ **~2.370 row**

**Sumber data scrape:** Inline JS `#scopus-chart-articles` di halaman profil SINTA:
```javascript
option = {
    xAxis: { data: ['2011', '2012', ..., '2025', '2026'] },
    series: [{ data: [31, 27, 42, 50, 53, 89, 116, 196, 390, 430, 403, 362, 608, 831, 639, 43] }]
}
```
Regex ekstraksi: cari blok `scopus-chart-articles`, ambil pasangan xAxis.data ↔ series.data.

**Query contoh:**
```python
# Tren Scopus satu PT
SintaPublikasiTahunan.objects.filter(afiliasi__perguruan_tinggi__kode_pt='061008').order_by('tahun')

# Total publikasi Scopus seluruh PTMA per tahun
SintaPublikasiTahunan.objects.values('tahun').annotate(total=Sum('scopus_dokumen')).order_by('tahun')

# Ranking PT terbanyak Scopus tahun 2024
SintaPublikasiTahunan.objects.filter(tahun=2024).order_by('-scopus_dokumen').select_related('afiliasi__perguruan_tinggi')
```

**Status:** ⏳ Model & migration belum dibuat — menunggu konfirmasi

---

## 7. Penggunaan Script

```bash
# Scrape semua PT (resumable — skip yang sudah ada)
python utils/sinta/scrape_sinta_afiliasi.py

# Scrape satu PT berdasarkan kode PDDikti
python utils/sinta/scrape_sinta_afiliasi.py --kode 061008

# Batasi jumlah PT (untuk testing)
python utils/sinta/scrape_sinta_afiliasi.py --limit 5

# Tampilkan ringkasan output yang sudah ada, lalu keluar
python utils/sinta/scrape_sinta_afiliasi.py --status
```

### 7.1 Mekanisme Resume

Output disimpan sebagai dict `{kode_pt: {...data...}}` di JSON. Setiap kode PT yang sudah ada di file output akan di-skip (baris: `if kode in results: continue`). Auto-save dilakukan **setelah tiap PT** berhasil diproses.

---

## 8. Logo SINTA

Logo SINTA (147×147px RGBA PNG) disimpan sebagai konstanta `SINTA_LOGO_BASE64` di dalam script (base64-encoded). Logo di-embed agar script tidak bergantung pada file eksternal.

**Catatan:** URL asli logo (`/public/assets/img/brand_sinta.png`) saat ini mengembalikan 404, sehingga tidak bisa di-download ulang secara otomatis. Logo di-embed dari versi yang sudah didownload sebelumnya.

---

## 9. Library Eksternal SINTA

Library JS yang dimuat halaman SINTA (untuk referensi chart):

```
echarts-en.min.js       → ECharts library (chart engine)
macarons.js             → ECharts theme "Macarons"
chart.js                → Chart.js (library alternatif)
d3.js + topojson.js     → D3.js (untuk datamaps)
datamaps.idn.js         → Peta Indonesia (choropleth)
```

Semua chart data di-embed sebagai **inline `<script>`** di HTML — tidak dimuat dari file JS eksternal. Artinya cukup satu GET request per halaman untuk mendapatkan semua data.

---

## 10. Hasil Scrape (21 Maret 2026)

### 10.1 Ringkasan Eksekusi

| Item | Nilai |
|---|---|
| Tanggal scrape | 21 Maret 2026 |
| Total PT diproses | 162 |
| Ditemukan di SINTA | **158** |
| Tidak ditemukan | 4 |
| Error | 0 |
| Diimport ke DB | **156** (2 kode_pt tidak ada di DB lokal) |
| File individual | `utils/sinta/outs/{kode}_sinta_afiliasi.json` (162 file) |
| File gabungan | `utils/outs/sinta_afiliasi.json` |

### 10.2 Contoh Output (UNISMUH Makassar — `091004_sinta_afiliasi.json`)

```json
{
  "sinta_profile_url": "https://sinta.kemdiktisaintek.go.id/affiliations/profile/2530",
  "sinta_id": "2530",
  "nama": "Universitas Muhammadiyah Makassar",
  "singkatan": "UNISMUH MAKASSAR",
  "lokasi": "KOTA MAKASSAR - SULAWESI SELATAN, ID",
  "sinta_kode": "091004",
  "jumlah_authors": 794,
  "jumlah_departments": 70,
  "jumlah_journals": 27,
  "sinta_score_overall": 296472,
  "sinta_score_3year": 137494,
  "sinta_score_productivity": 369,
  "sinta_score_productivity_3year": 171,
  "scopus_dokumen": 938.0,
  "gscholar_dokumen": 29836.0,
  "wos_dokumen": 24.0,
  "garuda_dokumen": 6842.0,
  "scopus_sitasi": 4.84,
  "gscholar_sitasi": 212.15,
  "wos_sitasi": 0.21,
  "garuda_sitasi": 0.01,
  "scopus_dokumen_disitasi": 615.0,
  "gscholar_dokumen_disitasi": 14633.0,
  "wos_dokumen_disitasi": 12.0,
  "garuda_dokumen_disitasi": 5.0,
  "scopus_q1": 143,
  "scopus_q2": 135,
  "scopus_q3": 243,
  "scopus_q4": 254,
  "scopus_noq": 163,
  "sinta_last_update": "2026-03-04 07:58:02",
  "nama_input": "UNIVERSITAS MUHAMMADIYAH MAKASSAR",
  "kode_input": "091004"
}
```

### 10.3 Statistik Agregat Seluruh PTMA

**Total Publikasi per Sumber:**

| Sumber | Total Dokumen |
|---|---|
| Scopus | 34.912 |
| Google Scholar | 742.056 |
| Web of Science | 825 |
| Garuda | 224.326 |

**Distribusi Kuartil Scopus (total semua PT):**

| Q1 | Q2 | Q3 | Q4 | No-Q | Total |
|---|---|---|---|---|---|
| 4.937 | 5.297 | 7.459 | 10.855 | 6.364 | **34.912** |

### 10.4 Top 10 SINTA Score Overall

| Rank | PT | Kode | SINTA Score |
|---|---|---|---|
| 1 | Universitas Muhammadiyah Sidoarjo | 071060 | 1.456.645 |
| 2 | Universitas Muhammadiyah Surakarta | 061008 | 1.318.091 |
| 3 | Universitas Muhammadiyah Malang | 071024 | 835.352 |
| 4 | Universitas Muhammadiyah Surabaya | 071012 | 819.771 |
| 5 | Universitas Ahmad Dahlan | 051013 | 693.774 |
| 6 | Universitas Muhammadiyah Sumatera Utara | 011003 | 648.451 |
| 7 | Universitas Muhammadiyah Yogyakarta | 051007 | 646.993 |
| 8 | Universitas Muhammadiyah Jakarta | 031011 | 390.804 |
| 9 | Universitas Muhammadiyah Prof Dr Hamka | 031039 | 359.960 |
| 10 | Universitas Muhammadiyah Purwokerto | 061019 | 328.664 |

### 10.5 Top 10 Dokumen Scopus

| Rank | PT | Dokumen |
|---|---|---|
| 1 | Universitas Muhammadiyah Yogyakarta | 4.456 |
| 2 | Universitas Muhammadiyah Surakarta | 4.350 |
| 3 | Universitas Ahmad Dahlan | 3.747 |
| 4 | Universitas Muhammadiyah Malang | 2.980 |
| 5 | Universitas Muhammadiyah Prof Dr Hamka | 2.128 |
| 6 | Universitas Muhammadiyah Semarang | 1.002 |
| 7 | Universitas Muhammadiyah Purwokerto | 984 |
| 8 | Universitas Muhammadiyah Makassar | 938 |
| 9 | Universitas Muhammadiyah Sumatera Utara | 918 |
| 10 | Universitas Muhammadiyah Jakarta | 837 |

### 10.6 PT Tidak Ditemukan di SINTA (4 PT)

| Kode | Nama |
|---|---|
| 073182 | Sekolah Tinggi Teknologi Muhammadiyah AR Fachruddin |
| 091094 | Universitas Muhammadiyah Kolaka Utara |
| 102011 | Institut Teknologi dan Bisnis Muhammadiyah Sarolangun |
| 212174 | Institut Muhammadiyah Darul Arqam Garut |

### 10.7 PT Tidak Ada di DB Lokal (2 PT, tidak diimport)

| Kode | Keterangan |
|---|---|
| 171018 | kode_pt tidak ada di tabel PerguruanTinggi |
| 173136 | kode_pt tidak ada di tabel PerguruanTinggi |

---

## 11. Bugs dan Catatan Diketahui

| No | Masalah | Status |
|---|---|---|
| 1 | WoS kolom hidden (`d-none`) | ✅ Sudah ditangani — BeautifulSoup baca semua DOM |
| 2 | Format angka Indonesia (`.` ribuan, `,` desimal) | ✅ `_parse_number()` menangani |
| 3 | Logo URL 404 | ✅ Logo embed base64 di script |
| 4 | Research radar belum diambil | ⏳ Direncanakan (§5.1) |
| 5 | Tren Scopus per tahun belum diambil | ⏳ Direncanakan (§5.2) |
| 6 | Daftar artikel individual belum diambil | ⏳ Direncanakan (§5.3) |
| 7 | Tab lain (researches, books, dst.) belum diambil | ⏳ Direncanakan (§5.5) |
| 8 | Logo universitas belum diambil | ⏳ Direncanakan (§5.4) — URL: `/authorverification/public/images/affiliations/{sinta_id}.jpg` |
