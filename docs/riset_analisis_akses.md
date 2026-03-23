# Pengaturan Akses Fitur Analisis Riset PTMA

**Tanggal**: 2026-03-23
**Terkait**: `sinta-artikel.component.ts`, `apps/universities/views.py`

---

## Latar Belakang

Fitur analisis riset (TF-IDF + LDA + Qwen2.5 LLM) membutuhkan ~2 menit CPU untuk
dijalankan pertama kali. Agar server tidak terbebani oleh request analisis berulang dari
semua user, diputuskan untuk memisahkan hak akses:

- **Membaca hasil analisis** — semua user (publik, dari cache)
- **Memicu analisis baru** — hanya administrator (`is_staff = True`)

---

## Perubahan Backend

**File**: `apps/universities/views.py`
**Action**: `riset_analisis` di `SintaScopusArtikelViewSet`

### Sebelum
```python
@action(detail=False, methods=['get'], url_path='riset-analisis')
def riset_analisis(self, request):
    # Selalu generate ulang jika cache kosong, siapapun bisa trigger
```

### Sesudah
```python
@action(detail=False, methods=['get', 'post'], url_path='riset-analisis')
def riset_analisis(self, request):
    _FULL_CACHE_KEY = 'riset_analisis_full_v1'

    # POST — hanya admin
    if request.method == 'POST':
        if not (request.user and request.user.is_staff):
            return Response({'detail': '...'}, status=403)
        cache.delete(_FULL_CACHE_KEY)   # hapus cache, lanjut generate

    # GET — baca cache, kembalikan {"ready": False} jika kosong
    if request.method == 'GET':
        cached = cache.get(_FULL_CACHE_KEY)
        if cached: return Response(cached)
        return Response({'ready': False, 'detail': 'Hubungi administrator.'})

    # Generate (hanya dicapai via POST admin)
    # ... TF-IDF, LDA, Qwen, WCU classification ...
    cache.set(_FULL_CACHE_KEY, result, timeout=604800)  # 7 hari
    return Response(result)
```

### Endpoint
| Method | URL | Akses | Keterangan |
|--------|-----|-------|------------|
| `GET` | `/api/sinta-scopus-artikel/riset-analisis/` | Publik | Baca cache, instan |
| `POST` | `/api/sinta-scopus-artikel/riset-analisis/` | Admin only | Regenerasi analisis |

### Cache
- **Key**: `riset_analisis_full_v1`
- **TTL**: 7 hari (604800 detik)
- **Invalidasi**: dihapus otomatis saat admin POST, atau ganti key secara manual
- **Backend cache**: Django default (LocMemCache di development, bisa diganti Redis di production)

---

## Perubahan Frontend

### `AuthService` (`src/app/services/auth.service.ts`)
Ditambahkan method:
```typescript
isAdmin(): boolean {
  const u = this.getCurrentUser();
  return !!(u && u.is_staff);
}
```
Membaca field `is_staff` dari objek user yang disimpan di `localStorage` saat login.

### `SintaArtikelComponent` (`sinta-artikel.component.ts`)

**Property baru:**
```typescript
risetNotReady   = false;   // cache kosong — user lihat pesan
risetRegenerating = false; // admin sedang trigger regenerasi
```

**Constructor:** `AuthService` diinjek sebagai `public auth`

**Method baru:**
```typescript
regenerateRiset(): void {
  // POST ke /api/sinta-scopus-artikel/riset-analisis/
  // Hanya bisa dipanggil jika auth.isAdmin() === true
  // Loading state: risetRegenerating = true selama proses
}
```

**Update `loadRiset()`:**
- Jika response `ready === false` → set `risetNotReady = true`, tidak set `this.riset`
- User lihat panel info, bukan error

### Tampilan berdasarkan kondisi

| Kondisi | Tampilan |
|---------|----------|
| Cache ada, semua user | Hasil analisis normal |
| Cache kosong, non-admin | Panel info: "Hubungi administrator" |
| Cache kosong, admin | Panel info kuning: "Klik Perbarui Analisis" |
| Admin, accordion terbuka | Tombol **Perbarui Analisis** (ikon refresh) di header |
| Sedang regenerasi | Loading spinner + teks "~2 menit" |
| POST dari non-admin | 403 Forbidden dari backend (tidak bisa terjadi via UI) |

---

## Alur Lengkap

```
User buka accordion "Analisis Riset"
  │
  ├─ GET /riset-analisis/
  │    ├─ Cache ada → tampil hasil ✓
  │    └─ Cache kosong → {ready: false}
  │          ├─ Non-admin → "Hubungi administrator"
  │          └─ Admin → "Klik Perbarui Analisis" + tombol muncul
  │
  └─ Admin klik "Perbarui Analisis"
       │
       ├─ POST /riset-analisis/
       │    ├─ Cek is_staff → lanjut generate
       │    ├─ TF-IDF word cloud
       │    ├─ LDA 8 topik
       │    ├─ Qwen2.5 deskripsi (~90–120 dtk)
       │    ├─ WCU classification
       │    └─ Simpan ke cache (7 hari) → return result
       │
       └─ Frontend update tampilan
```

---

## Catatan Keamanan

- Proteksi berlapis: backend cek `is_staff` secara mandiri (tidak bergantung frontend)
- Tombol "Perbarui Analisis" disembunyikan di UI untuk non-admin, tapi backend tetap
  menolak POST dari non-admin dengan `403 Forbidden`
- Field `is_staff` berasal dari Django User model, diset via Django Admin

---

## Cara Mengatur Hak Akses User

Untuk memberikan hak admin ke user:
```python
# Via Django shell
python manage.py shell
>>> from django.contrib.auth.models import User
>>> u = User.objects.get(username='nama_user')
>>> u.is_staff = True
>>> u.save()
```
Atau via Django Admin panel: `/admin/auth/user/` → centang **Staff status**.
