import time, sys
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

OUT = "utils/outs/screenshots"

print("Starting...", flush=True)
options = Options()
options.add_argument("--headless")
options.add_argument("--window-size=1920,1080")
options.binary_location = "/snap/firefox/current/usr/lib/firefox/firefox"
driver = webdriver.Firefox(options=options)
print("Driver OK", flush=True)

try:
    driver.get("https://pddikti.kemdiktisaintek.go.id/search/universitas%20muhammadiyah%20yogyakarta")
    time.sleep(6)

    pt_url = None
    for table in driver.find_elements(By.TAG_NAME, "table"):
        for row in table.find_elements(By.TAG_NAME, "tr")[1:]:
            for cell in row.find_elements(By.TAG_NAME, "td"):
                for a in cell.find_elements(By.TAG_NAME, "a"):
                    href = a.get_attribute("href") or ""
                    if "/detail-pt/" in href:
                        pt_url = href
                        break
                if pt_url: break
            if pt_url: break
        if pt_url: break
    print(f"PT URL: {pt_url}", flush=True)

    driver.get(pt_url)
    time.sleep(10)
    # Tunggu tabel dan dropdown muncul
    for _ in range(10):
        selects = driver.find_elements(By.TAG_NAME, "select")
        tables = driver.find_elements(By.TAG_NAME, "table")
        print(f"  Waiting... selects={len(selects)}, tables={len(tables)}", flush=True)
        if selects and tables:
            break
        time.sleep(2)
    driver.save_screenshot(f"{OUT}/dbg0a_pt_atas.png")
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)
    driver.save_screenshot(f"{OUT}/dbg0b_pt_bawah.png")
    # Coba kembali setelah scroll
    selects = driver.find_elements(By.TAG_NAME, "select")
    tables = driver.find_elements(By.TAG_NAME, "table")
    print(f"  Setelah scroll: selects={len(selects)}, tables={len(tables)}", flush=True)
    if selects:
        try:
            Select(selects[0]).select_by_value("semua")
            time.sleep(5)
            driver.save_screenshot(f"{OUT}/dbg0c_pt_semua.png")
        except Exception as e:
            print(f"  select semua gagal: {e}", flush=True)

    driver.execute_script("""
        window.__capturedURL = null;
        var _orig = window.history.pushState.bind(window.history);
        window.history.pushState = function(s,t,u){ window.__capturedURL=u; _orig(s,t,u); };
    """)
    tables = driver.find_elements(By.TAG_NAME, "table")
    print(f"Tables: {len(tables)}", flush=True)
    # Cari baris dengan kode prodi (cell pertama berisi kode angka)
    target_row = None
    for tbl in tables:
        for row in tbl.find_elements(By.TAG_NAME, "tr"):
            cells_tmp = row.find_elements(By.TAG_NAME, "td")
            if len(cells_tmp) >= 2 and cells_tmp[0].text.strip().isdigit():
                target_row = row
                break
        if target_row:
            break
    if not target_row:
        print("Tidak ada baris prodi ditemukan, keluar"); sys.exit(1)
    cells = target_row.find_elements(By.TAG_NAME, "td")
    kode = cells[0].text.strip()
    nama = cells[1].text.strip()
    print(f"Prodi: {kode} | {nama}", flush=True)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cells[1])
    time.sleep(0.3)
    cells[1].click()
    time.sleep(2)

    cap = driver.execute_script("return window.__capturedURL;")
    fresh = f"https://pddikti.kemdiktisaintek.go.id{cap}" if cap else None
    print(f"Fresh URL: {fresh}", flush=True)

    if not fresh:
        print("Gagal dapat URL, keluar")
        sys.exit(1)

    driver.get(fresh)
    time.sleep(8)
    print("Prodi page loaded", flush=True)

    # SS1: sebelum scroll
    sels = driver.find_elements(By.TAG_NAME, "select")
    print(f"[SS1] Select count sebelum scroll: {len(sels)}", flush=True)
    for i, s in enumerate(sels):
        opts = [o.text.strip() for o in s.find_elements(By.TAG_NAME, "option")]
        print(f"  sel[{i}] opts: {opts[:6]}", flush=True)
    driver.save_screenshot(f"{OUT}/dbg1_sebelum_scroll.png")

    # Scroll ke bawah
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)

    # SS2: sesudah scroll
    sels = driver.find_elements(By.TAG_NAME, "select")
    print(f"[SS2] Select count sesudah scroll: {len(sels)}", flush=True)
    for i, s in enumerate(sels):
        opts = [o.text.strip() for o in s.find_elements(By.TAG_NAME, "option")]
        print(f"  sel[{i}] opts: {opts[:6]}", flush=True)
    driver.save_screenshot(f"{OUT}/dbg2_sesudah_scroll.png")

    # Klik tab Tenaga Pendidik
    try:
        el = driver.find_element(By.XPATH, "//*[normalize-space(text())='Tenaga Pendidik']")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.5)
        el.click()
        time.sleep(4)
        print("Tab Tenaga Pendidik diklik", flush=True)
    except Exception as e:
        print(f"Klik tab gagal: {e}", flush=True)

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)

    # SS3: sesudah klik tab + scroll
    sels = driver.find_elements(By.TAG_NAME, "select")
    print(f"[SS3] Select count sesudah klik tab: {len(sels)}", flush=True)
    for i, s in enumerate(sels):
        opts = [o.text.strip() for o in s.find_elements(By.TAG_NAME, "option")]
        print(f"  sel[{i}] opts: {opts[:8]}", flush=True)
    driver.save_screenshot(f"{OUT}/dbg3_setelah_tab.png")

finally:
    driver.quit()
    print("Done", flush=True)
