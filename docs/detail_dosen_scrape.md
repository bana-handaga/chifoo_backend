# Scraper Detail Dosen PDDikti

Dokumentasi lengkap untuk `utils/scrape_pddikti_detaildosen.py` dan `utils/scrape_pddikti_batch_dosen.py`.

---

## Daftar Isi

1. [Gambaran Umum](#1-gambaran-umum)
2. [Arsitektur & Alur Kerja](#2-arsitektur--alur-kerja)
3. [Penggunaan](#3-penggunaan)
4. [Struktur Output JSON](#4-struktur-output-json)
5. [Perubahan Struktur Website PDDikti (2025)](#5-perubahan-struktur-website-pddikti-2025)
6. [Detail Teknis Scraping](#6-detail-teknis-scraping)
7. [Mekanisme Fail-Safe](#7-mekanisme-fail-safe)
8. [Masalah yang Pernah Ditemui & Solusinya](#8-masalah-yang-pernah-ditemui--solusinya)
9. [File & Direktori](#9-file--direktori)

---

## 1. Gambaran Umum

Scraper ini mengambil data detail dosen dari portal PDDikti (`pddikti.kemdiktisaintek.go.id`) menggunakan Selenium + Firefox headless.

Data yang diambil:
- **Profil** — nama, jenis kelamin, PT, prodi, jabatan fungsional, pendidikan tertinggi, ikatan kerja, status aktif
- **Riwayat Pendidikan** — riwayat studi formal (S1, S2, S3)
- **Riwayat Mengajar** *(mode --full)* — mata kuliah per semester akademik
- **Penelitian** *(mode --full)* — daftar judul penelitian + tahun
- **Pengabdian Masyarakat** *(mode --full)* — daftar judul pengabdian + tahun
- **Publikasi Karya** *(mode --full)* — daftar publikasi + jenis + tahun
- **HKI/Paten** *(mode --full)* — daftar HKI/paten (jika ada)

---

## 2. Arsitektur & Alur Kerja

### 2.1 Scraper Tunggal (`scrape_pddikti_detaildosen.py`)

```
1. Buka halaman pencarian:
   https://pddikti.kemdiktisaintek.go.id/search/[NAMA] [PT]

2. Klik tab "Dosen" pada hasil pencarian

3. Ambil semua link /detail-dosen/ yang muncul
   → Jika 1 link: langsung pakai
   → Jika >1: cocokkan NIDN dengan URL, atau ambil yang pertama

4. Buka URL detail dosen

5. Scrape profil dari body text (via regex)

6. Scrape riwayat pendidikan dari tabel halaman utama (selalu)

7. (Jika --full) Scrape tab-tab portofolio:
   - Penelitian
   - Riwayat Mengajar
   - Pengabdian Masyarakat
   - Publikasi Karya
   - HKI/Paten

8. Simpan ke outs/dosen/[kode_pt]/[nidn]_[nama].json
```

### 2.2 Batch Scraper (`scrape_pddikti_batch_dosen.py`)

```
1. Baca semua file outs/[kode_pt]/*_detailprodi.json
   → Kumpulkan dosen unik per NIDN (prioritas) / NUPTK (fallback)
   → Jika NIDN sama muncul di banyak prodi, pakai data semester terbaru

2. Filter dosen yang sudah ada di outs/dosen/

3. Scrape satu per satu (dengan 1 instance browser)

4. Gagal → catat ke outs/dosen/_failed.json
   → Bisa di-retry dengan --retry-failed

5. Abort otomatis jika N kali gagal berturut-turut (default N=10)
```

---

## 3. Penggunaan

### 3.1 Scraper Tunggal

```bash
# Mode default: profil + riwayat pendidikan (~30 detik)
python utils/scrape_pddikti_detaildosen.py \
  --nama "YULIA FITRI" \
  --pt "UNIVERSITAS MUHAMMADIYAH RIAU"

# Dengan NIDN (lebih akurat jika ada beberapa hasil)
python utils/scrape_pddikti_detaildosen.py \
  --nama "YULIA FITRI" \
  --pt "UNIVERSITAS MUHAMMADIYAH RIAU" \
  --nidn "1007078501"

# Mode full: semua data (~2-3 menit)
python utils/scrape_pddikti_detaildosen.py \
  --nama "YULIA FITRI" \
  --pt "UNIVERSITAS MUHAMMADIYAH RIAU" \
  --nidn "1007078501" \
  --full

# Dengan data tambahan dari sumber lain (mengisi jika tidak ada di halaman)
python utils/scrape_pddikti_detaildosen.py \
  --nama "YULIA FITRI" \
  --pt "UNIVERSITAS MUHAMMADIYAH RIAU" \
  --nidn "1007078501" \
  --nuptk "2039763664230363" \
  --pendidikan "S2" \
  --status "Aktif" \
  --full

# Debug: tampilkan browser (tidak headless)
python utils/scrape_pddikti_detaildosen.py \
  --nama "YULIA FITRI" \
  --pt "UNIVERSITAS MUHAMMADIYAH RIAU" \
  --debug
```

**Argumen:**

| Argumen | Keterangan | Default |
|---------|-----------|---------|
| `--nama` | Nama lengkap dosen *(wajib)* | — |
| `--pt` | Nama perguruan tinggi *(wajib)* | — |
| `--nidn` | NIDN untuk disambiguasi & nama file | `""` |
| `--nuptk` | NUPTK (dari data homebase prodi) | `""` |
| `--pendidikan` | Pendidikan terakhir, e.g. `S2`, `S3` | `""` |
| `--status` | Status dosen, e.g. `Aktif` | `""` |
| `--full` | Scrape semua tab (mengajar, penelitian, dst) | `False` |
| `--debug` | Tampilkan browser (tidak headless) | `False` |

### 3.2 Batch Scraper

```bash
# Scrape semua dosen (resumable — skip yang sudah ada)
python utils/scrape_pddikti_batch_dosen.py

# Filter satu PT saja
python utils/scrape_pddikti_batch_dosen.py --pt-kode 061008

# Retry dosen yang sebelumnya gagal
python utils/scrape_pddikti_batch_dosen.py --retry-failed

# Dry run — tampilkan daftar tanpa scrape
python utils/scrape_pddikti_batch_dosen.py --dry-run

# Batasi jumlah (untuk testing)
python utils/scrape_pddikti_batch_dosen.py --limit 5

# Tampilkan ringkasan progress
python utils/scrape_pddikti_batch_dosen.py --status

# Mode full (scrape semua tab, lebih lambat)
python utils/scrape_pddikti_batch_dosen.py --full

# Ubah threshold abort (default 10)
python utils/scrape_pddikti_batch_dosen.py --max-fail 5

# Paralel — bagi beban ke 2 proses (jalankan di terminal berbeda)
python utils/scrape_pddikti_batch_dosen.py --shard 0 --total-shards 2
python utils/scrape_pddikti_batch_dosen.py --shard 1 --total-shards 2
```

**Argumen Batch:**

| Argumen | Keterangan | Default |
|---------|-----------|---------|
| `--pt-kode` | Filter PT tertentu, e.g. `061008` | semua PT |
| `--retry-failed` | Retry dosen dari `_failed.json` | `False` |
| `--dry-run` | Tampilkan daftar tanpa scrape | `False` |
| `--limit N` | Batasi jumlah scrape (testing) | `0` = unlimited |
| `--full` | Scrape semua tab | `False` |
| `--max-fail N` | Abort jika N kali gagal berturut-turut | `10` |
| `--shard I` | Index shard (0-based) untuk paralel | `0` |
| `--total-shards N` | Total shard untuk paralel | `1` |
| `--status` | Tampilkan progress lalu keluar | `False` |

---

## 4. Struktur Output JSON

Contoh output `outs/dosen/061008/1007078501_YULIA_FITRI.json`:

```json
{
  "url_pencarian": "https://pddikti.kemdiktisaintek.go.id/search/YULIA%20FITRI%20UNIVERSITAS%20MUHAMMADIYAH%20RIAU",
  "profil": {
    "Nama": "YULIA FITRI",
    "Jenis Kelamin": "Perempuan",
    "Perguruan Tinggi": "Universitas Muhammadiyah Riau",
    "Program Studi": "Fisika",
    "Jabatan Fungsional": "Lektor",
    "Pendidikan Tertinggi": "S2",
    "Ikatan Kerja": "Dosen Tetap",
    "Status Aktif": "Aktif"
  },
  "riwayat_pendidikan": [
    {
      "Perguruan Tinggi": "Institut Teknologi Bandung",
      "Gelar Akademik": "Magister Sains",
      "Tahun": "2011",
      "Jenjang": "S2"
    }
  ],
  "riwayat_mengajar": {
    "2025/2026 Ganjil": [
      {
        "Nama Mata kuliah": "KERJA PRAKTEK",
        "Kode Kelas": "40203701",
        "Nama Kelas": "16371",
        "Perguruan Tinggi": "Universitas Muhammadiyah Riau"
      }
    ],
    "2024/2025 Genap": [ ... ]
  },
  "penelitian": [
    {
      "No": "1",
      "Judul Penelitian": "...",
      "Tahun": "2024"
    }
  ],
  "pengabdian": [
    {
      "No": "1",
      "Judul Pengabdian Masyarakat": "...",
      "Tahun": "2023"
    }
  ],
  "publikasi": [
    {
      "No": "1",
      "Judul Karya": "...",
      "Jenis Karya": "Prosiding seminar internasional",
      "Tahun": "2024"
    }
  ],
  "hki_paten": [],
  "raw_sections": {},
  "_tabs_found": [
    "Riwayat Pendidikan",
    "Riwayat Mengajar",
    "Penelitian",
    "Pengabdian Masyarakat",
    "Publikasi Karya",
    "HKI/Paten"
  ],
  "input": {
    "nama": "YULIA FITRI",
    "pt": "UNIVERSITAS MUHAMMADIYAH RIAU",
    "nidn": "1007078501",
    "nuptk": "",
    "pendidikan": "",
    "status": ""
  }
}
```

**Catatan field:**
- `url_pencarian` — URL search disimpan sebagai referensi re-scrape di masa depan (stabil, berbasis nama). URL detail **tidak** disimpan karena session-based (berubah tiap sesi).
- `riwayat_mengajar` — dict: key = label semester (`"2025/2026 Ganjil"`), value = list matkul
- `_tabs_found` — daftar tab yang terdeteksi di halaman (untuk debugging)
- `raw_sections` — tabel yang tidak bisa diklasifikasikan (biasanya kosong)

---

## 5. Perubahan Struktur Website PDDikti (2025)

Ini adalah temuan penting dari sesi debugging yang perlu diketahui agar scraper tetap bisa dipertahankan ke depan.

### 5.1 URL Detail Dosen — Session-Based

**Perilaku lama:** URL detail dosen relatif stabil.

**Perilaku baru (2025):** URL detail bersifat **session-based** — berubah setiap sesi baru. Contoh:
```
https://pddikti.kemdiktisaintek.go.id/detail-dosen/fEgwzhmVSPAA6mOpIWSejZVUUf-men...
```
URL yang sama akan mengembalikan "Terjadi Kesalahan" jika dibuka di sesi lain.

**Dampak:** URL detail **tidak boleh disimpan/di-cache**. Setiap scrape harus mulai dari pencarian ulang.

**Penanganan di scraper:** `url_pencarian` (berbasis nama, stabil) disimpan, bukan `url_detail`.

### 5.2 Label Field Profil Berubah

| Label Lama | Label Baru (2025) | Key di JSON |
|-----------|-------------------|-------------|
| `Pendidikan Tertinggi` | `Pendidikan Terakhir` | `Pendidikan Tertinggi` |
| `Ikatan Kerja` | `Status Ikatan Kerja` | `Ikatan Kerja` |
| `Status Aktif` | `Status Aktivitas` | `Status Aktif` |

Scraper menggunakan mapping tabel (bukan hardcode label) sehingga mendukung kedua versi:
```python
profil_keys_map = {
    "Pendidikan Terakhir":  "Pendidikan Tertinggi",   # label baru
    "Pendidikan Tertinggi": "Pendidikan Tertinggi",   # label lama
    "Status Ikatan Kerja":  "Ikatan Kerja",           # label baru
    ...
}
```

### 5.3 Header Kolom Tabel Mengajar Berubah

| Header Lama | Header Baru (2025) |
|------------|-------------------|
| `Mata Kuliah` | `Nama Mata kuliah` *(perhatikan huruf kecil 'k')* |
| `SKS` | *(tidak ada)* |
| `Kelas` | `Kode Kelas` + `Nama Kelas` *(dipisah jadi 2 kolom)* |
| — | `Perguruan Tinggi` *(kolom baru)* |

### 5.4 Semua Tab Dirender Sekaligus di DOM

**Perilaku lama:** Konten tab dimuat secara dinamis saat diklik (lazy loading).

**Perilaku baru (2025):** Seluruh konten semua tab — termasuk **semua semester riwayat mengajar** — sudah ada di DOM sejak halaman pertama kali dimuat. Tab selector hanya berfungsi sebagai toggle visibility CSS.

**Dampak kritis:**
- `element.text` (Selenium) pada elemen tersembunyi mengembalikan string kosong `""` — tabel yang tidak aktif tampak tidak memiliki header.
- Solusi: gunakan `element.get_attribute("textContent")` yang membaca DOM langsung tanpa memedulikan visibility.

**Implikasi pada scraping riwayat mengajar:**
- Tidak perlu klik tiap semester satu per satu (dulu diperlukan untuk trigger lazy load).
- Cukup klik tab "Riwayat Mengajar" sekali, lalu ambil semua tabel mengajar sekaligus dari DOM.
- 5 tabel di DOM = 5 semester (urutan tabel di DOM = urutan semester di selector).
- Pasangkan `semester_labels[i]` → `mengajar_tables[i]` berdasarkan urutan.

### 5.5 Elemen Semester Selector Multiline

**Masalah:** Fungsi `_collect_semester_items` yang lama menangkap container element yang berisi teks semua semester sekaligus (teks multi-baris):
```
2025/2026 Ganjil
2024/2025 Genap
2024/2025 Ganjil
...
```
`re.match()` cocok karena string dimulai dengan pola semester, sehingga container ini ikut masuk ke daftar.

**Solusi:** Filter elemen yang mengandung `\n` — semester item valid selalu single-line:
```python
if "\n" not in txt and SEM_PATTERN.match(txt) and el.is_displayed():
    ...
```

---

## 6. Detail Teknis Scraping

### 6.1 `_el_text()` — Membaca Teks Elemen Hidden

Fungsi helper kritis yang ditambahkan untuk menangani elemen non-visible:

```python
def _el_text(el):
    txt = el.text.strip()
    if not txt:
        try:
            txt = (el.get_attribute("textContent") or "").strip()
        except Exception:
            pass
    return txt
```

- `el.text` → kosong untuk elemen hidden
- `el.get_attribute("textContent")` → membaca DOM langsung, bekerja untuk semua elemen

Digunakan di `get_table_as_list()` dan `scrape_tables_on_page()`.

### 6.2 Deteksi Tabel Mengajar

Tabel mengajar diidentifikasi dengan mencocokkan header kolom:

```python
MENGAJAR_HEADERS = [
    "mata kuliah", "sks", "kelas", "matkul",
    "nama mata kuliah", "kode mata kuliah", "nama matakuliah",
    "kode kelas", "nama kelas"   # header baru 2025
]
```

Filter ketat untuk section lain:
- **Riwayat pendidikan**: harus ada `"gelar"` atau `"jenjang"`, dan **tidak** ada `"mata kuliah"` / `"kode kelas"`
- **Pengabdian**: harus ada `"judul pengabdian masyarakat"` atau `"pengabdian masyarakat"`
- **Publikasi**: harus ada `"judul karya"` atau `"jenis karya"`
- **HKI/Paten**: harus ada `"hki"` / `"paten"` / `"hak kekayaan"` / `"judul hki"`

### 6.3 Scraping Profil via Regex

Profil diambil dari `body.text` menggunakan regex:
```python
pattern = rf"(?:^|\n){re.escape(label)}\s*[:\n]\s*([^\n]+)"
```

Pola ini mencocokkan format:
- `Nama: YULIA FITRI` (kolom-nilai dalam satu baris)
- `Nama\nYULIA FITRI` (label dan nilai di baris terpisah — format baru 2025)

### 6.4 Identifikasi Dosen dalam Batch

Identifier unik (UID) untuk tiap dosen:
1. **NIDN** (prioritas utama) — dosen tetap biasanya punya NIDN
2. **NUPTK** (fallback) — dosen tidak tetap / tanpa NIDN
3. **Skip** — jika keduanya kosong (tidak bisa diidentifikasi)

Jika NIDN yang sama muncul di banyak file detailprodi (mengajar di beberapa prodi), data dari **semester paling baru** yang dipakai (tahun akademik tertinggi).

### 6.5 Nama File Output

```
outs/dosen/[kode_pt]/[uid]_[NAMA_UPPERCASE_UNDERSCORED].json
```

Contoh:
```
outs/dosen/061008/1007078501_YULIA_FITRI.json
outs/dosen/061008/no_nidn_2039763664230363_AHMAD_FAUZI.json   ← jika pakai NUPTK
```

---

## 7. Mekanisme Fail-Safe

### 7.1 Abort Otomatis (--max-fail)

Jika sejumlah N kegagalan terjadi **berturut-turut** tanpa ada satu pun sukses di antaranya, seluruh proses batch dihentikan. Counter direset ke 0 setiap ada scrape yang sukses.

```
[ABORT] 10 kegagalan berturut-turut — proses dihentikan.
```

Ini untuk mendeteksi situasi seperti:
- Website PDDikti sedang down / berubah struktur
- IP diblokir / rate-limited
- Browser crash berulang

Threshold default: **10**. Ubah dengan `--max-fail N`.

### 7.2 Resume & Retry

- Scrape **resumable** — setiap run otomatis skip dosen yang sudah ada filenya.
- Gagal → dicatat ke `outs/dosen/_failed.json`.
- Retry dengan `--retry-failed` — hanya scrape yang ada di failed list.

### 7.3 Restart Browser Otomatis

Jika error mengandung kata `"session"` atau `"webdriver"` (indikasi browser crash), driver di-quit dan diinisialisasi ulang sebelum lanjut ke dosen berikutnya.

### 7.4 Log Persisten

Semua aktivitas dicatat ke `outs/dosen/_batch.log` dengan timestamp. Log ini append-only dan tidak terhapus antar run.

---

## 8. Masalah yang Pernah Ditemui & Solusinya

### 8.1 Tabel Mengajar Tidak Terdeteksi (Nol Data)

**Gejala:** Log menunjukkan 5 semester ditemukan di dropdown tapi semua mengembalikan 0 matkul.

**Penyebab:** Tabel mengajar ada di DOM tapi `el.text` mengembalikan `""` untuk elemen hidden, sehingga header tabel tampak kosong dan dilewati oleh `scrape_tables_on_page`.

**Solusi:** Ganti `el.text.strip()` dengan fungsi `_el_text()` yang fallback ke `get_attribute("textContent")`.

### 8.2 Riwayat Pendidikan Kelebihan Data (23 baris, harusnya 2)

**Gejala:** `riwayat_pendidikan` berisi baris-baris dari tabel mengajar.

**Penyebab:** Filter lama menggunakan `"perguruan tinggi"` untuk mendeteksi tabel pendidikan. Tabel mengajar baru (2025) juga punya kolom `Perguruan Tinggi`, sehingga ikut lolos filter.

**Solusi:** Filter riwayat pendidikan diperketat — wajib ada kolom `"Gelar"` atau `"Jenjang"`, dan **tidak** ada `"Mata kuliah"` atau `"Kode Kelas"`.

### 8.3 Pengabdian/Publikasi/HKI Kelebihan Data (47 baris, harusnya 10)

**Gejala:** Setelah fix `_el_text`, tiba-tiba pengabdian/publikasi/HKI berisi semua tabel dari semua tab (mengajar + pendidikan + lainnya).

**Penyebab:** Setelah `textContent` diaktifkan, semua tabel di DOM terbaca tanpa filter, termasuk tabel tab lain yang sebelumnya dianggap tidak ada karena hidden.

**Solusi:** Tambahkan filter ketat berbasis header spesifik per section (lihat 6.2).

### 8.4 Semester Selector Menangkap Container

**Gejala:** Log menunjukkan `[*] Klik semester: '2025/2026 Ganjil\n2024/2025 Genap\n...'` — satu klik memuat teks semua semester.

**Penyebab:** `re.match()` cocok dengan teks yang *dimulai* dengan pola semester, termasuk container yang berisi semua semester.

**Solusi:** Tambahkan kondisi `"\n" not in txt` sebelum match.

### 8.5 URL Detail Expired

**Gejala:** Halaman menampilkan "Terjadi Kesalahan" untuk semua field biodata.

**Penyebab:** URL detail dosen bersifat session-based — tidak bisa digunakan kembali di sesi lain.

**Solusi:** Jangan cache URL detail. Selalu ambil URL baru melalui alur pencarian (`url_pencarian`).

### 8.6 Data Publikasi Anomali

**Gejala:** Tabel publikasi dosen Fisika berisi makalah akuntansi/keuangan dari peneliti lain.

**Penyebab:** Ini adalah masalah **kualitas data PDDikti**, bukan bug scraper. PDDikti kadang mengasosiasikan publikasi dari dosen lain dengan profil yang sedang dilihat.

**Penanganan:** Tidak ada yang bisa dilakukan di level scraper. Tandai sebagai known issue; validasi data perlu dilakukan di level post-processing.

---

## 9. File & Direktori

```
chifoo_backend/
├── utils/
│   ├── scrape_pddikti_detaildosen.py    ← scraper tunggal
│   ├── scrape_pddikti_batch_dosen.py    ← batch orchestrator
│   └── outs/
│       ├── [kode_pt]/                   ← input: file detailprodi (dari scraper prodi)
│       │   └── [kode_pt]_*_detailprodi.json
│       └── dosen/                       ← output: file detail dosen
│           ├── [kode_pt]/
│           │   └── [nidn]_[nama].json
│           ├── _failed.json             ← dosen yang gagal di-scrape
│           └── _batch.log              ← log aktivitas batch
└── docs/
    └── detail_dosen_scrape.md          ← dokumen ini
```

### Dependensi

```
selenium
firefox (binary: /snap/firefox/current/usr/lib/firefox/firefox)
geckodriver (harus tersedia di PATH)
```

### Inisialisasi Browser

```python
options = Options()
options.add_argument("--headless")
options.add_argument("--window-size=1920,1080")
options.binary_location = "/snap/firefox/current/usr/lib/firefox/firefox"
driver = webdriver.Firefox(options=options)
```

Pastikan `geckodriver` tersedia di PATH. Pada server Ubuntu, biasanya diinstall via:
```bash
apt install firefox-geckodriver
# atau download manual dari https://github.com/mozilla/geckodriver/releases
```

---

*Terakhir diperbarui: Maret 2026 — berdasarkan pengujian dengan dosen YULIA FITRI (NIDN 1007078501), Universitas Muhammadiyah Riau*
