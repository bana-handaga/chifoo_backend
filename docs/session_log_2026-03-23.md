# Session Log — 2026-03-23

## Topik: Analisis Riset PTMA dengan LLM Lokal

### Latar Belakang
Halaman **Artikel Ilmiah** di frontend memerlukan deskripsi otomatis untuk setiap topik riset
yang dihasilkan oleh LDA (Latent Dirichlet Allocation) dari judul artikel Scopus.
Deskripsi bertujuan menjelaskan: bidang riset apa yang sedang dikerjakan dosen PTMA, dan tren utamanya.

### Opsi yang Dievaluasi

| Opsi | Model | Pro | Kontra |
|------|-------|-----|--------|
| Anthropic API (Claude Haiku) | `claude-haiku-4-5-20251001` | Kualitas tinggi, mudah | Butuh API key berbayar, tidak tersedia |
| OpenAI API | GPT-3.5 / GPT-4o-mini | Kualitas tinggi | Butuh API key berbayar, tidak tersedia |
| Model Lokal HuggingFace | `google/flan-t5-base` | Gratis, offline, ringan | Kualitas lebih rendah, perlu install |

### Keputusan: Model Lokal — `google/flan-t5-base`

**Alasan:**
- Server memiliki RAM tersisa **23 GB** (total 32 GB), disk sisa **106 GB** — sangat cukup
- Model `flan-t5-base` hanya ~250 MB, berjalan di CPU tanpa GPU
- Tidak ada ketergantungan API eksternal / biaya
- Cukup untuk task deskripsi singkat 2 kalimat dari kata kunci

**Hasil evaluasi model:**
| Model | Bahasa Indonesia | Keterangan |
|-------|-----------------|------------|
| `google/flan-t5-base` | ❌ Rusak (loop "tidak") | Tidak support Indonesian |
| `google/flan-t5-large` | ❌ Rusak | Tidak support Indonesian |
| `Qwen/Qwen2.5-0.5B-Instruct` | ✅ Baik | Multilingual, instruction-tuned, ~1 GB |

**Model dipilih: `Qwen/Qwen2.5-0.5B-Instruct`**

**Alternatif cadangan:**
- `Qwen/Qwen2.5-1.5B-Instruct` (~3 GB) jika kualitas masih kurang
- Atau masukkan `ANTHROPIC_API_KEY` ke `.env` untuk switch ke Claude Haiku

### Implementasi

**Backend:** `apps/universities/views.py` — method `riset_analisis` di `SintaScopusArtikelViewSet`

Alur:
1. LDA menghasilkan `N` topik beserta daftar `keywords` per topik
2. Untuk setiap topik, kirim prompt ke `flan-t5-base`:
   ```
   Describe the research topic with keywords: [kw1, kw2, ...] in 2 sentences in Indonesian.
   ```
3. Hasil disimpan dalam field `deskripsi` di response JSON
4. Response di-cache (Django cache framework) selama 24 jam agar tidak re-inference setiap request

**Frontend:** `sinta-artikel.component.ts`
- Accordion "Analisis Riset" menampilkan kartu per topik
- Setiap kartu: label topik, kata kunci, deskripsi LLM, jumlah artikel, share per tahun

### Dependencies yang Diinstall
```bash
pip install transformers sentencepiece torch --index-url https://download.pytorch.org/whl/cpu
```

### Catatan Performa
- Inference pertama (load model): ~3–5 detik
- Inference per topik: ~1–2 detik di CPU
- Total untuk ~8 topik: ~15–20 detik (di-cache setelahnya)
- Cache key: `riset_analisis_v1`

### Status
- [ ] Install dependencies
- [ ] Implementasi inference di views.py
- [ ] Test endpoint
- [ ] Tampilan frontend kartu topik
