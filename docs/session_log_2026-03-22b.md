# Session Log — Halaman Afiliasi Perguruan Tinggi SINTA

> Tanggal  : 2026-03-22 (sesi kedua)
> Scope    : Backend API + Frontend halaman `/sinta/afiliasi`
> Repo     : chifoo_backend · chifoo_frontend

---

## A. Latar Belakang

Halaman `/sinta/afiliasi` sebelumnya hanya berupa placeholder "Segera Hadir".
Pada sesi ini dibangun menjadi halaman penuh yang menampilkan profil dan peringkat
PTMA (Perguruan Tinggi Muhammadiyah & Aisyiyah) berdasarkan data SINTA resmi,
mencakup skor, metrik publikasi per database indeks, distribusi kuartil, dan cluster.

---

## B. Perubahan Backend

### B.1 · Serializer baru (`apps/universities/serializers.py`)

Ditambahkan 4 serializer:

| Serializer | Fungsi |
|---|---|
| `SintaClusterMinSerializer` | Ringkasan cluster (nama, total_score, 6 skor komponen) |
| `SintaTrendTahunanSerializer` | Tren output per tahun (scopus, research, service) |
| `SintaWcuTahunanSerializer` | WCU analysis per tahun (5 bidang + overall) |
| `SintaAfiliasiListSerializer` | Daftar/ranking — semua metrik tanpa logo & trend |
| `SintaAfiliasiDetailSerializer` | Detail lengkap — tambah logo_base64, trend, WCU |

**Field tambahan `pt_logo`** pada `SintaAfiliasiListSerializer`:
```python
pt_logo = serializers.SerializerMethodField()

def get_pt_logo(self, obj):
    logo = obj.perguruan_tinggi.logo
    return logo.url if logo else ''
```
Mengembalikan **path relatif** (misal `/media/logos/UMS.jpg`) tanpa `build_absolute_uri`,
agar URL tidak ter-hardcode ke `localhost` saat production.

### B.2 · ViewSet baru (`apps/universities/views.py`)

```python
class SintaAfiliasiViewSet(PublicReadAdminWriteMixin, viewsets.ReadOnlyModelViewSet):
    queryset = SintaAfiliasi.objects
        .select_related('perguruan_tinggi', 'cluster')
        .prefetch_related('trend_tahunan', 'wcu_tahunan')
        .order_by('-sinta_score_overall')
```

Endpoint tersedia:
- `GET /api/sinta-afiliasi/` — list dengan filter, search, ordering
- `GET /api/sinta-afiliasi/{id}/` — detail (termasuk logo_base64, trend, WCU)
- `GET /api/sinta-afiliasi/stats/` — agregat: total PT, penulis, dok Scopus/GScholar/Garuda, distribusi cluster

**Filter:** `cluster__cluster_name__icontains`
**Search:** nama, singkatan, kota, provinsi
**Ordering:** sinta_score_overall, sinta_score_3year, scopus_dokumen, scopus_sitasi, gscholar_dokumen, jumlah_authors, cluster__total_score, nama_sinta

### B.3 · URL routing (`apps/universities/urls.py`)

```python
router.register(r'sinta-afiliasi', SintaAfiliasiViewSet, basename='sinta-afiliasi')
```

### B.4 · Media URL serving (`ptma/urls.py`)

**Masalah:** URL `/media/logos/...` mengembalikan 404 karena Django tidak otomatis
melayani file media tanpa konfigurasi eksplisit di `urls.py`.

**Solusi:**
```python
urlpatterns = [
    ...
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) \
  + static(settings.MEDIA_URL,  document_root=settings.MEDIA_ROOT)
```

---

## C. Perubahan Frontend

### C.1 · Komponen baru (`sinta-afiliasi.component.ts`)

**Struktur halaman:**

| Seksi | Isi |
|---|---|
| Hero banner | Stats bar (total PT, penulis, dok Scopus/GScholar/Garuda, rerata skor) + mini bar chart distribusi cluster (klik = filter) |
| Toolbar | Search real-time (debounce 350ms), filter pill per cluster, dropdown sort |
| Ranking cards | Rank badge, logo PT, nama + lokasi, badge cluster, tag metrik ringkas, skor ring SVG proporsional |
| Modal detail | Header berwarna per cluster, logo besar, 4 skor SINTA, tab per database indeks, distribusi kuartil Q1–Q4, skor cluster 6 komponen, ringkasan SDM |

**Fitur teknis:**
- `logoSrc(pt)` — helper menggabungkan `MEDIA + pt.pt_logo` sebagai fallback ketika `logo_base64` kosong
- Modal: lazy load detail (`/api/sinta-afiliasi/{id}/`) hanya saat diklik, cache ke array `data[]`
- Skor ring: SVG circle `stroke-dasharray` proporsional terhadap PT dengan skor tertinggi
- Scroll lock saat modal terbuka (`document.body.style.overflow = 'hidden'`)

### C.2 · Environment (`environment.ts` / `environment.prod.ts`)

Tambah field `mediaUrl` untuk prefix URL file media:

```typescript
// environment.ts (development)
mediaUrl: 'http://localhost:8000'

// environment.prod.ts (production)
mediaUrl: 'https://chifoo.biroti-ums.id'
```

### C.3 · Layout width seragam

Semua halaman SINTA diubah dari `max-width: 1100–1200px` → **`max-width: 1400px`**
agar lebar konsisten dengan halaman Dashboard dan Perguruan Tinggi:

| File | Sebelum | Sesudah |
|---|---|---|
| `sinta.component.ts` | 1200px | 1400px |
| `sinta-afiliasi.component.ts` | 1200px | 1400px |
| `sinta-cluster.component.ts` | 1200px | 1400px |
| `pages.ts` (placeholder) | 1100px | 1400px |
| `sinta-jurnal.component.ts` | — | sudah 1400px |

### C.4 · Perbaikan UI lainnya

- **Badge "Segera Hadir"** dihapus dari card Afiliasi dan Cluster di halaman SINTA overview
- **Placeholder logo** — teks singkatan (UMS, UAD, dll.) diganti ikon SVG kampus abu-abu
- **Logo fallback** — urutan prioritas: `logo_base64` → `pt_logo` (URL) → ikon SVG

---

## D. Kendala & Solusi

| Kendala | Penyebab | Solusi |
|---|---|---|
| URL logo pakai `localhost:8000` di production | `build_absolute_uri()` menggunakan host request | Kembalikan path relatif saja dari serializer, frontend prefix dengan `environment.mediaUrl` |
| `/media/logos/` 404 di backend | `urls.py` hanya mendaftarkan `STATIC_URL`, belum `MEDIA_URL` | Tambah `+ static(MEDIA_URL, document_root=MEDIA_ROOT)` |
| Logo tidak tampil di lokal | 165 file logo di `public/media/logos/` semua **0 byte** (kosong) | File logo asli hanya ada di production server — perlu rsync dari production |
| Folder `public/media/logos/` belum ada | Baru dibuat saat sesi ini | `mkdir -p public/media/logos/` |

---

## E. Status Logo per Environment

| Environment | File logo | Aksesibel | Tampil di UI |
|---|---|---|---|
| **Production** (`chifoo.biroti-ums.id`) | ✅ Ada (asli) | ✅ HTTP 200 | ⏳ Tunggu deploy frontend |
| **Lokal** (`localhost:8000`) | ⚠️ Ada tapi 0 byte | ❌ Gambar kosong | ❌ Tidak tampil |

**Solusi lokal:** Sync file logo dari production:
```bash
rsync -av user@server:/path/public/media/logos/ \
  /home/ubuntu/_chifoo/chifoo_backend/public/media/logos/
```

---

## F. Commits

| Repo | Hash | Pesan |
|---|---|---|
| backend | `e5cc752` | feat(sinta): tambah endpoint API afiliasi PT — SintaAfiliasiViewSet |
| backend | `0e8a071` | feat(sinta-afiliasi): tambah field pt_logo dari PerguruanTinggi |
| backend | `4b6a0db` | fix(sinta-afiliasi): pt_logo kembalikan path relatif |
| backend | `4fd48a6` | fix: tambah serving MEDIA_URL di urls.py |
| frontend | `d4739bf` | feat(sinta): halaman Afiliasi PT dan Cluster SINTA |
| frontend | `007f0f1` | fix(sinta): layout 1400px seragam, logo PT, hapus badge |
| frontend | `53c17ab` | fix(sinta-afiliasi): tambah mediaUrl di environment |

---

## G. Pending / Backlog

- [ ] Deploy frontend ke `public_html` (tunggu konfirmasi)
- [ ] Sync file logo dari production ke lokal (`rsync`)
- [ ] Integrasi data `SintaTrendTahunan` & `SintaWcuTahunan` ke modal detail (data belum di-scrape)
- [ ] Halaman `/sinta/afiliasi/{id}` — detail per PT (future)
- [ ] Pagination pada ranking list (saat ini load semua sekaligus)
