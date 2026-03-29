# Sinkronisasi Detail Dosen dari PDDikti

## Sumber Data

LINK_SUMBER: https://pddikti.kemdiktisaintek.go.id/

## Tujuan

Melengkapi data profil individu dosen pada tabel `universities_profildosen` dan
mengisi riwayat pendidikan pada tabel `universities_riwayatpendidikandosen`,
berdasarkan data detail yang tersedia di halaman dosen PDDikti.

## Prasyarat

- Tabel `universities_profildosen` sudah terisi data dasar dosen (NIDN/NUPTK, nama)
  — biasanya hasil dari `sync_prodi_dosen.py` (langkah 6: tab Tenaga Pendidik)
- Tabel `universities_perguruantinggi` sudah ada data PT beserta `nama` yang sesuai PDDikti

## Script

```
utils/pddikti/sync_detail_dosen.py
```

Bergantung pada scraper:
```
utils/pddikti/scrape_pddikti_detaildosen.py
```

## Langkah-langkah

### 1. Baca daftar dosen dari database

Ambil daftar dosen dari `universities_profildosen` berdasarkan `perguruan_tinggi_id`
(lookup dari `kode_pt`). Setiap dosen memiliki: `id`, `nidn`, `nuptk`, `nama`.

### 2. Cari halaman detail dosen di PDDikti

Untuk tiap dosen:
- Buka halaman pencarian: `https://pddikti.kemdiktisaintek.go.id/search/[nama dosen] [nama PT]`
- Klik tab **"Dosen"** pada hasil pencarian
- Ambil link **"Lihat Detail"** yang mengarah ke `/detail-dosen/...`
- Jika ada lebih dari satu hasil, cocokkan dengan NIDN jika tersedia
- URL detail bersifat **session-based** (berubah setiap sesi), tidak disimpan ke DB —
  yang disimpan adalah `url_pencarian` (stabil, berbasis nama)

### 3. Scrape halaman detail dosen

Buka halaman `/detail-dosen/...` dan ekstrak:

**Profil** (dari body text via regex):
| Field PDDikti | Kolom DB (`universities_profildosen`) |
|---|---|
| Nama | nama |
| Jenis Kelamin | jenis_kelamin (`L`/`P`) |
| Jabatan Fungsional | jabatan_fungsional |
| Pendidikan Terakhir / Pendidikan Tertinggi | pendidikan_tertinggi (`s1`/`s2`/`s3`/`profesi`) |
| Status Ikatan Kerja / Ikatan Kerja | ikatan_kerja (`tetap`/`tidak_tetap`) |
| Status Aktivitas / Status Aktif | status |
| NUPTK | nuptk (hanya diupdate jika kosong) |
| URL pencarian | url_pencarian |
| Waktu scrape | scraped_at |

**Riwayat Pendidikan** (dari tabel pertama halaman):
| Kolom Tabel PDDikti | Kolom DB (`universities_riwayatpendidikandosen`) |
|---|---|
| Perguruan Tinggi | perguruan_tinggi_asal |
| Gelar Akademik | gelar |
| Jenjang | jenjang (mapped: S1→s1, S2→s2, S3→s3, dst.) |
| Tahun | tahun_lulus |
| — (auto-detect dari nama PT) | is_luar_negeri |

### 4. Update database

- **UPDATE** `universities_profildosen`: semua field profil di atas
- **DELETE + INSERT** `universities_riwayatpendidikandosen`: hapus riwayat lama milik dosen tersebut, lalu insert ulang dari hasil scrape terbaru
- Commit tiap satu dosen (bukan batch) agar partial success tidak hilang

### 5. Ulangi untuk semua dosen dalam PT

Jeda 3 detik antar dosen untuk menghindari rate-limit PDDikti.

## Penggunaan Script

```bash
# Sync semua dosen satu PT
python utils/pddikti/sync_detail_dosen.py --kode_pt 064167

# Sync satu dosen berdasarkan NIDN
python utils/pddikti/sync_detail_dosen.py --kode_pt 064167 --nidn 0610107606

# Preview tanpa menulis ke DB
python utils/pddikti/sync_detail_dosen.py --kode_pt 064167 --dry-run

# Batasi jumlah dosen yang diproses
python utils/pddikti/sync_detail_dosen.py --kode_pt 064167 --limit 5
```

## Catatan

- Script berjalan **mode default** (profil + riwayat pendidikan saja). Data lain
  (penelitian, pengabdian, publikasi, HKI) tersedia di `scrape_pddikti_detaildosen.py`
  dengan flag `--full`, namun belum diintegrasikan ke script sync ini.
- Dosen yang tidak ditemukan di PDDikti di-skip (tidak dihapus dari DB).
- Satu browser Firefox headless dibuka untuk seluruh proses, ditutup di akhir.
