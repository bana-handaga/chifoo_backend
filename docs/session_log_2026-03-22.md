# Catatan Aktivitas Pengembangan — Halaman Jurnal & Cluster SINTA

> Proyek: **PTMA Monitor** (chifoo_frontend + chifoo_backend)
> Dicatat: 2026-03-22
> Dikerjakan oleh: Tim Pengembang + Claude Code (AI Assistant)

---

## BAGIAN A — Halaman Jurnal SINTA (`/sinta/jurnal`)

### A.1 · Ikhtisar Fitur

Halaman untuk menelusuri dan menganalisis jurnal-jurnal milik PTMA (Perguruan Tinggi Muhammadiyah dan Aisyiyah) yang terdaftar di SINTA. Mendukung dua mode tampilan (Card / List), filter multi-dimensi, sorting, dan popup detail jurnal.

---

### A.2 · Riwayat Perubahan Berurutan

#### [01] Penyesuaian Tampilan Mode List
- **Masalah:** Hover row kurang terlihat, tidak ada tombol sort di header, kolom P-ISSN dan E-ISSN terpisah.
- **Solusi:**
  - Perkuat warna hover row (dari `#f8fafc` → `#eef2ff` + border-left indikator)
  - Tambah tombol `jt-sort` di setiap header kolom dengan state aktif dan arrow indikator ↑↓↕
  - Gabung P-ISSN + E-ISSN dalam satu kolom `jt-issn` (tampil atas-bawah)

#### [02] Susun 3 Tautan di Bawah Logo (Sejajar)
- **Masalah:** Tautan (Website, Scholar, Garuda) ditempatkan di kolom terpisah.
- **Solusi:** Pindahkan tautan ke bawah logo, susun horizontal menggunakan `display:flex; gap:.35rem`

#### [03] Badge Garuda & Warna Latar Kolom Impact
- **Masalah:** Garuda index belum dibedakan secara visual; kolom Impact susah dibedakan.
- **Solusi:**
  - Tambah badge `🦅 Garuda` berwarna oranye di bawah tautan
  - Berikan `background: #fefce8` (kuning muda) pada kolom Impact agar berbeda

#### [04] Hapus Kolom Indeks
- **Perubahan:** Kolom "Indeks" (Scopus / Garuda) dihapus dari tabel list — informasi tersebut sudah cukup dari badge di bawah tautan logo.

#### [05] Penyesuaian Lebar Halaman
- **Masalah:** Margin kiri-kanan terlalu besar, tidak simetris dengan halaman Dashboard dan Perguruan Tinggi.
- **Solusi:** `max-width: 1200px; margin: 0 auto; padding: 0 1.25rem` — konsisten dengan layout global.

#### [06] Kolom PT — Nama Lengkap + Toggle Sort
- **Perubahan:** Kolom Perguruan Tinggi menampilkan nama lengkap (bukan hanya singkatan). Ditambah tombol sort di header PT.

#### [07] Popup Detail Jurnal
- **Fitur baru:** Klik card atau row list → tampil modal overlay dengan:
  - Logo ukuran besar (`max-height: 200px; object-fit: contain`) — tanpa upscaling
  - Info lengkap: Nama, Akreditasi, ISSN, Subject Area, Afiliasi, Impact, H5-Index, Sitasi
  - Tautan eksternal (Website, Scholar, Editor, Garuda)
  - FAB akreditasi `88px` circular gradient di sebelah kanan
  - Animasi slide-up, backdrop blur, scroll lock (`document.body.style.overflow = 'hidden'`)

#### [08] Default Mode List + Perbaikan Logo
- **Default view** diubah dari Card → **List** (`viewMode = 'list'` saat init)
- **Logo tidak tampil** → penyebab: production API belum mengembalikan field `logo_base64` (server belum pull + migrate)
- **Background Card** dibuat tipis sesuai warna akreditasi (S1=ungu, S2=biru, S3=hijau, dst.)

#### [09] FAB Akreditasi — Card View
- **Fitur:** Badge akreditasi bergaya FAB (72px circle, gradient warna) di sisi kanan setiap card
- CSS class: `.jc-grade-fab`, `.jc-grade-fab__val`, `.jc-grade-fab__lbl`, `.jc-grade-fab--s1` s/d `--s6`

#### [10] Estimasi WCU Subject Area (Backend)
- **Analisis awal:** Jurnal SINTA memiliki field `subject_area` (kategori SINTA), namun tidak ada pengelompokan standar WCU/QS.
- **Solusi hybrid ML:**
  1. **Rule-based regex** — peta kata kunci dari `subject_area` SINTA → 5 kelompok WCU (coverage 79%)
  2. **TF-IDF + Logistic Regression** (OneVsRest, char_wb ngrams) — untuk sisa 21% yang tidak tercover
  3. Cross-validation F1-Score: ~71.9%
- **5 Kelompok WCU:**
  | Kode | Label |
  |------|-------|
  | Natural Sciences | Sains Alam |
  | Engineering & Technology | Rekayasa & Teknologi |
  | Life Sciences & Medicine | Hayati & Kesehatan |
  | Social Sciences & Management | Sosial & Manajemen |
  | Arts & Humanities | Seni & Humaniora |
- **Hasil:** 976 jurnal berhasil diklasifikasi. Distribusi: Social 621, Life Sciences 198, Arts 189, Engineering 176, Natural Sciences 109.
- **File baru:** `apps/universities/management/commands/predict_wcu_area.py`

#### [11] Field `wcu_area` di Backend
- **Model:** Tambah `wcu_area = CharField(max_length=200, blank=True)` ke model `SintaJurnal`
- **Migration:** `0011_add_wcu_area_to_sintajurnal.py`
- **Serializer:** `wcu_area` ditambah ke `SintaJurnalSerializer.Meta.fields`
- **ViewSet:** `wcu_area__icontains` ke `filterset_fields`, `wcu_area` ke `ordering_fields`
- **Stats action:** Tambah `distribusi_wcu` (hitung jurnal per kelompok WCU) di endpoint `/api/sinta-jurnal/stats/`

#### [12] Filter & Kolom WCU di Frontend
- **Stats bar:** Tambah chips WCU (🔬 Sains, ⚙️ Rekayasa, 🌿 Hayati, 📊 Sosial, 🎨 Humaniora) — klik untuk filter
- **Filter row:** Dropdown "Semua Bidang" dengan 5 pilihan WCU
- **List view:** Kolom "Bidang" (`jt-wcu`) antara nama jurnal dan kolom PT — isi: ikon emoji + label singkat
- **Card view:** Tag WCU di bawah nama jurnal
- **Build params:** `if (this.filterWcu) p['wcu_area__icontains'] = this.filterWcu`

---

### A.3 · Kendala & Solusi Teknis

| Kendala | Penyebab | Solusi |
|---------|----------|--------|
| Logo tidak tampil di production | Server production belum `git pull` + migrate | Push backend ke GitHub+GitLab, instruksikan server pull |
| MySQL Lost Connection saat predict | `SintaJurnal.objects.all()` menarik kolom `logo_base64` (TEXT besar) | Ganti dengan `.objects.only('id','nama','afiliasi_teks','subject_area','wcu_area')` |
| ML memprediksi semua → Social Sciences | Class imbalance (65% training = Social) | Hybrid approach: rule-based dulu (79% coverage), ML hanya untuk sisa 21% |
| Kolom Bidang kosong di live site | Production belum punya field `wcu_area` | Backend sudah push ke git (`5a372f3`), menunggu server pull+migrate+predict |
| Duplikat CSS rule `.jt-nama__text` | Sisa kode setelah refactor | Hapus rule yang lama |

---

### A.4 · File yang Diubah/Dibuat

```
chifoo_backend/
├── apps/universities/
│   ├── models.py                    ← tambah field wcu_area ke SintaJurnal
│   ├── serializers.py               ← tambah wcu_area ke SintaJurnalSerializer
│   ├── views.py                     ← tambah filter, ordering, distribusi_wcu ke stats
│   ├── migrations/
│   │   └── 0011_add_wcu_area_to_sintajurnal.py  ← migration baru
│   └── management/commands/
│       └── predict_wcu_area.py      ← command ML hybrid baru

chifoo_frontend/
└── src/app/components/sinta/
    └── sinta-jurnal.component.ts    ← komponen utama (full rewrite bertahap)
```

---

## BAGIAN B — Halaman Cluster SINTA (`/sinta/cluster`)

### B.1 · Ikhtisar Fitur

Halaman informatif yang menjelaskan sistem pengelompokan (clustering) kinerja riset perguruan tinggi oleh Kemdiktisaintek melalui platform SINTA, beserta posisi PTMA di tiap cluster.

---

### B.2 · Konten & Struktur Halaman

#### Hero Banner
- Latar: `linear-gradient(135deg, #1e1b4b → #312e81 → #4338ca)` (ungu gelap)
- Informasi ringkas: jumlah PT, penulis aktif, total artikel
- **Donut chart SVG** menampilkan proporsi PT per cluster (warna berbeda tiap level)

#### Penjelasan 5 Level Cluster
| Level | Label | Warna | Ambang Skor |
|-------|-------|-------|-------------|
| 1 | Mandiri 🏆 | Ungu `#7c3aed` | ≥ 10.000 |
| 2 | Utama 🥇 | Biru `#2563eb` | 3.000–9.999 |
| 3 | Madya 🥈 | Hijau `#059669` | 1.000–2.999 |
| 4 | Binaan 🥉 | Amber `#d97706` | 300–999 |
| 5 | Pemula 🌱 | Merah `#dc2626` | < 300 |

Setiap kartu menampilkan: ikon, label, rentang skor, deskripsi, dan jumlah PTMA di level tersebut. **Klik kartu → filter tabel**.

#### Alur Cara Kerja (5 Langkah)
1. Dosen mendaftar ke SINTA
2. Skor publikasi dihitung (per artikel, per indeks)
3. Agregasi skor seluruh dosen per institusi
4. Penetapan cluster berdasarkan ambang batas Kemdiktisaintek
5. Publikasi di profil institusi SINTA

#### Tabel Ranking
- 22 PTMA representatif dengan data ilustratif
- **Sortable:** nama, cluster, skor 3 tahun, penulis, artikel
- **Filter:** pill button per cluster (klik ganda = reset)
- **Skor bar:** bar proporsional berwarna sesuai cluster
- **Badge cluster:** label + warna per level

#### Disclaimer / Catatan
- Data bersifat ilustratif (mock), perlu pembaruan dari data resmi `sinta.kemdikbud.go.id`

---

### B.3 · Data Mock PTMA (22 Institusi)

| Cluster | Contoh Institusi | Skor 3yr Est. |
|---------|-----------------|--------------|
| C1 Mandiri | UMS, UMY, UMM, UAD, UHAMKA | 10.210–14.820 |
| C2 Utama | UNIMMA, UMP, UMSIDA, UNISMUH, UM Pontianak | 2.980–4.820 |
| C3 Madya | UMTAS, UNIMUS, UM BJM, UMK, UNISA | 1.060–1.840 |
| C4 Binaan | UMP Palembang, UM Kotabumi, UM Sorong, UM Manado | 360–680 |
| C5 Pemula | UM Luwuk, UM Papua, STIKES Aisyiyah PLG | 90–180 |

> **Catatan:** Angka skor di atas adalah estimasi ilustratif. Data aktual dapat berbeda secara signifikan dan harus diverifikasi dari sinta.kemdikbud.go.id.

---

### B.4 · Registrasi Komponen

```typescript
// app.module.ts — perubahan:
import { SintaClusterComponent } from './components/sinta/sinta-cluster.component';

// Routes:
{ path: 'sinta/cluster', component: SintaClusterComponent }

// Declarations:
SintaClusterComponent
```

---

### B.5 · File yang Dibuat

```
chifoo_frontend/
└── src/app/components/sinta/
    └── sinta-cluster.component.ts   ← komponen halaman cluster (baru)

chifoo_frontend/
└── src/app/
    └── app.module.ts                ← tambah import + route + declaration
```

---

## BAGIAN C — Catatan Deployment

| Tanggal | Aksi | Status |
|---------|------|--------|
| 2026-03-22 | Push backend (wcu_area, migration, serializer, views) ke GitHub + GitLab | ✅ Commit `5a372f3` |
| 2026-03-22 | Build frontend + deploy ke `public_html` (jurnal + cluster) | ✅ |
| Pending | Production server: `git pull` + `migrate` + `predict_wcu_area --save` + restart | ⏳ |

### Perintah deployment production (backend):
```bash
cd /path/to/chifoo_backend
git pull origin main
python manage.py migrate
python manage.py predict_wcu_area --save
# restart gunicorn/uwsgi
sudo systemctl restart gunicorn   # atau sesuai konfigurasi server
```

---

## BAGIAN D — Backlog / Rencana Berikutnya

- [ ] Integrasi data cluster dari API resmi SINTA (gantikan data mock)
- [ ] Backend endpoint untuk data SintaCluster per institusi
- [ ] Halaman `/sinta/afiliasi` — ranking PT per skor SINTA agregat
- [ ] Tren skor SINTA per tahun (chart garis per PT)
- [ ] Filter cluster di halaman jurnal berdasarkan cluster PT penerbit
- [ ] Export tabel cluster ke CSV/Excel

---

*Dokumen ini dibuat otomatis berdasarkan riwayat sesi pengembangan.*
