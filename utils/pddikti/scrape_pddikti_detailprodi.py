"""
Scraper PDDikti — Detail setiap Program Studi

Alur:
  1. Buka halaman pencarian → temukan URL detail PT
  2. Buka halaman detail PT, ambil daftar prodi (kode + nama)
  3. Untuk setiap prodi:
       a. Klik nama prodi dari halaman PT → tangkap URL segar via JS interceptor
       b. Buka URL tersebut → scrape profil, dosen homebase, mahasiswa
       c. Kembali ke halaman PT, pilih 'semua' lagi
  4. Simpan tiap prodi ke outs/[kode_pt]_[kode_ps]_detailprodi.json

URL prodi di PDDikti bersifat sementara (session-based), jadi URL harus
diambil baru sesaat sebelum dibuka — tidak bisa disimpan lalu dipakai kemudian.

Usage:
    python3 utils/scrape_pddikti_detailprodi.py
    python3 utils/scrape_pddikti_detailprodi.py --resume
    python3 utils/scrape_pddikti_detailprodi.py --start 5
    python3 utils/scrape_pddikti_detailprodi.py --force
    python3 utils/scrape_pddikti_detailprodi.py --resume --force --start 1 --end 2
"""

import os
import re
import time
import json
import argparse
from pathlib import Path

from selenium import webdriver
from firefox_helper import make_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

OUT_DIR  = str(Path(__file__).resolve().parent.parent / "outs")
BASE_URL = "https://pddikti.kemdiktisaintek.go.id"
N_SEMESTER_DOSEN = 2    # Jumlah semester terakhir untuk data dosen (Genap 2025, Gasal 2025)
N_SEMESTER_MHS   = 15  # Jumlah semester terakhir untuk data mahasiswa
# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def init_driver(headless=True):
    return make_driver(headless=headless)


# ---------------------------------------------------------------------------
# Navigasi ke halaman PT
# ---------------------------------------------------------------------------

def find_pt_detail_url(driver, keyword, nama_pt_target):
    url = f"{BASE_URL}/search/{keyword.replace(' ', '%20')}"
    print(f"Membuka pencarian: {url}")
    driver.get(url)
    time.sleep(6)

    for table in driver.find_elements(By.TAG_NAME, "table"):
        rows = table.find_elements(By.TAG_NAME, "tr")
        if not rows:
            continue
        header_cells = (rows[0].find_elements(By.TAG_NAME, "th") or
                        rows[0].find_elements(By.TAG_NAME, "td"))
        headers = [h.text.strip() for h in header_cells]

        for row in rows[1:]:
            cells = row.find_elements(By.TAG_NAME, "td")
            if not cells:
                continue
            row_dict = dict(zip(headers, [c.text.strip() for c in cells]))
            nama = row_dict.get("Nama Perguruan TInggi",
                   row_dict.get("Nama Perguruan Tinggi", "")).strip()

            if nama.upper() != nama_pt_target.strip().upper():
                continue

            for cell in cells:
                for a in cell.find_elements(By.TAG_NAME, "a"):
                    href = a.get_attribute("href") or ""
                    if "/detail-pt/" in href:
                        print(f"  [COCOK] '{nama}' → {href[:70]}...")
                        return href

    print(f"  [TIDAK DITEMUKAN] PT '{nama_pt_target}' tidak ditemukan.")
    return None


# ---------------------------------------------------------------------------
# Ambil daftar prodi dari halaman PT (kode + nama saja, tanpa URL)
# ---------------------------------------------------------------------------

def _inject_interceptor(driver):
    driver.execute_script("""
        window.__capturedURL = null;
        var _orig = window.history.pushState.bind(window.history);
        window.history.pushState = function(state, title, url) {
            window.__capturedURL = url;
            _orig(state, title, url);
        };
    """)


def _close_modal(driver):
    """Tutup modal popup (misal survei kepuasan) jika muncul."""
    try:
        for btn in driver.find_elements(By.XPATH,
                "//button[normalize-space(text())='×' or normalize-space(text())='✕' or "
                "normalize-space(text())='x' or normalize-space(text())='X' or "
                "@aria-label='Close' or @aria-label='close' or contains(@class,'close')]"):
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(1)
                return True
    except Exception:
        pass
    # Fallback: tutup via Escape key
    try:
        from selenium.webdriver.common.keys import Keys
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.5)
    except Exception:
        pass
    return False


def _select_semua(driver):
    """Pilih opsi 'semua' pada dropdown daftar prodi via teks label (case-insensitive)."""
    try:
        for sel_el in driver.find_elements(By.TAG_NAME, "select"):
            opts = sel_el.find_elements(By.TAG_NAME, "option")
            for opt in opts:
                if opt.text.strip().lower() == "semua":
                    val = opt.get_attribute("value")
                    driver.execute_script(
                        "arguments[0].value = arguments[1];"
                        "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                        sel_el, val
                    )
                    print(f"  _select_semua: pilih nilai '{val}' (label 'semua')")
                    time.sleep(4)
                    return
    except Exception:
        pass


def get_prodi_list(driver, pt_detail_url):
    """Buka halaman PT, pilih 'semua', ambil daftar prodi aktif dengan pagination."""
    print(f"\n  Membuka halaman PT: {pt_detail_url[:70]}...")
    driver.get(pt_detail_url)
    time.sleep(7)
    _close_modal(driver)
    _select_semua(driver)

    # Tunggu tabel muncul, maks 20 detik
    deadline = time.time() + 20
    while time.time() < deadline:
        if driver.find_elements(By.TAG_NAME, "table"):
            break
        time.sleep(2)

    if not driver.find_elements(By.TAG_NAME, "table"):
        print("  [PERINGATAN] Tabel prodi tidak ditemukan (timeout 20s).")
        return []

    def _detect_header(tabel):
        header_idx = {}
        for row in tabel.find_elements(By.TAG_NAME, "tr")[:3]:
            cells = row.find_elements(By.TAG_NAME, "th") or row.find_elements(By.TAG_NAME, "td")
            texts = [c.text.strip().lower() for c in cells]
            for key, candidates in {
                "kode":    ["kode", "kode prodi"],
                "nama":    ["nama", "nama prodi", "program studi"],
                "jenjang": ["jenjang"],
                "status":  ["status"],
            }.items():
                for cand in candidates:
                    if cand in texts:
                        header_idx[key] = texts.index(cand)
                        break
            if header_idx:
                break
        return header_idx

    def _read_page(tabel, idx_kode, idx_nama, idx_jenjang, idx_status):
        rows_data = []
        skipped = 0
        for row in tabel.find_elements(By.TAG_NAME, "tr")[3:]:
            cells = row.find_elements(By.TAG_NAME, "td")
            if not cells or len(cells) < 2:
                continue
            kode    = cells[idx_kode].text.strip()    if len(cells) > idx_kode    else ""
            nama    = cells[idx_nama].text.strip()    if len(cells) > idx_nama    else ""
            jenjang = cells[idx_jenjang].text.strip() if len(cells) > idx_jenjang else ""
            status  = cells[idx_status].text.strip()  if len(cells) > idx_status  else ""
            if not kode:
                continue
            if status and status.lower() != "aktif":
                skipped += 1
                continue
            rows_data.append({"kode": kode, "nama": nama, "jenjang": jenjang, "status": status})
        return rows_data, skipped

    def _find_next_btn():
        for btn in driver.find_elements(By.TAG_NAME, "button"):
            try:
                txt  = btn.text.strip()
                aria = (btn.get_attribute("aria-label") or "").lower()
                if (txt in (">", "›", "»") or "next" in aria) and not btn.get_attribute("disabled"):
                    return btn
            except Exception:
                continue
        return None

    prodi_list = []
    skipped_nonaktif = 0
    seen_kodes = set()
    page = 1

    while True:
        tables = driver.find_elements(By.TAG_NAME, "table")
        if not tables:
            break
        tabel = tables[0]

        header_idx = _detect_header(tabel)
        idx_kode    = header_idx.get("kode",    0)
        idx_nama    = header_idx.get("nama",    1)
        idx_jenjang = header_idx.get("jenjang", 2)
        idx_status  = header_idx.get("status",  3)

        rows_data, skipped = _read_page(tabel, idx_kode, idx_nama, idx_jenjang, idx_status)
        skipped_nonaktif += skipped

        new_rows = [r for r in rows_data if r["kode"] not in seen_kodes]
        if not new_rows:
            break  # tidak ada data baru, stop
        for r in new_rows:
            seen_kodes.add(r["kode"])
        prodi_list.extend(new_rows)

        if page == 1:
            print(f"    Hal.1: {len(new_rows)} prodi")

        next_btn = _find_next_btn()
        if not next_btn:
            break

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", next_btn)
        page += 1
        time.sleep(3)
        print(f"    Hal.{page}: baca halaman berikutnya...")

    print(f"  Ditemukan {len(prodi_list)} prodi aktif dari {page} hal. (dilewati {skipped_nonaktif} non-aktif).")
    return prodi_list


# ---------------------------------------------------------------------------
# Ambil URL segar satu prodi dengan klik dari halaman PT
# ---------------------------------------------------------------------------

def get_fresh_prodi_url(driver, pt_detail_url, kode, nama):
    """
    Asumsi: driver sudah ada di halaman PT dengan dropdown 'semua' aktif
    dan JS interceptor sudah di-inject.
    Klik cell nama prodi, tangkap URL, kembali ke halaman PT.
    """
    driver.execute_script("window.__capturedURL = null;")

    # Cari cell nama prodi berdasarkan kode
    cell_nama = None
    try:
        cell_nama = driver.find_element(
            By.XPATH,
            f"//td[normalize-space(text())='{kode}']/following-sibling::td[1]"
        )
    except Exception:
        try:
            table = driver.find_elements(By.TAG_NAME, "table")[0]
            for r in table.find_elements(By.TAG_NAME, "tr"):
                cells = r.find_elements(By.TAG_NAME, "td")
                if cells and cells[0].text.strip() == kode:
                    cell_nama = cells[1]
                    break
        except Exception:
            pass

    if not cell_nama:
        print(f"    Cell prodi {kode} tidak ditemukan di halaman PT")
        return None

    # Tunggu overlay loading hilang sebelum klik (maks 15 detik)
    deadline_overlay = time.time() + 15
    while time.time() < deadline_overlay:
        overlays = driver.find_elements(
            By.CSS_SELECTOR,
            "div.absolute.inset-0, div[class*='bg-black/50'], div[class*='backdrop-blur']"
        )
        visible = [o for o in overlays if o.is_displayed()]
        if not visible:
            break
        time.sleep(1)

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cell_nama)
    time.sleep(0.5)
    # Gunakan JS click sebagai fallback jika native click diblokir overlay
    try:
        cell_nama.click()
    except Exception:
        driver.execute_script("arguments[0].click();", cell_nama)
    time.sleep(2)

    captured = driver.execute_script("return window.__capturedURL;")
    if captured:
        fresh_url = f"{BASE_URL}{captured}" if captured.startswith("/") else captured
    else:
        fresh_url = driver.current_url
        if "/detail-pt/" in fresh_url:
            fresh_url = None   # tidak berpindah halaman, URL tidak valid

    return fresh_url


# ---------------------------------------------------------------------------
# Profil Prodi
# ---------------------------------------------------------------------------

def scrape_prodi_profile(driver):
    paras = driver.find_elements(By.TAG_NAME, "p")
    profile = {}
    current_label = None

    for p in paras:
        cls  = p.get_attribute("class") or ""
        text = p.text.strip()
        if not text:
            continue
        if "text-s" in cls and "font-semibold" not in cls and len(text) < 60:
            current_label = text
            profile[current_label] = []
        elif ("font-semibold" in cls or "text-l" in cls) and current_label:
            profile[current_label].append(text)

    clean = {}
    for k, v in profile.items():
        if v:
            clean[k] = v[0] if len(v) == 1 else v

    h1s = [el.text.strip() for el in driver.find_elements(By.TAG_NAME, "h1") if el.text.strip()]
    excluded = {"Informasi Umum", "Ilmu yang Dipelajari", "Kompetensi"}
    meaningful = [h for h in h1s if h not in excluded]
    if len(meaningful) >= 2:
        clean["nama_pt"]    = meaningful[0]
        clean["nama_prodi"] = meaningful[1]
    elif len(meaningful) == 1:
        clean["nama_prodi"] = meaningful[0]

    for p in paras:
        cls  = p.get_attribute("class") or ""
        text = p.text.strip()
        if cls == "" and text and ("@" in text or (text.startswith("0") and len(text) > 5)):
            clean.setdefault("Kontak", [])
            if isinstance(clean["Kontak"], str):
                clean["Kontak"] = [clean["Kontak"]]
            if text not in clean["Kontak"]:
                clean["Kontak"].append(text)

    return clean


# ---------------------------------------------------------------------------
# Helper: tunggu overlay loading hilang
# ---------------------------------------------------------------------------

def _wait_overlay_gone(driver, timeout=15):
    """Tunggu overlay loading (bg-black/50 backdrop-blur) hilang dari DOM."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        overlays = driver.find_elements(
            By.CSS_SELECTOR,
            "div[class*='bg-black/50'], div[class*='backdrop-blur']"
        )
        if not any(o.is_displayed() for o in overlays):
            return
        time.sleep(1)


# ---------------------------------------------------------------------------
# Dosen Homebase per Semester
# ---------------------------------------------------------------------------

def scrape_dosen_homebase(driver, n_semester=N_SEMESTER_DOSEN):
    """
    Baca tabel dosen homebase (tab Tenaga Pendidik sudah aktif secara default).
    Ambil N semester terakhir, tiap semester baca semua halaman tabel.

    Returns: dict { semester_label: [list_dosen] }
    """

    time.sleep(2)

    # Tunggu dropdown semester muncul di DALAM tab panel, maks 15 detik
    # Scroll ke bawah untuk memastikan tab content ter-render
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1)

    def _is_semester_select(sel_el):
        """Cek apakah select adalah dropdown semester (bukan rows-per-page atau lainnya).
        Mendeteksi via teks label (Genap/Ganjil/tahun) ATAU kode nilai 5 digit (20251)."""
        try:
            opts = sel_el.find_elements(By.TAG_NAME, "option")
            opt_texts = [o.text.strip() for o in opts]
            opt_vals  = [o.get_attribute("value") for o in opts]
            sem_keywords = ("genap", "ganjil", "gasal", "semester")
            text_match = any(
                any(kw in t.lower() for kw in sem_keywords) or
                any(t[j:j+4].isdigit() for j in range(max(0, len(t) - 3)))
                for t in opt_texts if t
            )
            # Kode semester PDDikti: 5 digit angka, misal "20251"
            val_match = any(len(v) == 5 and v.isdigit() for v in opt_vals if v)
            return text_match or val_match
        except Exception:
            return False

    semester_select = None
    deadline_tab = time.time() + 15
    while time.time() < deadline_tab:
        try:
            for sel_el in driver.find_elements(By.TAG_NAME, "select"):
                if _is_semester_select(sel_el):
                    semester_select = sel_el
                    break
        except Exception:
            pass
        if semester_select:
            break
        time.sleep(1)

    if semester_select is None:
        print("      [PERINGATAN] Dropdown semester dosen tidak ditemukan.")
        return {}

    # Simpan opsi semester SEBELUM interaksi DOM lainnya agar referensi tidak stale
    try:
        semester_opts = semester_select.find_elements(By.TAG_NAME, "option")
        target_semesters = [
            (o.get_attribute("value"), o.text.strip())
            for o in semester_opts[:n_semester]
        ]
        print(f"      Semester tersedia: {[t for _, t in target_semesters]}")
    except Exception as e:
        print(f"      [PERINGATAN] Gagal baca opsi semester: {e}")
        return {}
    semester_opt_values = [v for v, _ in target_semesters]

    COLS_DOSEN = ["No", "Nama", "NIDN", "NUPTK", "Pendidikan", "Status", "Ikatan Kerja"]

    def _refetch_semester_select():
        """Cari ulang semester select dari DOM saat ini via _is_semester_select."""
        for sel_el in driver.find_elements(By.TAG_NAME, "select"):
            if _is_semester_select(sel_el):
                return sel_el
        return None

    TIMEOUT_DOSEN = 60

    def _find_dosen_table_with_data():
        try:
            for tbl in driver.find_elements(By.TAG_NAME, "table"):
                try:
                    hdrs = [c.text.strip() for c in tbl.find_elements(
                        By.CSS_SELECTOR, "tr:first-child th, tr:first-child td")]
                    # Deteksi normal: header punya kolom Nama + NIDN
                    if "Nama" in hdrs and "NIDN" in hdrs:
                        data_rows = [
                            r for r in tbl.find_elements(By.TAG_NAME, "tr")[1:]
                            if any(c.text.strip() for c in r.find_elements(By.TAG_NAME, "td"))
                        ]
                        if data_rows:
                            return tbl
                    # Deteksi alternatif: header kosong tapi innerHTML mengandung pola NIDN
                    # (React kadang render header sebagai icon/span tanpa teks)
                    elif not any(hdrs):
                        html = tbl.get_attribute("innerHTML") or ""
                        import re as _re
                        # NIDN adalah 10 digit angka
                        if _re.search(r'\b\d{10}\b', html):
                            data_rows = [
                                r for r in tbl.find_elements(By.TAG_NAME, "tr")
                                if any(c.text.strip() for c in r.find_elements(By.TAG_NAME, "td"))
                            ]
                            if data_rows:
                                return tbl
                except Exception:
                    continue
        except Exception:
            pass
        return None

    dosen_per_semester = {}

    for sem_val, sem_txt in target_semesters:
        _wait_overlay_gone(driver)
        sel = _refetch_semester_select()
        if sel:
            try:
                # Gunakan JS set value agar tidak diblokir overlay (bypass klik)
                driver.execute_script(
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    sel, sem_val
                )
            except Exception as e:
                print(f"        [{sem_txt}] gagal pilih semester: {e}, lewati")
                dosen_per_semester[sem_txt] = []
                continue

        # Tunggu tabel dosen dengan data
        deadline = time.time() + TIMEOUT_DOSEN
        dosen_table_ready = None
        while time.time() < deadline:
            dosen_table_ready = _find_dosen_table_with_data()
            if dosen_table_ready:
                break
            time.sleep(1)

        if dosen_table_ready is None:
            print(f"        [{sem_txt}] timeout {TIMEOUT_DOSEN}s — tidak ada dosen homebase, berhenti iterasi semester")
            break

        # Beri jeda agar React selesai render pagination setelah data pertama muncul
        time.sleep(2)

        def _find_dosen_table():
            """Cari tabel dosen (ada header Nama + NIDN), tanpa syarat ada data."""
            for tbl in driver.find_elements(By.TAG_NAME, "table"):
                try:
                    hdrs = [c.text.strip() for c in tbl.find_elements(
                        By.CSS_SELECTOR, "tr:first-child th, tr:first-child td")]
                    if "Nama" in hdrs and "NIDN" in hdrs:
                        return tbl
                except Exception:
                    continue
            return None

        def _click_next_btn_dosen():
            """Cari dan klik tombol next-page tabel dosen dalam satu JS call.
            Return dict {clicked, cur, total, reason} untuk diagnostik.

            Dari HTML PDDikti:
              Tombol PREV : <button> tanpa aria-disabled
              Tombol NEXT : <button aria-disabled="false"> saat aktif
              Halaman terakhir: NEXT tetap aria-disabled="false" tapi ditambah attr disabled
            Selector button[aria-disabled='false']:not([disabled]) = NEXT aktif saja.

            Struktur pagination:
              <div>
                <button>SVG-prev</button>
                <div><p>CUR</p><span>dari</span><p>TOTAL</p></div>
                <button aria-disabled="false">SVG-next</button>
              </div>
            cur/total diambil dari <p> dalam sibling container tombol NEXT.
            """
            return driver.execute_script("""
                // Query langsung ke tabpanel dosen_homebase — tidak pakai walk-up
                // supaya tidak bisa melompat ke tabpanel lain (dosen_rasio, mahasiswa, dsb.)
                var tabpanel = document.querySelector(
                    '[role="tabpanel"][data-value="dosen_homebase"]');
                if (!tabpanel)
                    return {clicked: false, reason: "no_dosen_homebase_tabpanel", cur: 0, total: 0};

                // button[aria-disabled='false']:not([disabled]) = tombol NEXT yang aktif.
                // Halaman terakhir: NEXT punya attr native 'disabled' + aria-disabled='false'.
                var allNavBtns = Array.from(
                    tabpanel.querySelectorAll(
                        "button[aria-disabled='false']:not([disabled]) svg.text-linear-main-2")
                ).map(function(svg){ return svg.closest("button"); })
                 .filter(function(b){ return b !== null; });

                if (allNavBtns.length === 0)
                    return {clicked: false, reason: "last_page", cur: 0, total: 0};
                var nextBtn = allNavBtns[0];

                // Ambil cur/total dari <p> di parent langsung nextBtn
                var cur = 0, total = 0, pNums = [];
                try {
                    var paginContainer = nextBtn.parentElement;
                    pNums = Array.from(paginContainer.querySelectorAll("p"))
                                .filter(function(el){
                                    return /^\\d+$/.test(el.textContent.trim());
                                });
                    if (pNums.length >= 2) {
                        cur   = parseInt(pNums[0].textContent.trim());
                        total = parseInt(pNums[pNums.length - 1].textContent.trim());
                    }
                } catch(e) {}

                // dispatchEvent agar React synthetic event terpicu
                nextBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
                nextBtn.dispatchEvent(new MouseEvent('mouseup',   {bubbles: true, cancelable: true}));
                nextBtn.dispatchEvent(new MouseEvent('click',     {bubbles: true, cancelable: true}));
                return {clicked: true, reason: "ok navBtns=" + allNavBtns.length,
                        cur: cur, total: total};
            """)

        def _snapshot_first_row(tbl):
            """Ambil teks baris data pertama tabel sebagai penanda halaman."""
            try:
                rows = tbl.find_elements(By.TAG_NAME, "tr")
                for row in rows[1:]:
                    txt = row.text.strip()
                    if txt:
                        return txt
            except Exception:
                pass
            return ""

        all_dosen = []
        seen_rows = set()
        page = 1
        try:
            while True:
                dosen_table = _find_dosen_table()
                if dosen_table is None:
                    break

                rows_before = len(all_dosen)
                for row in dosen_table.find_elements(By.TAG_NAME, "tr")[1:]:
                    try:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if not cells or not any(c.text.strip() for c in cells):
                            continue
                        vals = [c.text.strip() for c in cells]
                        row_key = tuple(vals[:3])  # No+Nama+NIDN sebagai dedup key
                        if row_key in seen_rows:
                            continue
                        seen_rows.add(row_key)
                        all_dosen.append(dict(zip(COLS_DOSEN, vals)))
                    except Exception:
                        continue

                rows_added = len(all_dosen) - rows_before
                print(f"          hal.{page}: +{rows_added} dosen (total {len(all_dosen)})")

                if rows_added == 0 and page > 1:
                    break  # tidak ada data baru, berhenti

                # Ambil snapshot baris pertama lalu langsung klik next dalam satu JS call
                snap_before = _snapshot_first_row(dosen_table)

                result = _click_next_btn_dosen()
                print(f"          [next_btn] {result}")
                if not result.get("clicked"):
                    break

                page += 1

                # Tunggu tabel berubah (maks 20 detik)
                _wait_overlay_gone(driver)
                deadline_next = time.time() + 20
                changed = False
                while time.time() < deadline_next:
                    try:
                        new_tbl = _find_dosen_table()
                        snap_after = _snapshot_first_row(new_tbl) if new_tbl else None
                        if snap_after and snap_after != snap_before:
                            changed = True
                            break
                    except Exception:
                        pass
                    time.sleep(1)
                print(f"          [next_btn] changed={changed}")
                if not changed:
                    # Klik berhasil tapi halaman tidak berubah — hentikan
                    break

        except Exception as e:
            print(f"        [{sem_txt}] error saat baca tabel: {e}")

        dosen_per_semester[sem_txt] = all_dosen
        print(f"        [{sem_txt}] {len(all_dosen)} dosen")

    return dosen_per_semester


# ---------------------------------------------------------------------------
# Mahasiswa per Semester
# ---------------------------------------------------------------------------

def scrape_mahasiswa_per_semester(driver, n_semester=N_SEMESTER_MHS):
    MAX_PAGE_MHS = 3  # Baca maks 3 halaman saja

    _wait_overlay_gone(driver)
    try:
        driver.find_element(By.CSS_SELECTOR, "[data-value='mahasiswa']").click()
        time.sleep(3)
    except Exception as e:
        try:
            el = driver.find_element(By.XPATH, "//*[normalize-space(text())='Mahasiswa']")
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
            time.sleep(3)
        except Exception:
            print(f"      [PERINGATAN] Gagal klik tab Mahasiswa: {e}")
            return []

    def _find_mhs_table():
        for tbl in driver.find_elements(By.TAG_NAME, "table"):
            hdrs = [c.text.strip() for c in tbl.find_elements(
                By.CSS_SELECTOR, "tr:first-child th, tr:first-child td")]
            if "Semester" in hdrs and "Jumlah Mahasiswa" in hdrs:
                return tbl
        return None

    def _snapshot_mhs(tbl):
        try:
            rows = tbl.find_elements(By.TAG_NAME, "tr")
            for r in rows[1:]:
                txt = r.text.strip()
                if txt:
                    return txt
        except Exception:
            pass
        return None

    def _click_next_btn_mhs():
        return driver.execute_script("""
            var tabpanel = document.querySelector('[role="tabpanel"][data-value="mahasiswa"]');
            if (!tabpanel)
                return {clicked: false, reason: "no_mahasiswa_tabpanel"};

            var allNavBtns = Array.from(
                tabpanel.querySelectorAll(
                    "button[aria-disabled='false']:not([disabled]) svg.text-linear-main-2")
            ).map(function(svg){ return svg.closest("button"); })
             .filter(function(b){ return b !== null; });

            if (allNavBtns.length === 0)
                return {clicked: false, reason: "last_page"};
            var nextBtn = allNavBtns[0];

            var cur = 0, total = 0;
            try {
                var pNums = Array.from(nextBtn.parentElement.querySelectorAll("p"))
                                .filter(function(el){
                                    return /^\\d+$/.test(el.textContent.trim());
                                });
                if (pNums.length >= 2) {
                    cur   = parseInt(pNums[0].textContent.trim());
                    total = parseInt(pNums[pNums.length - 1].textContent.trim());
                }
            } catch(e) {}

            nextBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
            nextBtn.dispatchEvent(new MouseEvent('mouseup',   {bubbles: true, cancelable: true}));
            nextBtn.dispatchEvent(new MouseEvent('click',     {bubbles: true, cancelable: true}));
            return {clicked: true, reason: "ok", cur: cur, total: total};
        """)

    # Tunggu tabel mahasiswa muncul, maks 15 detik
    deadline_mhs = time.time() + 15
    while time.time() < deadline_mhs:
        if _find_mhs_table():
            break
        time.sleep(1)

    if not _find_mhs_table():
        print("      [PERINGATAN] Tabel mahasiswa tidak ditemukan.")
        return []

    mahasiswa = []
    page = 1
    while len(mahasiswa) < n_semester and page <= MAX_PAGE_MHS:
        tbl = _find_mhs_table()
        if not tbl:
            break

        for row in tbl.find_elements(By.TAG_NAME, "tr")[1:]:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 2:
                sem = cells[0].text.strip()
                jml = cells[1].text.strip()
                if sem:
                    mahasiswa.append({"semester": sem, "jumlah_mahasiswa": jml})
            if len(mahasiswa) >= n_semester:
                break

        if len(mahasiswa) >= n_semester or page >= MAX_PAGE_MHS:
            break

        snap_before = _snapshot_mhs(tbl)
        result = _click_next_btn_mhs()
        if not result.get("clicked"):
            break
        page += 1

        _wait_overlay_gone(driver)
        deadline_next = time.time() + 20
        changed = False
        while time.time() < deadline_next:
            try:
                new_tbl = _find_mhs_table()
                snap_after = _snapshot_mhs(new_tbl) if new_tbl else None
                if snap_after and snap_after != snap_before:
                    changed = True
                    break
            except Exception:
                pass
            time.sleep(1)
        if not changed:
            break

    print(f"        {len(mahasiswa)} semester mahasiswa (target {n_semester})")
    return mahasiswa


# ---------------------------------------------------------------------------
# Scrape satu prodi (driver sudah ada di halaman detail prodi)
# ---------------------------------------------------------------------------

def scrape_detail_prodi(driver):
    result = {}

    print("      → Profil...")
    result["profil"] = scrape_prodi_profile(driver)

    print(f"      → Dosen homebase ({N_SEMESTER_DOSEN} semester terakhir)...")
    result["dosen_homebase"] = scrape_dosen_homebase(driver)

    print("      → Mahasiswa per semester...")
    result["mahasiswa"] = scrape_mahasiswa_per_semester(driver)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(keyword, nama_pt, kode_pt, resume, force, start, end, kode_ps_filter=None):
    pt_out_dir = os.path.join(OUT_DIR, kode_pt)
    os.makedirs(pt_out_dir, exist_ok=True)

    driver = init_driver(headless=True)
    try:
        # 1. Temukan URL halaman PT
        pt_url = find_pt_detail_url(driver, keyword, nama_pt)
        if not pt_url:
            print("PT tidak ditemukan, berhenti.")
            return

        # 2. Ambil daftar prodi dari halaman PT
        prodi_list = get_prodi_list(driver, pt_url)
        if not prodi_list:
            print("Tidak ada prodi ditemukan.")
            return
        total = len(prodi_list)

        # Validasi --start
        start_idx = max(0, start - 1)
        if start_idx >= total:
            print(f"--start {start} melebihi jumlah prodi ({total}).")
            return

        # Validasi --end (None berarti sampai akhir)
        end_idx = total if end is None else min(end, total)
        if end_idx <= start_idx:
            print(f"--end {end} harus lebih besar dari --start {start}.")
            return

        target_list = prodi_list[start_idx:end_idx]

        # Filter per kode prodi jika --kode_ps diberikan
        if kode_ps_filter:
            target_list = [p for p in target_list if p["kode"] in kode_ps_filter]
            if not target_list:
                print(f"Tidak ada prodi dengan kode {kode_ps_filter} di range #{start}–#{end_idx}.")
                return

        print("=" * 60)
        print(f"PDDikti Scraper (Detail Prodi)  PT    : {nama_pt} ({kode_pt})")
        print(f"                                Prodi : {total}")
        print(f"                                Range : #{start} s/d #{end_idx} ({len(target_list)} prodi)")
        print(f"                                Mode  : {'resume' if resume else 'fresh'}")
        print("=" * 60)

        done = skipped = errors = 0

        for i, prodi in enumerate(target_list, start):
            kode_ps    = prodi["kode"]
            nama_ps    = prodi["nama"]
            jenjang    = prodi.get("jenjang", "")
            nama_lengkap = f"{jenjang} {nama_ps}".strip()
            out_path   = os.path.join(pt_out_dir, f"{kode_pt}_{kode_ps}_detailprodi.json")

            if resume and os.path.exists(out_path) and not force:
                print(f"  [{i}/{total}] SKIP {kode_ps} — {nama_lengkap} — sudah ada")
                skipped += 1
                continue

            print(f"\n  [{i}/{total}] {kode_ps} — {nama_lengkap}")

            try:
                # 3a. Selalu buka halaman PT fresh sebelum tiap prodi
                #     agar interceptor bersih dan dropdown dalam keadaan awal
                driver.get(pt_url)
                time.sleep(7)
                _close_modal(driver)
                _select_semua(driver)
                _inject_interceptor(driver)

                # 3b. Klik prodi dari tabel PT → dapat URL segar
                fresh_url = get_fresh_prodi_url(driver, pt_url, kode_ps, nama_ps)

                if not fresh_url:
                    print(f"      [ERROR] Gagal mendapat URL segar untuk {kode_ps}, lanjut ke prodi berikutnya")
                    errors += 1
                    continue

                print(f"      URL: {fresh_url}")

                # 3c. Buka halaman detail prodi
                driver.get(fresh_url)
                time.sleep(7)
                _close_modal(driver)

                # 3d. Scrape
                detail = scrape_detail_prodi(driver)
                detail["kode_pt"] = kode_pt
                detail["kode_ps"] = kode_ps
                detail["nama_ps"] = nama_ps
                detail["nama_pt"] = nama_pt
                detail["url"]     = fresh_url

                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(detail, f, ensure_ascii=False, indent=2)

                n_dosen = sum(len(v) for v in detail["dosen_homebase"].values())
                n_mhs   = len(detail["mahasiswa"])
                print(f"      Tersimpan: {out_path}")
                print(f"      dosen={n_dosen} ({len(detail['dosen_homebase'])} sem), mhs={n_mhs} sem")
                done += 1

            except Exception as e:
                print(f"      [ERROR] {kode_ps}: {e}, lanjut ke prodi berikutnya")
                errors += 1

    finally:
        driver.quit()

    print(f"\nSelesai — done: {done}, skipped: {skipped}, errors: {errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scraper PDDikti — Detail profil, dosen, mahasiswa tiap prodi"
    )
    parser.add_argument("--keyword", default="universitas muhammadiyah surakarta",
                        help="Kata kunci pencarian PT")
    parser.add_argument("--nama",    default="UNIVERSITAS MUHAMMADIYAH SURAKARTA",
                        help="Nama PT persis (huruf kapital)")
    parser.add_argument("--kode",    default="061008",
                        help="Kode PT (prefix nama file output)")
    parser.add_argument("--resume",  action="store_true",
                        help="Skip prodi yang file output-nya sudah ada")
    parser.add_argument("--force",   action="store_true",
                        help="Paksa update data meskipun file output sudah ada (override --resume)")
    parser.add_argument("--start",   type=int, default=1,
                        help="Nomor urut prodi awal (1-based, default: 1)")
    parser.add_argument("--end",     type=int, default=None,
                        help="Nomor urut prodi akhir inklusif (1-based, default: sampai prodi terakhir)")
    parser.add_argument("--kode_ps", nargs='+', default=None,
                        help="Filter kode prodi tertentu (bisa lebih dari satu)")
    args = parser.parse_args()

    main(
        keyword        = args.keyword,
        nama_pt        = args.nama,
        kode_pt        = args.kode,
        resume         = args.resume,
        force          = args.force,
        start          = args.start,
        end            = args.end,
        kode_ps_filter = set(args.kode_ps) if args.kode_ps else None,
    )
