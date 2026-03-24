"""
Scrape daftar pengabdian per author dari SINTA (?view=services).

Input : daftar SintaAuthor dari DB
Output: utils/sinta/outs/author_services/{kode_pt}/{sinta_id}_services.json

Format tiap file:
  {
    "sinta_id": "...",
    "scraped_at": "...",
    "total_scraped": N,
    "service_history": {"2022": 3, "2023": 5, ...},
    "services": [
      {
        "judul": "...",
        "leader_nama": "...",
        "skema": "PKM PID ( PKM-PID )",
        "skema_kode": "PKM-PID",
        "tahun": 2024,
        "dana": "Rp. 5.000.000",
        "status": "Approved",
        "sumber": "INTERNAL",
        "personils": [{"nama": "...", "sinta_id": "..."}]
      }
    ]
  }

Usage:
  cd chifoo_backend
  python utils/sinta/scrape_sinta_author_services.py --sinta-id 6771904
  python utils/sinta/scrape_sinta_author_services.py
  python utils/sinta/scrape_sinta_author_services.py --status
  python utils/sinta/scrape_sinta_author_services.py --force
  python utils/sinta/scrape_sinta_author_services.py --offset 0 --limit 1000
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ptma.settings.base")

import django
django.setup()

from apps.universities.models import SintaAuthor

# ── Config ───────────────────────────────────────────────────────────────────
SINTA_USERNAME = "bana.handaga@ums.ac.id"
SINTA_PASSWORD = "Jawad@Mahdi1214"

BASE_URL  = "https://sinta.kemdiktisaintek.go.id"
LOGIN_URL = f"{BASE_URL}/logins/do_login"
OUT_BASE  = BASE_DIR / "utils" / "sinta" / "outs" / "author_services"

DELAY_OK  = 1.5
DELAY_ERR = 5.0
MAX_RETRY = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
}


# ── Auth ─────────────────────────────────────────────────────────────────────

def do_login(session, username, password):
    try:
        session.get(f"{BASE_URL}/logins", headers=HEADERS, timeout=15)
        resp = session.post(
            LOGIN_URL, data={"username": username, "password": password},
            headers={**HEADERS, "Referer": f"{BASE_URL}/logins"},
            timeout=20, allow_redirects=True,
        )
        return resp.status_code == 200 and "logout" in resp.text.lower()
    except Exception:
        return False


def is_session_expired(html):
    return 'action="https://sinta.kemdiktisaintek.go.id/logins/do_login"' in html


# ── Fetch ────────────────────────────────────────────────────────────────────

def fetch_page(session, url, username, password):
    for attempt in range(MAX_RETRY):
        try:
            resp = session.get(url, headers=HEADERS, timeout=20)
            if resp.status_code in (429, 503):
                time.sleep(DELAY_ERR * (attempt + 1))
                continue
            if resp.status_code != 200:
                return None
            if is_session_expired(resp.text) and username:
                do_login(session, username, password)
                continue
            return resp.text
        except Exception:
            time.sleep(DELAY_ERR)
    return None


# ── Parse ────────────────────────────────────────────────────────────────────

def extract_skema_kode(skema):
    m = re.search(r'\(\s*([A-Z0-9\-]+)\s*\)', skema)
    return m.group(1) if m else ""


def get_last_page(html):
    """Cari nomor halaman terakhir dari pagination."""
    soup = BeautifulSoup(html, "html.parser")
    pages = [a.get_text(strip=True) for a in soup.select(".page-link")
             if a.get_text(strip=True).isdigit()]
    return max((int(p) for p in pages), default=1)


def parse_service_history(html):
    """Ambil tren tahunan dari JS chart (service-chart-articles)."""
    history = {}
    m = re.search(r"getElementById\(['\"]service-chart-articles['\"]", html)
    if m:
        block = html[m.start():m.start() + 5000]
        arrays = re.findall(r"data\s*:\s*\[([^\]]+)\]", block, re.DOTALL)
        if len(arrays) >= 2:
            years  = re.findall(r"['\"](\d{4})['\"]", arrays[0])
            counts = re.findall(r"\b(\d+)\b",          arrays[1])
            for yr, cnt in zip(years, counts):
                if int(cnt) > 0:
                    history[yr] = int(cnt)
    return history


def parse_services(html):
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all(class_="ar-list-item")
    results = []

    for item in items:
        title_el = item.find(class_="ar-title")
        judul = title_el.get_text(strip=True) if title_el else ""
        if not judul:
            continue

        leader_nama = ""
        skema = ""
        personils = []

        for meta in item.find_all(class_="ar-meta"):
            text = meta.get_text(" ", strip=True)

            if text.startswith("Leader"):
                pub_el = meta.find(class_="ar-pub")
                if pub_el:
                    skema = pub_el.get_text(strip=True)
                    leader_raw = meta.get_text(" ", strip=True)
                    leader_raw = re.sub(r'Leader\s*:\s*', '', leader_raw)
                    leader_nama = leader_raw.replace(skema, "").strip()
                else:
                    leader_nama = re.sub(r'Leader\s*:\s*', '', text).strip()

            elif text.startswith("Personils"):
                for a in meta.find_all("a", href=re.compile(r"/authors/profile/")):
                    href = a.get("href", "")
                    m = re.search(r'/authors/profile/(\d+)', href)
                    sinta_id = m.group(1) if m else ""
                    nama = a.get_text(strip=True)
                    if nama and nama != "-":
                        personils.append({"nama": nama, "sinta_id": sinta_id})

        tahun = None
        dana = ""
        status = ""
        sumber = ""

        year_el = item.find(class_="ar-year")
        if year_el:
            try:
                tahun = int(year_el.get_text(strip=True))
            except ValueError:
                pass

        for el in item.find_all(class_="ar-quartile"):
            cls = " ".join(el.get("class", []))
            txt = el.get_text(strip=True)
            if "text-success" in cls:
                status = txt
            elif "text-info" in cls:
                sumber = txt.replace(" SOURCE", "").strip()
            elif not dana and txt.startswith("Rp"):
                dana = txt

        results.append({
            "judul":       judul,
            "leader_nama": leader_nama,
            "skema":       skema,
            "skema_kode":  extract_skema_kode(skema),
            "tahun":       tahun,
            "dana":        dana,
            "status":      status,
            "sumber":      sumber,
            "personils":   personils,
        })

    return results


# ── File helpers ──────────────────────────────────────────────────────────────

def find_existing(sinta_id):
    for f in OUT_BASE.glob(f"*/{sinta_id}_services.json"):
        return f
    return None


def save_result(sinta_id, kode_pt, services, service_history):
    out_dir = OUT_BASE / kode_pt
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{sinta_id}_services.json"
    payload = {
        "sinta_id":       sinta_id,
        "scraped_at":     datetime.now(timezone.utc).isoformat(),
        "total_scraped":  len(services),
        "service_history": service_history,
        "services":       services,
    }
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return out_file


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_authors():
    qs = (
        SintaAuthor.objects
        .select_related("afiliasi")
        .values_list("sinta_id", "afiliasi__sinta_kode")
    )
    return [(sid, kode or "unknown") for sid, kode in qs if sid]


# ── Status ────────────────────────────────────────────────────────────────────

def status():
    authors = get_authors()
    total   = len(authors)
    done    = sum(1 for sid, _ in authors if find_existing(sid))
    all_files = list(OUT_BASE.glob("*/*_services.json"))
    total_items = not_found_count = 0
    for f in all_files:
        try:
            d = json.loads(f.read_text())
            n = d.get("total_scraped", 0)
            total_items += n
            if n == 0:
                not_found_count += 1
        except Exception:
            pass
    print(f"Author di DB          : {total:,}")
    print(f"Sudah discrape        : {done:,}")
    print(f"Belum discrape        : {total - done:,}")
    print(f"Total file JSON       : {len(all_files):,}")
    print(f"  Tidak ada pengabdian: {not_found_count:,}")
    print(f"Total pengabdian      : {total_items:,}")


# ── Run ───────────────────────────────────────────────────────────────────────

def run(authors, force=False, username="", password=""):
    session = requests.Session()
    ok = skip = err = not_found = 0
    total = len(authors)

    if username:
        print(f"Login sebagai {username!r}...", end=" ", flush=True)
        print("OK" if do_login(session, username, password) else "GAGAL — lanjut tanpa login")

    for i, (sid, kode_pt) in enumerate(authors, 1):
        if find_existing(sid) and not force:
            skip += 1
            continue

        base_url = f"{BASE_URL}/authors/profile/{sid}/?view=services"
        html = fetch_page(session, f"{base_url}&page=1", username, password)
        if html is None:
            print(f"  [{i}/{total}] {sid} ERROR")
            err += 1
            time.sleep(DELAY_ERR)
            continue

        service_history = parse_service_history(html)
        last_page = get_last_page(html)
        all_services = parse_services(html)

        for pg in range(2, last_page + 1):
            html_pg = fetch_page(session, f"{base_url}&page={pg}", username, password)
            if html_pg:
                all_services.extend(parse_services(html_pg))
            time.sleep(DELAY_OK)

        save_result(sid, kode_pt, all_services, service_history)

        if all_services:
            ok += 1
            print(f"  [{i}/{total}] {sid} ok ({len(all_services)} pengabdian "
                  f"[{last_page}p], tren={len(service_history)} tahun)")
        else:
            not_found += 1

        time.sleep(DELAY_OK)

        if i % 200 == 0:
            print(f"\n  --- [{i}/{total}] ok={ok} not_found={not_found} skip={skip} err={err} ---\n")

    print(f"\nSelesai: {ok} scraped, {not_found} tidak ada pengabdian, {skip} dilewati, {err} error.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape pengabdian author dari SINTA")
    parser.add_argument("--sinta-id", help="Scrape satu author saja")
    parser.add_argument("--force",    action="store_true")
    parser.add_argument("--status",   action="store_true")
    parser.add_argument("--offset",   type=int, default=0)
    parser.add_argument("--limit",    type=int, default=0)
    parser.add_argument("--username", default=SINTA_USERNAME)
    parser.add_argument("--password", default=SINTA_PASSWORD)
    args = parser.parse_args()

    if args.status:
        status()
        return

    if args.sinta_id:
        try:
            a = SintaAuthor.objects.select_related("afiliasi").get(sinta_id=args.sinta_id)
            kode_pt = a.afiliasi.sinta_kode if a.afiliasi else "unknown"
        except Exception:
            kode_pt = "unknown"
        authors = [(args.sinta_id, kode_pt)]
    else:
        print("Mengambil daftar author dari DB...")
        authors = get_authors()
        print(f"  → {len(authors):,} author ditemukan")

    if args.offset:
        authors = authors[args.offset:]
    if args.limit:
        authors = authors[:args.limit]

    run(authors, force=args.force, username=args.username, password=args.password)


if __name__ == "__main__":
    main()
