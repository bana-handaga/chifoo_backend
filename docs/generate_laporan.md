# Generate Laporan — Dokumentasi Teknis Lengkap

## Deskripsi Fitur

**Generate Laporan** adalah fitur di halaman **Laporan** (tab/accordion pertama) yang menghitung
dan menyimpan snapshot distribusi data seluruh Perguruan Tinggi Muhammadiyah & Aisyiyah (PTMA)
pada satu titik waktu tertentu. Hasil snapshot mencakup distribusi program studi, dosen (gender,
jabatan, pendidikan, status, ikatan kerja), dan tren mahasiswa aktif 7 semester terakhir — satu
baris per PT.

---

## Alur Proses (End-to-End)

```
Pengguna klik "Generate Laporan"
        │
        ▼
Frontend: generateLaporan()
  → POST /api/monitoring/snapshot-laporan/generate/
        │
        ▼
Backend: SnapshotLaporanViewSet.generate()
  → panggil _compute_snapshot()
        │
        ├─ 1. Ambil 7 semester terakhir dari DataMahasiswa
        ├─ 2. Agregasi bulk semua distribusi per PT_id
        ├─ 3. Hapus snapshot minggu ini (overwrite)
        ├─ 4. Buat SnapshotLaporan (header)
        └─ 5. bulk_create SnapshotPerPT (satu baris per PT)
        │
        ▼
Response: SnapshotLaporanSerializer (header + per_pt)
        │
        ▼
Frontend: tampilkan di tabel hasil, update riwayat
```

---

## Aturan Penyimpanan Snapshot

> **Satu snapshot per pekan (Senin–Minggu).**

- Generate ulang **dalam pekan yang sama** → snapshot lama pekan itu dihapus, diganti yang baru
- Generate di **pekan berbeda** → snapshot lama tetap tersimpan
- Maksimal **10 snapshot** ditampilkan di riwayat (query `[:10]`)
- Snapshot dapat dihapus manual melalui tombol hapus di tabel riwayat

Logika overwrite di backend (`apps/monitoring/views.py`, fungsi `_compute_snapshot`):
```python
week_start = now - timedelta(days=now.weekday())
week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
SnapshotLaporan.objects.filter(dibuat_pada__gte=week_start).delete()
```

---

## Struktur Database

### Model: `SnapshotLaporan` (header)

| Field               | Tipe        | Keterangan                                      |
|---------------------|-------------|--------------------------------------------------|
| `id`                | AutoField   | Primary key                                      |
| `dibuat_pada`       | DateTimeField | Waktu generate (auto)                           |
| `keterangan`        | CharField   | Ringkasan otomatis: "X dari Y PT aktif"          |
| `total_pt`          | IntegerField | Jumlah PT aktif saat generate                   |
| `total_pt_non_aktif`| IntegerField | Jumlah PT tidak aktif saat generate             |

### Model: `SnapshotPerPT` (detail per PT)

Satu `SnapshotLaporan` memiliki banyak `SnapshotPerPT` (relasi FK → `related_name='per_pt'`).

#### Grup kolom: Identitas PT
| Field            | Sumber                          |
|------------------|---------------------------------|
| `perguruan_tinggi` | FK ke `PerguruanTinggi`       |
| `pt_kode`        | `PerguruanTinggi.kode_pt`       |
| `pt_nama`        | `PerguruanTinggi.nama`          |
| `pt_singkatan`   | `PerguruanTinggi.singkatan`     |
| `pt_jenis`       | `PerguruanTinggi.jenis`         |
| `pt_organisasi`  | `PerguruanTinggi.organisasi_induk` |
| `pt_akreditasi`  | `PerguruanTinggi.akreditasi_institusi` |
| `pt_aktif`       | `PerguruanTinggi.is_active`     |

#### Grup kolom: Program Studi (11 kolom)
| Field                    | Keterangan                                  |
|--------------------------|----------------------------------------------|
| `total_prodi`            | Semua prodi (aktif + non-aktif)              |
| `prodi_aktif`            | Prodi dengan `is_active=True`               |
| `prodi_non_aktif`        | `total_prodi - prodi_aktif`                  |
| `prodi_s1`               | Jumlah prodi jenjang S1                     |
| `prodi_s2`               | Jumlah prodi jenjang S2                     |
| `prodi_s3`               | Jumlah prodi jenjang S3                     |
| `prodi_d3`               | Jumlah prodi jenjang D3                     |
| `prodi_d4`               | Jumlah prodi jenjang D4                     |
| `prodi_profesi`          | Jumlah prodi jenjang Profesi                |
| `prodi_sp1`              | Jumlah prodi jenjang Sp-1                   |
| `prodi_jenjang_lainnya`  | Jenjang di luar 7 kategori di atas          |

#### Grup kolom: Dosen — Ringkasan (3 kolom)
| Field               | Keterangan                                               |
|---------------------|-----------------------------------------------------------|
| `total_dosen`       | Dari `DataDosen` semester terbaru (lebih akurat dari scraping) |
| `dosen_with_detail` | Jumlah `ProfilDosen` dengan `jabatan_fungsional` terisi  |
| `dosen_no_detail`   | `total_dosen - dosen_with_detail` (belum detail)         |

> **Catatan:** `total_dosen` diambil dari `DataDosen.dosen_tetap + dosen_tidak_tetap` pada
> semester paling baru yang tersedia. Ini lebih akurat dibanding menghitung dari
> `ProfilDosen` yang merupakan hasil scraping (bisa tidak lengkap).

#### Grup kolom: Gender (3 kolom)
| Field                  | Keterangan                                          |
|------------------------|------------------------------------------------------|
| `dosen_pria`           | `ProfilDosen.jenis_kelamin = 'L'`                   |
| `dosen_wanita`         | `ProfilDosen.jenis_kelamin = 'P'`                   |
| `dosen_gender_no_info` | `max(0, total_dosen - pria - wanita)` (tidak terdata) |

#### Grup kolom: Jabatan Fungsional (5 kolom)
| Field                    | Nilai jabatan di DB              |
|--------------------------|----------------------------------|
| `dosen_profesor`         | `"Profesor"`                    |
| `dosen_lektor_kepala`    | `"Lektor Kepala"`               |
| `dosen_lektor`           | `"Lektor"`                      |
| `dosen_asisten_ahli`     | `"Asisten Ahli"`                |
| `dosen_jabatan_lainnya`  | `max(0, total - 4 kategori atas)` (termasuk kosong) |

#### Grup kolom: Pendidikan Tertinggi (5 kolom)
| Field                  | Nilai pendidikan di DB         |
|------------------------|--------------------------------|
| `dosen_pend_s3`        | `"s3"`                        |
| `dosen_pend_s2`        | `"s2"`                        |
| `dosen_pend_s1`        | `"s1"`                        |
| `dosen_pend_profesi`   | `"profesi"`                   |
| `dosen_pend_lainnya`   | `max(0, total - 4 kategori atas)` |

#### Grup kolom: Status Dosen (5 kolom)
| Field                    | Nilai status di DB              |
|--------------------------|---------------------------------|
| `dosen_aktif`            | `"Aktif"`                      |
| `dosen_tugas_belajar`    | `"TUGAS BELAJAR"`              |
| `dosen_ijin_belajar`     | `"IJIN BELAJAR"`               |
| `dosen_cuti`             | `"CUTI"`                       |
| `dosen_status_lainnya`   | `max(0, total - 4 kategori atas)` |

#### Grup kolom: Ikatan Kerja (4 kolom)
| Field                   | Nilai ikatan_kerja di DB       |
|-------------------------|--------------------------------|
| `dosen_tetap`           | `"tetap"`                     |
| `dosen_tidak_tetap`     | `"tidak_tetap"`               |
| `dosen_dtpk`            | `"dtpk"` (Tetap Perjanjian Kerja) |
| `dosen_ikatan_lainnya`  | `max(0, total - 3 kategori atas)` |

#### Grup kolom: Tren Mahasiswa Aktif — 7 Semester (14 kolom)
Kolom `mhs_label_N` berisi label teks (misal `"2023/2024 Ganjil"`), `mhs_sem_N` berisi angka.
`N=1` = semester terlama, `N=7` = semester terbaru.

```python
# Cara pengambilan 7 semester:
semesters = list(
    DataMahasiswa.objects
    .values_list('tahun_akademik', 'semester')
    .distinct()
    .order_by('-tahun_akademik', '-semester')[:7]
)
semesters_asc = list(reversed(semesters))  # lama → baru untuk kolom 1–7
```

---

## API Endpoints

| Method | URL                                               | Keterangan                          |
|--------|---------------------------------------------------|--------------------------------------|
| GET    | `/api/monitoring/snapshot-laporan/`               | Daftar 10 snapshot terbaru (list)   |
| POST   | `/api/monitoring/snapshot-laporan/generate/`      | Buat/overwrite snapshot baru        |
| GET    | `/api/monitoring/snapshot-laporan/{id}/`          | Detail snapshot + semua data per PT |
| DELETE | `/api/monitoring/snapshot-laporan/{id}/`          | Hapus snapshot                      |

### Request: Generate
```
POST /api/monitoring/snapshot-laporan/generate/
Content-Type: application/json

{ "keterangan": "opsional — jika kosong, digenerate otomatis" }
```

### Response: List Snapshot
```json
[
  {
    "id": 42,
    "dibuat_pada": "2026-03-17T09:00:00Z",
    "keterangan": "169 dari 172 PT aktif (3 PT tidak aktif)",
    "total_pt": 169,
    "total_pt_non_aktif": 3
  },
  ...
]
```

### Response: Detail Snapshot
```json
{
  "id": 42,
  "dibuat_pada": "2026-03-17T09:00:00Z",
  "keterangan": "...",
  "total_pt": 169,
  "total_pt_non_aktif": 3,
  "per_pt": [
    {
      "pt_id": 5, "pt_kode": "060046", "pt_nama": "Universitas Muhammadiyah ...",
      "pt_singkatan": "UMS", "pt_jenis": "Universitas",
      "pt_organisasi": "muhammadiyah", "pt_akreditasi": "Unggul", "pt_aktif": true,
      "total_prodi": 52, "prodi_aktif": 50, "prodi_non_aktif": 2,
      "prodi_s1": 30, "prodi_s2": 12, "prodi_s3": 4,
      "prodi_d3": 2, "prodi_d4": 1, "prodi_profesi": 1, "prodi_sp1": 0, "prodi_jenjang_lainnya": 0,
      "total_dosen": 850, "dosen_with_detail": 810, "dosen_no_detail": 40,
      "dosen_pria": 510, "dosen_wanita": 330, "dosen_gender_no_info": 10,
      "dosen_profesor": 45, "dosen_lektor_kepala": 180, "dosen_lektor": 310,
      "dosen_asisten_ahli": 200, "dosen_jabatan_lainnya": 115,
      "dosen_pend_s3": 220, "dosen_pend_s2": 580, "dosen_pend_s1": 40,
      "dosen_pend_profesi": 5, "dosen_pend_lainnya": 5,
      "dosen_aktif": 820, "dosen_tugas_belajar": 15, "dosen_ijin_belajar": 5,
      "dosen_cuti": 2, "dosen_status_lainnya": 8,
      "dosen_tetap": 750, "dosen_tidak_tetap": 60, "dosen_dtpk": 30, "dosen_ikatan_lainnya": 10,
      "mhs_label_1": "2022/2023 Ganjil", "mhs_sem_1": 18500,
      "mhs_label_2": "2022/2023 Genap",  "mhs_sem_2": 17200,
      "mhs_label_3": "2023/2024 Ganjil", "mhs_sem_3": 19100,
      "mhs_label_4": "2023/2024 Genap",  "mhs_sem_4": 17800,
      "mhs_label_5": "2024/2025 Ganjil", "mhs_sem_5": 20500,
      "mhs_label_6": "2024/2025 Genap",  "mhs_sem_6": 19200,
      "mhs_label_7": "2025/2026 Ganjil", "mhs_sem_7": 21000
    },
    ...
  ]
}
```

---

## Implementasi Backend (`apps/monitoring/views.py`)

Fungsi inti: `_compute_snapshot(keterangan='') → SnapshotLaporan`

### Langkah 1 — Ambil 7 Semester Terakhir
```python
semesters = list(
    DataMahasiswa.objects
    .values_list('tahun_akademik', 'semester')
    .distinct()
    .order_by('-tahun_akademik', '-semester')[:7]
)
semesters_asc = list(reversed(semesters))
```

### Langkah 2 — Agregasi Bulk (8 query total)
```python
# Prodi per jenjang (aktif saja)
prodi_qs = ProgramStudi.objects.filter(is_active=True)
           .values('perguruan_tinggi_id', 'jenjang').annotate(n=Count('id'))

# Total prodi (aktif + non-aktif)
prodi_total_qs = ProgramStudi.objects.values('perguruan_tinggi_id').annotate(n=Count('id'))

# Gender dosen
gender_qs = ProfilDosen.objects.values('perguruan_tinggi_id', 'jenis_kelamin').annotate(n=Count('id'))

# Dosen dengan detail jabatan
detail_qs = ProfilDosen.objects.values('perguruan_tinggi_id')
            .annotate(with_detail=Count('id', filter=Q(jabatan_fungsional__gt='')))

# Total dosen dari DataDosen (semester terbaru)
_DataDosen.objects.filter(ta=latest, sem=latest).values('perguruan_tinggi_id')
          .annotate(total=Sum('dosen_tetap') + Sum('dosen_tidak_tetap'))

# Jabatan fungsional
jabatan_qs = ProfilDosen.objects.values('perguruan_tinggi_id', 'jabatan_fungsional').annotate(n=Count('id'))

# Pendidikan tertinggi
pendidikan_qs = ProfilDosen.objects.values('perguruan_tinggi_id', 'pendidikan_tertinggi').annotate(n=Count('id'))

# Status dosen
status_qs = ProfilDosen.objects.values('perguruan_tinggi_id', 'status').annotate(n=Count('id'))

# Ikatan kerja
ikatan_qs = ProfilDosen.objects.values('perguruan_tinggi_id', 'ikatan_kerja').annotate(n=Count('id'))

# Mahasiswa aktif per (PT, semester)
mhs_qs = DataMahasiswa.objects.filter(tahun_akademik__in=ta_list, semester__in=sem_list)
         .values('perguruan_tinggi_id', 'tahun_akademik', 'semester')
         .annotate(total=Sum('mahasiswa_aktif'))
```

### Langkah 3 — Overwrite Pekan Ini
```python
week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
SnapshotLaporan.objects.filter(dibuat_pada__gte=week_start).delete()
```

### Langkah 4 — Buat Header & Bulk Insert Detail
```python
snap = SnapshotLaporan.objects.create(keterangan=keterangan, total_pt=..., total_pt_non_aktif=...)
SnapshotPerPT.objects.bulk_create(bulk)   # satu pass, tanpa N+1
```

---

## Implementasi Frontend (`statistik.component.ts`)

### State utama
```typescript
genOpen    = false;       // accordion terbuka/tutup
generating = false;       // tombol disabled saat proses
snapshots: any[] = [];    // daftar 10 snapshot terbaru
activeSnap: any  = null;  // snapshot yang sedang ditampilkan
snapLoading      = false; // loading detail snapshot
snapFilter       = '';    // filter nama PT
showNonAktif     = false; // checkbox tampilkan PT non-aktif
snapSortKey      = 'pt_nama';
snapSortAsc      = true;
snapPage         = 1;     // halaman riwayat (5 per hal)
snapResPage      = 1;     // halaman hasil tabel (5 per hal)
```

### Fungsi utama

**`loadSnapshots()`** — dipanggil saat `ngOnInit`, mengambil daftar 10 snapshot terbaru.

**`generateLaporan()`** — trigger dari tombol. Memanggil `POST .../generate/`, lalu:
- Hapus snapshot pekan ini dari list lokal
- Prepend snapshot baru ke `snapshots[]`
- Set sebagai `activeSnap` (langsung tampil di tabel)

**`loadSnap(id)`** — klik baris di tabel riwayat. Toggle: klik baris aktif = tutup.
Memanggil `GET .../snapshot-laporan/{id}/` untuk ambil data per PT.

**`filteredSnap` (getter)** — filter + sort dari `activeSnap.per_pt`:
1. Filter `pt_aktif` jika `showNonAktif = false`
2. Filter nama PT dari `snapFilter`
3. Sort berdasarkan `snapSortKey` + `snapSortAsc`

**`snapTotals` (getter)** — menghitung baris total di footer tabel dengan `reduce` dari `filteredSnap`.

**`deleteSnap(event, id)`** — hapus dengan `confirm()`, lalu filter dari `snapshots[]`.

**`exportSnap(fmt)`** — ekspor data `filteredSnap` ke format CSV, XLSX, atau PDF (cetak).

---

## Tampilan Tabel Hasil

Tabel menggunakan **header dua baris** dengan colspan per grup:

| Grup            | Kolom Header Level 2                                              | Jumlah |
|-----------------|-------------------------------------------------------------------|--------|
| Identitas PT    | PT, Org, Jenis, Akreditasi, Status                               | 5      |
| Prodi           | Total, Aktif, Non-Aktif, S1, S2, S3, D3, D4, Profesi, Sp-1, Lain | 11    |
| Dosen           | Total, Lengkap, Blm Detail                                        | 3      |
| Gender          | Pria, Wanita, No Info                                             | 3      |
| Jabatan         | Prof, LK, L, AA, Lain                                             | 5      |
| Pendidikan      | S3, S2, S1, Profesi, Lain                                         | 5      |
| Status Dosen    | Aktif, TB (Tugas Belajar), IB (Ijin Belajar), Cuti, Lain         | 5      |
| Ikatan Kerja    | Tetap, Tdk Tetap, DTPK, Lain                                      | 4      |
| Mhs Aktif 7 Sem | sem_1 … sem_7 (label otomatis dari data)                         | 7      |
| **Total**       |                                                                   | **48** |

Seluruh kolom sortable dengan klik header. Footer menampilkan total keseluruhan dari `filteredSnap`.

### Kontrol tampilan
- **Filter nama PT** — input text, filter real-time dari `activeSnap.per_pt`
- **Toggle PT non-aktif** — checkbox, default hanya tampilkan PT aktif
- **Ekspor** — CSV (dengan BOM UTF-8), XLSX (via SheetJS), PDF (print window)
- **Paginasi** — 5 PT per halaman, navigasi atas dan bawah tabel

### Catatan kaki tabel
1. **Kolom "Blm Detail"**: dihitung dari total dosen DataDosen dikurangi ProfilDosen yang
   sudah ada `jabatan_fungsional` — mencerminkan data yang belum ter-scraping dari PDDikti.
2. **Cakupan PT**: informasi jumlah PT aktif vs non-aktif dari snapshot yang dipilih.
3. **Sumber data**: pddikti.kemdiktisaintek.go.id via scraping berkala.

---

## File Terkait

| File                                               | Peran                                              |
|----------------------------------------------------|----------------------------------------------------|
| `apps/monitoring/models.py`                        | Model `SnapshotLaporan` + `SnapshotPerPT`          |
| `apps/monitoring/views.py`                         | `_compute_snapshot()` + `SnapshotLaporanViewSet`   |
| `apps/monitoring/serializers.py`                   | `SnapshotLaporanSerializer`, `SnapshotPerPTSerializer` |
| `apps/monitoring/urls.py`                          | Route: `snapshot-laporan/`, `snapshot-laporan/generate/` |
| `apps/monitoring/migrations/0002_snapshot_laporan.py` | Migrasi awal model snapshot                    |
| `apps/monitoring/migrations/0003_snapshot_perpt_flat_fields.py` | Tambah kolom flat per PT             |
| `apps/monitoring/migrations/0004_add_dosen_detail_cols.py` | Tambah kolom detail dosen                |
| `apps/monitoring/migrations/0005_add_prodi_aktif_cols.py`  | Tambah kolom prodi aktif/non-aktif       |
| `apps/monitoring/migrations/0006_snapshotlaporan_total_pt_non_aktif.py` | Tambah total_pt_non_aktif |
| `apps/monitoring/migrations/0007_snapshotperpt_dosen_gender_no_info.py` | Tambah dosen_gender_no_info |
| `chifoo_frontend/.../statistik.component.ts`       | Frontend accordion Generate Laporan                |
| `chifoo_frontend/.../api.service.ts`               | `getSnapshotList()`, `getSnapshotDetail()`, `generateSnapshot()`, `deleteSnapshot()` |

---

## Catatan Performa

- Seluruh agregasi menggunakan **bulk query** dengan `values().annotate()` — tidak ada N+1 query.
- Data per PT di-index ke dict Python (`defaultdict`) sebelum looping PT → O(1) lookup.
- `SnapshotPerPT.objects.bulk_create(bulk)` — satu INSERT untuk semua baris PT.
- Untuk ~170 PT, proses generate memakan waktu **< 1 detik** di server.

---

*Dokumentasi dibuat: Maret 2026*
