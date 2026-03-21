"""
Script untuk mengambil data Perguruan Tinggi dari PDDikti
menggunakan Selenium + Firefox (Geckodriver)
"""

import os
import time
import json
import csv
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def init_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/snap/firefox/current/usr/lib/firefox/firefox"
    return webdriver.Firefox(options=options)


# ---------------------------------------------------------------------------
# Halaman pencarian
# ---------------------------------------------------------------------------

def scrape_search_page(driver, url):
    """Buka halaman search dan ambil semua data tabel (PT, Dosen, Mahasiswa, Prodi)."""
    print(f"Membuka: {url}")
    driver.get(url)
    time.sleep(6)
    print(f"Judul: {driver.title}")

    all_data = {}
    tables = driver.find_elements(By.TAG_NAME, "table")
    print(f"Jumlah tabel ditemukan: {len(tables)}")

    for i, table in enumerate(tables):
        rows = table.find_elements(By.TAG_NAME, "tr")
        if not rows:
            continue

        header_cells = rows[0].find_elements(By.TAG_NAME, "th") or rows[0].find_elements(By.TAG_NAME, "td")
        headers = [h.text.strip() for h in header_cells]

        # Identifikasi nama section dari teks sebelum tabel
        try:
            preceding = driver.execute_script(
                "var el = arguments[0]; var prev = el.previousElementSibling;"
                "while(prev && !prev.textContent.trim()) prev = prev.previousElementSibling;"
                "return prev ? prev.textContent.trim() : '';",
                table,
            )
        except Exception:
            preceding = ""
        section_name = preceding[:80] if preceding else f"tabel_{i+1}"

        data_rows = []
        for row in rows[1:]:
            cells = row.find_elements(By.TAG_NAME, "td")
            if not cells:
                continue
            values = [c.text.strip() for c in cells]
            row_links = [
                a.get_attribute("href")
                for c in cells
                for a in c.find_elements(By.TAG_NAME, "a")
                if a.get_attribute("href")
            ]
            row_dict = dict(zip(headers, values))
            if row_links:
                row_dict["_detail_url"] = row_links[0]
            data_rows.append(row_dict)

        if data_rows:
            all_data[section_name] = {"headers": headers, "rows": data_rows}
            print(f"  [{section_name}] {len(data_rows)} baris | kolom: {headers}")

    return all_data


# ---------------------------------------------------------------------------
# Halaman detail PT
# ---------------------------------------------------------------------------

def extract_profile(driver):
    """
    Ekstrak info profil PT dari pasangan <p> label-value di halaman detail.
    Label: class mengandung 'font-regular text-s'
    Value: class mengandung 'font-semibold'
    """
    paras = driver.find_elements(By.TAG_NAME, "p")
    profile = {}
    current_label = None

    for p in paras:
        cls = p.get_attribute("class") or ""
        text = p.text.strip()
        if not text:
            continue

        if "font-regular text-s" in cls:
            # Ini adalah label
            current_label = text
            # Siapkan slot untuk multi-value (misal Kontak bisa banyak)
            profile[current_label] = []
        elif "font-semibold" in cls and current_label:
            # Ini adalah nilai dari label sebelumnya
            profile[current_label].append(text)

    # Rapikan: single value → string, multi value → list
    clean = {}
    for k, v in profile.items():
        if not v:
            continue
        elif len(v) == 1:
            clean[k] = v[0]
        else:
            clean[k] = v

    # Ambil lokasi (kota/provinsi) dari <p> dengan class khusus
    try:
        loc_el = driver.find_element(
            By.CSS_SELECTOR, "p.text-xs, p[class*='text-white'], p[class*='md\\:text-lg']"
        )
        clean["Lokasi"] = loc_el.text.strip()
    except Exception:
        pass

    return clean


def extract_prodi_table(driver):
    """
    Pilih 'semua' di dropdown Tampilkan, tunggu tabel reload,
    lalu ekstrak semua baris program studi.
    """
    wait = WebDriverWait(driver, 30)

    # Klik dropdown "semua"
    selects = driver.find_elements(By.TAG_NAME, "select")
    if not selects:
        print("  [PERINGATAN] Tidak ada dropdown Tampilkan ditemukan.")
        return []

    tampilkan_select = selects[0]
    sel_obj = Select(tampilkan_select)

    # Pilih "semua" jika tersedia, jika tidak pilih nilai terbesar (last option)
    opts = sel_obj.options
    opt_values = [o.get_attribute("value") for o in opts]
    if "semua" in opt_values:
        sel_obj.select_by_value("semua")
        print("  Dropdown 'semua' dipilih, menunggu tabel reload...")
    else:
        sel_obj.select_by_value(opt_values[-1])
        print(f"  Dropdown '{opt_values[-1]}' dipilih (tidak ada opsi semua), menunggu tabel reload...")

    # Tunggu baris bertambah atau stabil
    time.sleep(5)

    # Ambil tabel program studi (tabel pertama) — guard jika tidak ada tabel
    all_tables = driver.find_elements(By.TAG_NAME, "table")
    if not all_tables:
        print("  [PERINGATAN] Tidak ada tabel ditemukan setelah dropdown dipilih.")
        return []
    table = all_tables[0]
    all_rows = table.find_elements(By.TAG_NAME, "tr")
    print(f"  Total baris di tabel: {len(all_rows)}")

    # --- Tentukan kolom header ---
    # Tabel punya 3 baris header: baris 0, 1, 2 (baris 3+ adalah data)
    # Mapping kolom yang sudah dipetakan secara manual:
    KOLOM = [
        "Kode",
        "Nama Program Studi",
        "Status",
        "Jenjang",
        "Akreditasi",
        "Data Pelaporan (Penghitung)",
        "Dosen Tetap",
        "Dosen Tidak Tetap",
        "Total Dosen",
        "Jumlah Mahasiswa",
        "Rasio Dosen/Mahasiswa",
    ]

    prodi_list = []
    # Baris data dimulai dari index 3 (lewati 3 baris header)
    for row in all_rows[3:]:
        cells = row.find_elements(By.TAG_NAME, "td")
        if not cells:
            continue
        values = [c.text.strip() for c in cells]
        # Lewati baris yang semua nilainya kosong
        if not any(values):
            continue
        row_dict = {}
        for j, col in enumerate(KOLOM):
            row_dict[col] = values[j] if j < len(values) else ""
        prodi_list.append(row_dict)

    return prodi_list


def extract_statistik(driver):
    """Ekstrak statistik ringkasan: rasio dosen-mahasiswa, rata-rata masa studi, dll."""
    statistik = {}
    body_text = driver.find_element(By.TAG_NAME, "body").text

    # Cari tabel Masa Studi (tabel ke-2, index 1)
    tables = driver.find_elements(By.TAG_NAME, "table")
    if len(tables) >= 2:
        masa_studi_table = tables[1]
        rows = masa_studi_table.find_elements(By.TAG_NAME, "tr")
        masa_studi = {}
        for row in rows[1:]:  # skip header
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 2:
                jenjang = cells[0].text.strip()
                rata_rata = cells[1].text.strip()
                if jenjang:
                    masa_studi[jenjang] = rata_rata
        statistik["Masa Studi"] = masa_studi

    # Cari teks Rasio Dosen:Mahasiswa dan Rata-rata
    lines = body_text.split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if "Rasio Dosen: Mahasiswa" in line and i + 1 < len(lines):
            statistik["Rasio Dosen: Mahasiswa"] = lines[i + 1].strip()
        elif "Rata rata Mahasiswa Baru" in line and i + 1 < len(lines):
            statistik["Rata-rata Mahasiswa Baru"] = lines[i + 1].strip()
        elif "Rata rata Jumlah Lulusan" in line and i + 1 < len(lines):
            statistik["Rata-rata Jumlah Lulusan"] = lines[i + 1].strip()

    return statistik


def scrape_pt_detail(driver, pt_url, nama_dari_tabel=""):
    """
    Ambil semua detail PT:
    - Profil (kode, status, akreditasi, kontak, alamat, dll.)
    - Tabel program studi lengkap (dropdown 'semua')
    - Statistik (rasio, masa studi)
    """
    print(f"\n  Mengakses detail PT: {pt_url}")
    driver.get(pt_url)
    time.sleep(7)

    detail = {"url": pt_url}

    # 1. Nama PT dari heading
    nama_di_halaman = ""
    for tag in ["h1", "h2", "h3"]:
        for el in driver.find_elements(By.TAG_NAME, tag):
            txt = el.text.strip()
            if txt and len(txt) > 5:
                nama_di_halaman = txt
                break
        if nama_di_halaman:
            break

    # Verifikasi nama
    if nama_dari_tabel and nama_di_halaman:
        cocok = nama_dari_tabel.strip().upper() == nama_di_halaman.strip().upper()
        detail["nama"] = nama_dari_tabel  # Gunakan nama persis dari tabel
        detail["nama_verifikasi"] = {
            "nama_dari_tabel": nama_dari_tabel,
            "nama_di_halaman": nama_di_halaman,
            "jumlah_huruf_tabel": len(nama_dari_tabel),
            "jumlah_huruf_halaman": len(nama_di_halaman),
            "cocok": cocok,
        }
        status = "[OK]" if cocok else "[PERINGATAN] Nama tidak cocok!"
        print(f"  {status} '{nama_dari_tabel}' ({len(nama_dari_tabel)} huruf)")
    else:
        detail["nama"] = nama_dari_tabel or nama_di_halaman

    # 2. Profil
    print("  Mengekstrak profil...")
    detail["profil"] = extract_profile(driver)
    print(f"  Profil: {list(detail['profil'].keys())}")

    # 3. Program Studi (pilih 'semua' di dropdown)
    print("  Mengambil semua Program Studi...")
    detail["program_studi"] = extract_prodi_table(driver)
    print(f"  Total Program Studi: {len(detail['program_studi'])}")

    # 4. Statistik
    print("  Mengekstrak statistik...")
    detail["statistik"] = extract_statistik(driver)
    print(f"  Statistik: {detail['statistik']}")

    return detail


# ---------------------------------------------------------------------------
# Scraping detail Program Studi
# ---------------------------------------------------------------------------

def collect_prodi_urls(driver, pt_detail_url):
    """
    Buka halaman detail PT, pilih 'semua' di dropdown prodi,
    lalu kumpulkan URL halaman detail tiap prodi dengan ctrl+click
    (tab baru, tanpa meninggalkan halaman PT).
    Returns: list of dict {kode, nama, url}
    """
    print(f"\n  Mengumpulkan URL prodi dari: {pt_detail_url[:60]}...")
    driver.get(pt_detail_url)
    time.sleep(7)

    selects = driver.find_elements(By.TAG_NAME, "select")
    Select(selects[0]).select_by_value("semua")
    time.sleep(5)

    table = driver.find_elements(By.TAG_NAME, "table")[0]
    rows  = table.find_elements(By.TAG_NAME, "tr")

    # Pass 1: kumpulkan semua (kode, nama) tanpa klik
    prodi_list = []
    for row in rows[3:]:
        cells = row.find_elements(By.TAG_NAME, "td")
        if not cells or len(cells) < 2:
            continue
        kode = cells[0].text.strip()
        nama = cells[1].text.strip()
        if kode:
            prodi_list.append({"kode": kode, "nama": nama})

    n_total = len(prodi_list)
    print(f"  Ditemukan {n_total} prodi, mulai mengumpulkan URL...")

    # Inject JS interceptor: tangkap URL dari pushState tanpa berpindah halaman
    driver.execute_script("""
        window.__capturedURL = null;
        var _orig = window.history.pushState.bind(window.history);
        window.history.pushState = function(state, title, url) {
            window.__capturedURL = url;
            _orig(state, title, url);
        };
    """)

    # Pass 2: klik tiap cell nama, tangkap URL via interceptor, lalu kembali
    prodi_urls = []
    for idx, prodi in enumerate(prodi_list):
        kode = prodi["kode"]
        nama = prodi["nama"]

        # Reset interceptor
        driver.execute_script("window.__capturedURL = null;")

        # Cari cell nama prodi berdasarkan kode di kolom sebelumnya
        try:
            cell_nama = driver.find_element(
                By.XPATH,
                f"//td[normalize-space(text())='{kode}']/following-sibling::td[1]"
            )
        except Exception:
            # Fallback: cari berdasarkan posisi baris di tabel
            try:
                table = driver.find_elements(By.TAG_NAME, "table")[0]
                all_rows = table.find_elements(By.TAG_NAME, "tr")
                data_rows = [r for r in all_rows if r.find_elements(By.TAG_NAME, "td")]
                match = next((r for r in data_rows if r.find_elements(By.TAG_NAME, "td") and
                              r.find_elements(By.TAG_NAME, "td")[0].text.strip() == kode), None)
                cell_nama = match.find_elements(By.TAG_NAME, "td")[1] if match else None
            except Exception:
                cell_nama = None

        if not cell_nama:
            print(f"    [{idx+1}/{n_total}] {kode} — cell tidak ditemukan")
            prodi_urls.append({"kode": kode, "nama": nama, "url": ""})
            continue

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cell_nama)
        time.sleep(0.3)
        cell_nama.click()
        time.sleep(2)

        # Ambil URL yang ditangkap interceptor
        captured = driver.execute_script("return window.__capturedURL;")
        if captured:
            full_url = f"https://pddikti.kemdiktisaintek.go.id{captured}" \
                       if captured.startswith("/") else captured
        else:
            full_url = driver.current_url

        prodi_urls.append({"kode": kode, "nama": nama, "url": full_url})
        print(f"    [{idx+1}/{n_total}] {kode} | {nama[:35]} | ...{full_url[-40:]}")

        # Kembali ke halaman PT, tunggu dan pastikan tabel masih ada
        driver.back()
        time.sleep(4)

        # Re-inject interceptor dan re-pilih semua setelah back
        driver.execute_script("""
            window.__capturedURL = null;
            var _orig = window.history.pushState.bind(window.history);
            window.history.pushState = function(state, title, url) {
                window.__capturedURL = url;
                _orig(state, title, url);
            };
        """)
        try:
            selects = driver.find_elements(By.TAG_NAME, "select")
            if selects:
                Select(selects[0]).select_by_value("semua")
                time.sleep(3)
        except Exception:
            pass

    print(f"  Total URL prodi terkumpul: {len(prodi_urls)}")
    return prodi_urls


def scrape_prodi_profile(driver):
    """Ekstrak profil prodi dari pasangan <p> label-value."""
    paras = driver.find_elements(By.TAG_NAME, "p")
    profile = {}
    current_label = None

    for p in paras:
        cls  = p.get_attribute("class") or ""
        text = p.text.strip()
        if not text:
            continue
        # Label: class mengandung 'text-s' tapi bukan font-semibold
        if "text-s" in cls and "font-semibold" not in cls and len(text) < 60:
            current_label = text
            profile[current_label] = []
        elif ("font-semibold" in cls or "text-l" in cls) and current_label:
            profile[current_label].append(text)

    clean = {}
    for k, v in profile.items():
        if v:
            clean[k] = v[0] if len(v) == 1 else v

    # Nama PT dan nama prodi dari h1
    h1s = [el.text.strip() for el in driver.find_elements(By.TAG_NAME, "h1") if el.text.strip()]
    excluded = {"Informasi Umum", "Ilmu yang Dipelajari", "Kompetensi"}
    meaningful = [h for h in h1s if h not in excluded]
    if len(meaningful) >= 2:
        clean["nama_pt"]    = meaningful[0]
        clean["nama_prodi"] = meaningful[1]
    elif len(meaningful) == 1:
        clean["nama_prodi"] = meaningful[0]

    # Kontak (p dengan class kosong yang mengandung @ atau dimulai 0)
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


def scrape_dosen_per_semester(driver):
    """
    Klik tab 'Tenaga Pendidik', iterasi setiap semester,
    ambil semua dosen dengan menangani paginasi.
    Returns: dict {semester_label: [list_dosen]}
    """
    # Pastikan tab Tenaga Pendidik aktif
    try:
        driver.find_element(By.CSS_SELECTOR, "[data-value='dosen_homebase']").click()
        time.sleep(2)
    except Exception:
        pass

    selects = driver.find_elements(By.TAG_NAME, "select")
    if not selects:
        return {}

    semester_select = selects[0]
    semester_opts   = semester_select.find_elements(By.TAG_NAME, "option")

    # Pilih jumlah tampilkan terbesar (biasanya 15)
    if len(selects) >= 2:
        try:
            opts_tampil = selects[1].find_elements(By.TAG_NAME, "option")
            Select(selects[1]).select_by_value(opts_tampil[-1].get_attribute("value"))
            time.sleep(2)
        except Exception:
            pass

    COLS_DOSEN = ["No", "Nama", "NIDN", "NUPTK", "Pendidikan", "Status", "Ikatan Kerja"]

    dosen_per_semester = {}

    for opt in semester_opts:
        sem_val = opt.get_attribute("value")
        sem_txt = opt.text.strip()

        # Re-fetch select karena DOM mungkin re-render
        selects = driver.find_elements(By.TAG_NAME, "select")
        Select(selects[0]).select_by_value(sem_val)
        time.sleep(3)

        all_dosen = []
        while True:
            tables = driver.find_elements(By.TAG_NAME, "table")
            if len(tables) < 2:
                break
            rows = tables[1].find_elements(By.TAG_NAME, "tr")

            for row in rows[1:]:
                cells = row.find_elements(By.TAG_NAME, "td")
                if not cells or not any(c.text.strip() for c in cells):
                    continue
                vals = [c.text.strip() for c in cells]
                all_dosen.append(dict(zip(COLS_DOSEN, vals)))

            # Cari tombol halaman berikutnya
            next_btn = None
            for btn in driver.find_elements(By.TAG_NAME, "button"):
                aria = (btn.get_attribute("aria-label") or "").lower()
                txt  = btn.text.strip()
                if ("next" in aria or txt in (">", "›", "»")) and not btn.get_attribute("disabled"):
                    next_btn = btn
                    break
            # Coba cari via SVG/icon next page (angka pagination)
            if not next_btn:
                try:
                    # Cari pola "X dari Y" untuk tahu apakah masih ada halaman
                    body_txt = driver.find_element(By.TAG_NAME, "body").text
                    import re
                    m = re.search(r"(\d+)\s+dari\s+(\d+)", body_txt)
                    if m:
                        cur_page  = int(m.group(1))
                        total_page = int(m.group(2))
                        if cur_page < total_page:
                            # Klik nomor halaman berikutnya
                            page_btns = driver.find_elements(
                                By.XPATH,
                                f"//p[normalize-space(text())='{cur_page + 1}'] | "
                                f"//button[normalize-space(text())='{cur_page + 1}'] | "
                                f"//span[normalize-space(text())='{cur_page + 1}']"
                            )
                            if page_btns:
                                next_btn = page_btns[0]
                except Exception:
                    pass

            if next_btn:
                next_btn.click()
                time.sleep(3)
            else:
                break

        dosen_per_semester[sem_txt] = all_dosen
        print(f"    [{sem_txt}] {len(all_dosen)} dosen")

    return dosen_per_semester


def scrape_mahasiswa_per_semester(driver):
    """
    Klik tab 'Mahasiswa', ambil tabel Semester | Jumlah Mahasiswa.
    Returns: list of dict {semester, jumlah_mahasiswa}
    """
    try:
        driver.find_element(By.CSS_SELECTOR, "[data-value='mahasiswa']").click()
        time.sleep(3)
    except Exception as e:
        print(f"    Gagal klik tab Mahasiswa: {e}")
        return []

    # Cari tabel yang header baris pertamanya = "Semester | Jumlah Mahasiswa"
    # (index bisa berubah tergantung DOM, jadi cari berdasarkan konten header)
    tables = driver.find_elements(By.TAG_NAME, "table")
    mhs_table = None
    for tbl in tables:
        header_cells = tbl.find_elements(By.CSS_SELECTOR, "tr:first-child th, tr:first-child td")
        texts = [c.text.strip() for c in header_cells]
        if "Semester" in texts and "Jumlah Mahasiswa" in texts:
            mhs_table = tbl
            break

    if not mhs_table:
        return []

    rows = mhs_table.find_elements(By.TAG_NAME, "tr")
    mahasiswa = []
    for row in rows[1:]:   # skip header
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) >= 2:
            sem = cells[0].text.strip()
            jml = cells[1].text.strip()
            if sem:
                mahasiswa.append({"semester": sem, "jumlah_mahasiswa": jml})

    return mahasiswa


def scrape_prodi_detail(driver, prodi_url):
    """
    Scrape halaman detail satu prodi:
    - profile
    - dosen (per semester)
    - mahasiswa (per semester)
    """
    print(f"\n    Membuka: {prodi_url[:70]}...")
    driver.get(prodi_url)
    time.sleep(7)

    result = {"url": prodi_url}

    print("      → Profil...")
    result["profile"] = scrape_prodi_profile(driver)

    print("      → Dosen homebase per semester...")
    result["dosen"] = scrape_dosen_per_semester(driver)

    print("      → Mahasiswa per semester...")
    result["mahasiswa"] = scrape_mahasiswa_per_semester(driver)

    return result


def save_prodi_detail(data, kode_pt, kode_ps, out_dir):
    """Simpan detail satu prodi ke [kode_pt]_[kode_ps].json"""
    os.makedirs(out_dir, exist_ok=True)
    path = f"{out_dir}/{kode_pt}_{kode_ps}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


# ---------------------------------------------------------------------------
# Simpan hasil
# ---------------------------------------------------------------------------

def save_results(all_data, filepath_json, filepath_csv=None):
    with open(filepath_json, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f"Data disimpan: {filepath_json}")

    if filepath_csv:
        all_rows = []
        for section, tabel in all_data.items():
            for row in tabel.get("rows", []):
                row["_section"] = section
                all_rows.append(row)
        if all_rows:
            fieldnames = list({k for r in all_rows for k in r.keys()})
            with open(filepath_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            print(f"CSV disimpan: {filepath_csv}")


def save_pt_details(pt_details, out_dir="/home/ubuntu/projects/utils/outs"):
    import os
    os.makedirs(out_dir, exist_ok=True)

    for pt in pt_details:
        kode = pt.get("kode_pt", "unknown").strip()

        # 1. JSON profil
        profil = {
            "nama": pt.get("nama", ""),
            "kode_pt": kode,
            "singkatan": pt.get("singkatan", ""),
            "url": pt.get("url", ""),
        }
        profil.update(pt.get("profil", {}))
        profil["statistik"] = pt.get("statistik", {})

        path_profil = f"{out_dir}/{kode}_profile.json"
        with open(path_profil, "w", encoding="utf-8") as f:
            json.dump(profil, f, ensure_ascii=False, indent=2)
        print(f"  Profil   : {path_profil}")

        # 2. JSON program studi
        prodi_list = []
        for prodi in pt.get("program_studi", []):
            row = {"nama_pt": pt.get("nama", ""), "kode_pt": kode}
            row.update(prodi)
            prodi_list.append(row)

        path_prodi = f"{out_dir}/{kode}_programstudi.json"
        with open(path_prodi, "w", encoding="utf-8") as f:
            json.dump(prodi_list, f, ensure_ascii=False, indent=2)
        print(f"  Prodi    : {path_prodi} ({len(prodi_list)} program studi)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(
    keyword="Universitas Muhammadiyah Malang",
    nama_pt_target="UNIVERSITAS MUHAMMADIYAH MALANG",
    kode_pt="071024",
):
    """
    keyword        : kata kunci pencarian (boleh huruf kecil)
    nama_pt_target : nama PT yang ingin diambil detailnya, harus persis sama
                     karakter per karakter (case-insensitive) dengan kolom
                     'Nama Perguruan Tinggi' di tabel hasil pencarian.
    kode_pt        : kode PT, digunakan sebagai prefix nama file output.
                     Output: outs/[kode_pt]_profile.json & outs/[kode_pt]_programstudi.json
    """
    url = f"https://pddikti.kemdiktisaintek.go.id/search/{keyword.replace(' ', '%20')}"
    out_dir = "/home/ubuntu/projects/utils/outs"
    print("=" * 60)
    print(f"PDDikti Scraper | Keyword     : {keyword}")
    print(f"                | Target nama : {nama_pt_target}")
    print(f"                | Kode PT     : {kode_pt}")
    print(f"                | Output dir  : {out_dir}/")
    print("=" * 60)

    driver = init_driver(headless=True)
    try:
        # 1. Halaman pencarian
        all_data = scrape_search_page(driver, url)
        driver.save_screenshot(f"{out_dir}/../pddikti_screenshot.png")

        # 2. Detail PT — hanya yang namanya persis sama dengan nama_pt_target
        pt_details = []
        for section, tabel in all_data.items():
            for row in tabel.get("rows", []):
                detail_url = row.get("_detail_url", "")
                if not (detail_url and "/detail-pt/" in detail_url):
                    continue

                nama_dari_tabel = row.get(
                    "Nama Perguruan TInggi",
                    row.get("Nama Perguruan Tinggi", ""),
                )

                # Filter ketat: nama harus persis sama (case-insensitive, spasi dinormalisasi)
                if nama_dari_tabel.strip().upper() != nama_pt_target.strip().upper():
                    print(f"  [LEWATI] '{nama_dari_tabel}' (tidak cocok dengan target)")
                    continue

                # Validasi tambahan: jumlah huruf harus sama
                if len(nama_dari_tabel.strip()) != len(nama_pt_target.strip()):
                    print(f"  [LEWATI] '{nama_dari_tabel}' (jumlah huruf berbeda: "
                          f"{len(nama_dari_tabel.strip())} vs {len(nama_pt_target.strip())})")
                    continue

                print(f"  [COCOK] '{nama_dari_tabel}' — mengambil detail...")
                detail = scrape_pt_detail(driver, detail_url, nama_dari_tabel)
                # Gunakan kode_pt dari argumen (bukan dari tabel) sebagai nama file
                detail["kode_pt"] = kode_pt
                detail["singkatan"] = row.get("Singkatan", "")
                detail["nama_pt"] = nama_dari_tabel
                pt_details.append(detail)

        if pt_details:
            print(f"\nMenyimpan output ke {out_dir}/")
            save_pt_details(pt_details, out_dir=out_dir)
            print(f"Total PT yang diambil: {len(pt_details)}")

            # 3. Scrape detail setiap Program Studi
            for pt in pt_details:
                pt_url    = pt["url"]
                kode_pt_  = pt["kode_pt"]

                print(f"\n{'='*60}")
                print(f"Mengumpulkan URL prodi untuk: {pt['nama']}")

                # Kumpulkan semua URL prodi via ctrl+click
                prodi_urls = collect_prodi_urls(driver, pt_url)

                total = len(prodi_urls)
                for i, prodi in enumerate(prodi_urls, 1):
                    kode_ps = prodi["kode"]
                    nama_ps = prodi["nama"]
                    url_ps  = prodi["url"]

                    if not url_ps or not kode_ps:
                        print(f"  [{i}/{total}] LEWATI {kode_ps} (URL kosong)")
                        continue

                    print(f"\n  [{i}/{total}] {kode_ps} - {nama_ps}")
                    detail = scrape_prodi_detail(driver, url_ps)
                    detail["kode_pt"] = kode_pt_
                    detail["kode_ps"] = kode_ps
                    detail["nama_ps"] = nama_ps

                    path = save_prodi_detail(detail, kode_pt_, kode_ps, out_dir)
                    print(f"      Tersimpan: {path}")
        else:
            print(f"\nTidak ada PT dengan nama persis '{nama_pt_target}' ditemukan.")

    finally:
        driver.quit()

    print("\nSelesai.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scraper PDDikti Perguruan Tinggi")
    parser.add_argument("--keyword",  default="universitas muhammadiyah malang",
                        help="Kata kunci pencarian")
    parser.add_argument("--nama",     default="UNIVERSITAS MUHAMMADIYAH MALANG",
                        help="Nama PT persis seperti di tabel (huruf kapital)")
    parser.add_argument("--kode",     default="071024",
                        help="Kode PT, digunakan sebagai prefix nama file output")
    args = parser.parse_args()

    main(keyword=args.keyword, nama_pt_target=args.nama, kode_pt=args.kode)
