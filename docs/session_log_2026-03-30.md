# Session Log — 2026-03-30

## Topik: Fix Firefox WebDriver + Pagination Dosen PDDikti

### Latar Belakang
`init_driver()` sangat lambat (hang) saat dijalankan dari terminal user.
Selain itu, scraping dosen home base di `sync_prodi_dosen.py` hanya membaca
halaman pertama (5 dosen) dan tidak meneruskan ke halaman berikutnya.

---

## Masalah 1: `init_driver()` Hang di Terminal

### Gejala
Script berhenti tanpa error di baris:
```python
driver = init_driver()
```
Log terakhir tampil: `"Inisialisasi browser..."` → tidak ada lanjutan.

### Root Cause (urutan investigasi)

1. **Proses stale dari sesi sebelumnya** — sisa proses Firefox/geckodriver dari Mar20
   yang tidak ter-kill. → Kill semua proses.

2. **`/usr/bin/firefox` wrapper memanggil `xdg-settings`/`gsettings`** — Wrapper
   `/usr/bin/firefox` adalah shell script yang memanggil `gsettings` dan
   `xdg-settings` untuk setup default browser. Di terminal tanpa desktop session
   (tanpa `$DBUS_SESSION_BUS_ADDRESS` valid), perintah ini **hang** tanpa output.

3. **Snap Firefox binary langsung butuh snap confinement** —
   `/snap/firefox/current/usr/lib/firefox/firefox` membutuhkan environment snap
   (`snap run`) agar marionette bekerja. File `MarionetteActivePort` tidak pernah
   terbuat jika dipanggil langsung oleh geckodriver di luar snap env.

4. **`FIREFOX_BINARY=/usr/bin/firefox` di-set di environment user** — Candidates
   pertama `_FIREFOX_CANDIDATES` mengambil dari `os.environ.get("FIREFOX_BINARY")`
   sehingga `/usr/lib/firefox-esr/firefox-esr` tidak pernah dicoba.

### Fix

#### Install Firefox ESR (non-snap deb)
```bash
sudo apt install firefox-esr
# → /usr/bin/firefox-esr (wrapper) dan /usr/lib/firefox-esr/firefox-esr (binary)
```
Firefox ESR deb package tidak menggunakan snap confinement sehingga marionette
bekerja normal di lingkungan server/terminal.

#### `firefox_helper.py` — Perubahan Kunci

**Sebelum:**
```python
_FIREFOX_CANDIDATES = [
    os.environ.get("FIREFOX_BINARY", ""),   # bisa override ke binary yang salah
    "/snap/firefox/current/usr/lib/firefox/firefox",
    "/usr/bin/firefox",
    "/usr/lib/firefox/firefox",
    "/usr/lib/firefox-esr/firefox-esr",
]
```

**Sesudah:** Pisahkan kandidat headless vs GUI
```python
_FIREFOX_HEADLESS_CANDIDATES = [
    "/usr/lib/firefox-esr/firefox-esr",   # binary langsung, tidak butuh display
    "/usr/lib/firefox/firefox",
    "/snap/firefox/current/usr/lib/firefox/firefox",
]

_FIREFOX_GUI_CANDIDATES = [
    "/usr/bin/firefox-esr",               # wrapper script yang setup env GTK
    "/usr/bin/firefox",
]
```

**Perubahan lain di `make_driver()`:**
- Pop `FIREFOX_BINARY`, `DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`, `XDG_RUNTIME_DIR`
  dari `os.environ` di mode headless — mencegah snap/wrapper dipakai.
- Set `MOZ_HEADLESS=1` dan `MOZ_DISABLE_CONTENT_SANDBOX=1`.
- Ganti `Service(str(GECKODRIVER_PATH))` → `Service(shutil.which("geckodriver"))`
  untuk menghindari selenium-manager yang lambat (selenium v4.x memicu
  auto-download jika path tidak ditemukan).
- Hapus `--no-sandbox` dan `--disable-dev-shm-usage` (flag Chrome-only, berbahaya
  di Firefox).
- Tambah preferences server-friendly:
  ```python
  options.set_preference("browser.tabs.remote.autostart", False)
  options.set_preference("security.sandbox.content.level", 0)
  options.set_preference("extensions.enabled", False)
  options.set_preference("datareporting.healthreport.uploadEnabled", False)
  options.set_preference("datareporting.policy.dataSubmissionEnabled", False)
  ```

### Pelajaran
- **Snap Firefox tidak bisa dipanggil langsung** dari luar snap env — selalu
  gunakan `snap run firefox` atau, lebih baik, install versi deb.
- **`FIREFOX_BINARY` di env user** bisa override candidates secara diam-diam.
  Selalu `pop` env var override sebelum membuat driver.
- **`--no-sandbox` dan `--disable-dev-shm-usage`** adalah flag Chrome/Chromium.
  Pada Firefox menyebabkan error atau diabaikan. Jangan digunakan untuk geckodriver.
- **Pemisahan kandidat headless vs GUI** penting: binary langsung
  (`/usr/lib/firefox-esr/firefox-esr`) cocok untuk headless; wrapper script
  (`/usr/bin/firefox-esr`) cocok untuk GUI karena mengatur GTK/display env.

---

## Masalah 2: Pagination Dosen Home Base Berhenti di Halaman 1

### Gejala
`_read_dosen_paginated()` hanya membaca 5 dosen (1 halaman) meskipun ada 37 dosen
(8 halaman). Setelah `_click_next_page()` berhasil klik, `_read_table_rows()`
mengembalikan list kosong.

### Root Cause

**Angular SPA re-render — StaleElementReferenceException**

PDDikti menggunakan Angular. Setelah klik pagination, Angular me-destroy dan
me-recreate seluruh komponen tabel. Selenium yang menyimpan referensi element DOM
lama mendapat `StaleElementReferenceException` saat mencoba membaca cell.

`_read_table_rows()` versi lama menyimpan referensi `WebElement`:
```python
for table in driver.find_elements(By.TAG_NAME, "table"):  # referensi lama
    rows = table.find_elements(By.TAG_NAME, "tr")          # referensi lama
    for row in rows[skip_header:]:
        cells = row.find_elements(By.TAG_NAME, "td")       # STALE setelah re-render
```

### Fix: JavaScript Atomik

Baca seluruh tabel dalam satu `execute_script()` call — JavaScript mengakses
state DOM **saat itu juga** tanpa menyimpan referensi element yang bisa stale:

```python
def _read_table_rows(driver, kolom, skip_header=1):
    key_col = kolom[2] if len(kolom) > 2 else kolom[0]
    try:
        raw = driver.execute_script("""
            var key_col = arguments[0];
            var skip = arguments[1];
            for (var tbl of document.querySelectorAll('table')) {
                var allRows = tbl.querySelectorAll('tr');
                if (allRows.length <= skip) continue;
                var hdrCells = allRows[0].querySelectorAll('th, td');
                var hdrs = Array.from(hdrCells).map(function(c){ return c.textContent.trim(); });
                if (hdrs.indexOf(key_col) < 0) continue;
                var result = [];
                for (var i = skip; i < allRows.length; i++) {
                    var cells = allRows[i].querySelectorAll('td');
                    if (!cells.length) continue;
                    var vals = Array.from(cells).map(function(c){ return c.textContent.trim(); });
                    if (!vals.some(function(v){ return v; })) continue;
                    result.push(vals);
                }
                if (result.length > 0) return {headers: hdrs, rows: result};
            }
            return null;
        """, key_col, skip_header)
    except Exception:
        return []
    ...
```

### Fix: `_click_next_page()` Disederhanakan

PDDikti detail prodi memiliki **tepat 4 `<button>`** di halaman:
- index 0 → prev page
- index 1 → next page
- index 2, 3 → tombol lain (tidak terkait pagination)

Versi lama mencari button "setelah tabel dosen" menggunakan `compareDocumentPosition`
yang tidak reliable. Versi baru langsung ambil `button[1]` dan cek `aria-disabled`:

```python
btn = driver.execute_script("""
    var btns = document.querySelectorAll('button');
    if (btns.length < 2) return null;
    var nextBtn = btns[1];
    if (nextBtn.getAttribute('aria-disabled') === 'false' && !nextBtn.disabled) {
        return nextBtn;
    }
    return null;
""")
```

### Fix Tambahan: Retry + Wait

```python
# Retry 4x jika tabel masih loading
for attempt in range(4):
    rows = _read_table_rows(driver, KOLOM_DOSEN, skip_header=1)
    if rows:
        break
    if attempt < 3:
        time.sleep(2)

# Wait 4 detik antar halaman (Angular butuh waktu render)
wait(4, "halaman berikutnya")
```

### Hasil Test
- UMS Akuntansi S1 (kode 62201): **37 dosen** terbaca dari **8 halaman** ✓
- Institut 'Aisyiyah Sulawesi Selatan: **33 dosen** dari 5 prodi ✓

---

## Fitur Baru: `--prodi` Filter CLI

Parameter tambahan untuk `sync_prodi_dosen.py` agar bisa test satu prodi saja:

```bash
python utils/pddikti/sync_prodi_dosen.py \
    --kode 065064 \
    --nama "UNIVERSITAS MUHAMMADIYAH SURAKARTA" \
    --prodi 62201 \
    --dry-run
```

`filter_prodi` diteruskan ke `scrape_pt_page()` untuk skip klik prodi lain
(menghemat waktu saat debugging).

---

## Commit

```
d917ec9  Fix Firefox WebDriver: pakai firefox-esr dan geckodriver sistem
```

File berubah:
- `utils/pddikti/firefox_helper.py`
- `utils/pddikti/sync_prodi_dosen.py`
- `utils/pddikti/test_browser.py` (baru — script kecil test GUI browser)
