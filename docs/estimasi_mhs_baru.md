# Estimasi Mahasiswa Baru Per Tahun — PTMA

## Latar Belakang

Data PDDikti yang tersedia di sistem hanya mengisi field `mahasiswa_aktif` per semester.
Field `mahasiswa_baru`, `mahasiswa_lulus`, dan `mahasiswa_dropout` ada di model database
tetapi nilainya 0 (tidak diisi dari sumber data).

Estimasi dilakukan secara tidak langsung dari pola `mahasiswa_aktif` per semester ganjil.

---

## Asumsi Dasar

1. **Penerimaan mahasiswa baru terjadi satu kali per tahun**, yaitu pada **semester ganjil**
   (Juli–Agustus). Tidak ada penerimaan baru di semester genap.

2. **Pada setiap semester ganjil**, jumlah mahasiswa aktif merupakan gabungan seluruh
   angkatan yang sedang berjalan. Untuk program S1 (masa studi normal 4 tahun / 8 semester):

   ```
   aktif_ganjil(T) = cohort(T) + cohort(T-1) + cohort(T-2) + cohort(T-3)
   ```

3. **Tidak ada mahasiswa yang mengulang lebih dari masa studi normal** (asumsi ideal).
   Dalam praktiknya ada yang mengulang, sehingga angka aktual bisa sedikit lebih besar
   dari estimasi.

4. **Tidak ada perbedaan intake antar-tahun dalam kondisi steady-state**, sehingga
   `cohort(T) ≈ cohort(T-1) ≈ ... ≈ aktif_ganjil / masa_studi`.

---

## Rumus Estimasi

### Mahasiswa Baru

Estimasi intake per tahun dihitung dengan membagi jumlah mahasiswa aktif pada semester
ganjil dengan masa studi normal masing-masing jenjang, lalu dijumlahkan:

```
baru_est(T) = Σ  [ aktif_ganjil(T, jenjang) / masa_studi(jenjang) ]
              jenjang
```

#### Masa Studi Normal per Jenjang

| Jenjang   | Masa Studi (tahun) | Keterangan                        |
|-----------|--------------------|-----------------------------------|
| S1        | 4                  | Program sarjana                   |
| S2        | 2                  | Program magister                  |
| S3        | 3                  | Program doktor                    |
| D4        | 4                  | Sarjana terapan                   |
| D3        | 3                  | Diploma tiga                      |
| D2        | 2                  | Diploma dua                       |
| D1        | 1                  | Diploma satu                      |
| Profesi   | 1                  | PPG, profesi dokter, dll.         |

### Mahasiswa Lulus (Cohort Shift)

Estimasi lulus menggunakan pergeseran kohort: mahasiswa yang masuk tahun T diperkirakan
lulus setelah menempuh masa studi normal.

```
lulus_est(T) = baru_est(T − masa_studi)
```

Karena S1 mendominasi (~80% mahasiswa PTMA), masa studi yang dipakai sebagai acuan
utama adalah **4 tahun**.

```
lulus_est(T) ≈ baru_est(T − 4)
```

---

## Hasil Estimasi PTMA (2019–2025)

Data diambil dari semester ganjil setiap tahun akademik.

| Tahun Akademik | Aktif Ganjil | Baru (est) | Lulus (est) | Keterangan          |
|----------------|-------------|------------|-------------|---------------------|
| 2019/2020      | 525.746     | 145.168    | —           | Data lulus mulai T+4|
| 2020/2021      | 548.230     | 151.911    | —           |                     |
| 2021/2022      | 570.793     | 163.877    | —           |                     |
| 2022/2023      | 602.194     | 177.982    | —           |                     |
| 2023/2024      | 611.732     | 184.926    | ~145.168    | dari cohort 2019/20 |
| 2024/2025      | 679.763     | 246.807*   | ~151.911    | dari cohort 2020/21 |

> \* Lonjakan 2024/2025 disebabkan oleh ekspansi besar program **PPG Prajabatan**
> (Pendidikan Profesi Guru), bukan kenaikan penerimaan umum. Lihat bagian catatan di bawah.

### Rincian Baru Estimate per Jenjang (ganjil 2024/2025)

| Jenjang  | Aktif   | Masa Studi | Kontribusi ke baru_est |
|----------|---------|-----------|------------------------|
| S1       | 541.000 | 4 tahun   | 135.250                |
| Profesi  | 93.861  | 1 tahun   | 93.861  ← dominan      |
| S2       | 20.286  | 2 tahun   | 10.143                 |
| D3       | 15.040  | 3 tahun   | 5.013                  |
| D4       | 7.750   | 4 tahun   | 1.937                  |
| S3       | 1.748   | 3 tahun   | 583                    |
| **Total**| **679.763** |       | **246.787**            |

---

## Catatan Penting

### 1. Distorsi PPG (Profesi Guru)

Program PPG (Pendidikan Profesi Guru) memiliki karakteristik berbeda dari program reguler:
- Masa studi hanya **1 tahun** (2 semester)
- Penerimaan dilakukan dalam **gelombang (batch)**, bukan penerimaan tahunan reguler
- Jumlahnya melonjak dari ~35.000 (2023/2024) menjadi ~94.000 (2024/2025) akibat
  kebijakan pemerintah mempercepat sertifikasi guru (PPG Prajabatan massal)

Akibatnya, estimasi `baru_est` 2024/2025 melonjak dari ~185K ke ~247K, padahal
penerimaan S1 hanya naik sekitar 1.500 mahasiswa.

**Rekomendasi:** Saat visualisasi, pisahkan baris Profesi/PPG dari jenjang akademik reguler.

### 2. Ini Bukan Data Aktual

Angka `baru_est` dan `lulus_est` adalah **estimasi statistik**, bukan data pelaporan PDDikti.
Selalu beri label `*estimasi` atau `(perkiraan)` pada tampilan publik.

### 3. Tidak Memisahkan Lulus vs Dropout

Estimasi `lulus_est` mencerminkan **kohort yang seharusnya selesai**, tanpa memisahkan
antara yang benar-benar lulus (mendapat ijazah) dan yang dropout/keluar. Data dropout
tidak tersedia di sumber PDDikti yang digunakan.

### 4. Data 2025/2026 Belum Lengkap

Semester genap 2025/2026 belum terisi (nilai 0 untuk seluruh prodi). Estimasi hanya
valid sampai tahun akademik **2024/2025**.

---

## Implementasi (Python/Django)

```python
from apps.universities.models import DataMahasiswa
from django.db.models import Sum

MASA_STUDI = {
    's1': 4, 's2': 2, 's3': 3,
    'd4': 4, 'd3': 3, 'd2': 2, 'd1': 1,
    'profesi': 1,
}

def estimasi_baru(tahun_akademik: str) -> dict:
    """
    Estimasi jumlah mahasiswa baru untuk tahun akademik tertentu.
    Hanya menggunakan data semester ganjil.
    Mengembalikan dict {'total': int, 'per_jenjang': {jenjang: int}}.
    """
    rows = (DataMahasiswa.objects
        .filter(semester='ganjil', tahun_akademik=tahun_akademik, mahasiswa_aktif__gt=0)
        .values('program_studi__jenjang')
        .annotate(total=Sum('mahasiswa_aktif')))

    per_jenjang = {}
    total = 0
    for r in rows:
        j   = r['program_studi__jenjang']
        ms  = MASA_STUDI.get(j, 4)
        est = round(r['total'] / ms)
        per_jenjang[j] = est
        total += est

    return {'total': total, 'per_jenjang': per_jenjang}


def estimasi_lulus(tahun_akademik: str, masa_studi_dominan: int = 4) -> int:
    """
    Estimasi mahasiswa lulus pada tahun_akademik T,
    yaitu ≈ baru_est dari T - masa_studi_dominan.
    """
    thn = int(tahun_akademik[:4])
    thn_masuk = '%d/%d' % (thn - masa_studi_dominan, thn - masa_studi_dominan + 1)
    return estimasi_baru(thn_masuk)['total']
```

---

## Referensi

- Sumber data: PDDikti via file `ept_itdd.json` (import ke model `DataMahasiswa`)
- Field yang digunakan: `mahasiswa_aktif`, `semester`, `tahun_akademik`, `program_studi__jenjang`
- Analisis dilakukan: Maret 2026
