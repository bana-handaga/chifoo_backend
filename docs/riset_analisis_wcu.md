# Analisis Aktivitas Riset PTMA — Dokumentasi Pengembangan

## Tujuan
Membangun halaman analitik yang menggambarkan peta aktivitas riset dosen PTMA
(Perguruan Tinggi Muhammadiyah-Aisyiyah) berdasarkan judul artikel Scopus yang telah di-scrape,
dikelompokkan ke dalam standar **5 Broad Subject Areas (WCU/QS/Scopus)**.

---

## Komponen yang Dibangun

### Backend — `apps/universities/views.py`
**ViewSet:** `SintaScopusArtikelViewSet`
**Action:** `GET /api/sinta-scopus-artikel/riset-analisis/`

#### Pipeline analisis:
1. **TF-IDF Word Cloud** — ekstrak kata kunci paling signifikan dari seluruh judul
2. **LDA (Latent Dirichlet Allocation)** — clustering otomatis judul ke N topik (sklearn)
3. **LLM Deskripsi** — Qwen2.5-0.5B-Instruct generate deskripsi paragraf per topik
4. **Trending Keywords per Tahun** — TF-IDF per tahun (2015–2025)
5. **WCU Classification** — keyword scoring per artikel ke 5 bidang WCU

#### Response JSON:
```json
{
  "total_titles": 2953,
  "word_cloud": [{"word": "learning", "score": 156.5}, ...],
  "lda_topics": [
    {
      "id": 0, "label": "Learning · Students · Education",
      "keywords": ["learning", "students", ...],
      "article_count": 716,
      "deskripsi": "Bidang riset utama... (paragraf LLM)",
      "wcu_field": "Social Sciences & Management",
      "wcu_color": "#d97706",
      "wcu_id": "social"
    }, ...
  ],
  "wcu_distribution": [
    {"field": "Social Sciences & Management", "field_id": "social", "color": "#d97706",
     "count": 1542, "pct": 52.2, "topics": ["Learning...", "Financial..."]},
    ...
  ],
  "wcu_trend_year": {
    "2023": [{"field": "Social Sciences & Management", "pct": 50.6, ...}, ...]
  },
  "trending_by_year": {"2023": [{"word": "learning", "score": 12.3}, ...]},
  "topic_per_year": {"2023": [{"label": "...", "count": 50}, ...]}
}
```

---

## Klasifikasi WCU

### 5 Broad Subject Areas
| Field | ID | Warna | Keterangan |
|-------|----|-------|------------|
| Social Sciences & Management | social | #d97706 | Pendidikan, ekonomi, manajemen, kebijakan |
| Engineering & Technology | engineering | #2563eb | ML, energi, konstruksi, elektronik |
| Life Sciences & Medicine | lifescience | #16a34a | Kesehatan, biologi, pertanian, farmasi |
| Natural Sciences | natural | #0891b2 | Fisika, kimia, matematika, lingkungan |
| Arts & Humanities | arts | #9333ea | Sastra, bahasa, agama, seni, budaya |

### Metode Klasifikasi
**Keyword Scoring (hybrid)**:
- Bigram matching (bobot ×3): `"machine learning"`, `"deep learning"`, `"clinical trial"`, dll.
- Single keyword matching (bobot ×1): daftar ~50 kata kunci per bidang
- Artikel diklasifikasikan ke bidang dengan skor tertinggi
- Fallback jika skor = 0: Social Sciences & Management

### Hasil Distribusi (data per 2026-03-23, N=2953 artikel)
```
Social Sciences & Management  : 1542 artikel (52.2%)
Engineering & Technology       :  578 artikel (19.6%)
Life Sciences & Medicine       :  496 artikel (16.8%)
Natural Sciences               :  236 artikel ( 8.0%)
Arts & Humanities              :  101 artikel ( 3.4%)
```

**Interpretasi**: PTMA memiliki kekuatan terbesar di Social Sciences (pendidikan, ekonomi,
manajemen Islam), diikuti Engineering (AI/ML, energi terbarukan, konstruksi), dan Life Sciences
(kesehatan, farmakologi herbal, pertanian).

---

## LLM untuk Deskripsi Topik

### Model: `Qwen/Qwen2.5-0.5B-Instruct`
- Ukuran: ~1 GB (float32, CPU)
- Bahasa: multilingual termasuk Bahasa Indonesia
- Output: 1 paragraf per topik LDA (~4–5 kalimat)
- Cache: Django cache framework, key `riset_analisis_deskripsi_v4`, TTL 24 jam
- Post-processing: strip karakter non-Latin (karakter Mandarin bocor dari training data)

### Evaluasi model yang dicoba:
| Model | Status | Masalah |
|-------|--------|---------|
| `google/flan-t5-base` | ❌ | Output loop "tidak tidak tidak" — tidak support Indonesian |
| `google/flan-t5-large` | ❌ | Sama, output repetitif |
| `Qwen/Qwen2.5-0.5B-Instruct` | ✅ | Output Indonesia baik, ada sedikit karakter Mandarin |

### Catatan performa
- Load model pertama kali: ~3 detik
- Generate 8 topik: ~90–120 detik (CPU)
- Setelah cache: respons instan (<1 detik untuk analisis non-LLM)
- Cache di-invalidate dengan mengubah `_CACHE_KEY` di views.py

---

## Frontend — `sinta-artikel.component.ts`

### Accordion 3: "Analisis Aktivitas Riset PTMA"
Konten (urutan dari atas):
1. **Word Cloud** — kata kunci TF-IDF, ukuran font proporsional
2. **WCU Broad Subject Areas**:
   - Stacked bar proporsi 5 bidang
   - 5 kartu dengan: ranking, nama bidang, jumlah artikel, persentase, topik terkait
   - Tren bidang per tahun (bar horizontal, pilih tahun)
3. **Klaster Topik Riset (LDA)**:
   - Grid 2 kolom kartu topik
   - Setiap kartu: aksen warna, label, badge WCU, progress bar, deskripsi LLM, kata kunci
4. **Kata Kunci Trending** + **Dominasi Topik** per tahun (2 kolom)

### Interface TypeScript baru:
```typescript
interface WcuItem    { field, field_id, color, count, pct, topics[] }
interface WcuTrendItem { field, field_id, color, count, pct }
// LdaTopic diperluas: + deskripsi?, wcu_field?, wcu_color?, wcu_id?
// RisetAnalisis diperluas: + wcu_distribution[], wcu_trend_year{}
```

---

## Instalasi Dependencies

```bash
# PyTorch CPU-only (sudah set default di pip config)
pip install torch --extra-index-url https://download.pytorch.org/whl/cpu

# NLP & ML
pip install transformers sentencepiece scikit-learn numpy

# Pip config (agar torch selalu CPU-only)
pip config set global.extra-index-url https://download.pytorch.org/whl/cpu
# File: ~/.config/pip/pip.conf
```

---

## Perbaikan & Catatan

- **Karakter Mandarin bocor**: diatasi dengan regex strip non-Latin setelah decode
- **Request timeout saat LLM**: pertama kali butuh ~2 menit; beri timeout curl ≥360 detik
- **Cache key versioning**: ganti `_CACHE_KEY` (v1→v4) untuk force-regenerate deskripsi
- **Klasifikasi "Concrete → Social"**: topik "Indonesia · Concrete · Sustainable" salah klasifikasi
  karena kata "Indonesia" mendominasi scoring Social Sciences — perlu fine-tuning keyword weight
- **Klasifikasi "Antioxidant → Engineering"**: perlu penambahan bobot Life Sciences untuk topik
  dengan kata kunci tunggal non-engineering

## Status
- [x] Backend endpoint `riset-analisis` dengan WCU classification
- [x] LLM deskripsi (Qwen2.5-0.5B) dengan caching
- [x] Frontend WCU distribution cards + stacked bar
- [x] Frontend WCU tren per tahun
- [x] Frontend LDA topic cards dengan WCU badge
- [ ] Fine-tuning keyword weights untuk klasifikasi yang lebih akurat
- [ ] Opsi upgrade ke Qwen2.5-1.5B untuk deskripsi lebih baik
