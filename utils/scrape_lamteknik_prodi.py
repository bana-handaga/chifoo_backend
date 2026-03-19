"""
Scrape data akreditasi prodi dari LAM Teknik
https://sakti.lamteknik.or.id/database-akreditasi
Simpan ke utils/ext/lamteknik_prodi.json
"""

import html as html_module
import json
import re
import ssl
import time
import urllib.request
from collections import Counter
from pathlib import Path

BASE_URL = "https://sakti.lamteknik.or.id/database-akreditasi"
OUT = Path(__file__).parent / "ext" / "lamteknik_prodi.json"


def make_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_page(page, ctx):
    url = f"{BASE_URL}?page={page}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return r.read().decode("utf-8", errors="replace")


def get_last_page(html_text):
    pages = re.findall(r'page=(\d+)', html_text)
    return max(int(p) for p in pages) if pages else 1


def strip_city(name):
    m = re.search(r",\s+[A-Z][A-Z\s]+$", name)
    return name[: m.start()].strip() if m else name


def parse_rows(html_text):
    tbody = re.findall(r"<tbody[^>]*>(.*?)</tbody>", html_text, re.DOTALL)
    if not tbody:
        return []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbody[0], re.DOTALL)
    records = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        clean = [html_module.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in cells]
        if len(clean) < 6:
            continue
        # Ambil nomor SK dari data-no-sk attribute
        no_sk_match = re.search(r'data-no-sk="([^"]*)"', row)
        nomor_sk = html_module.unescape(no_sk_match.group(1)).strip() if no_sk_match else None

        # Kolom: (no), nama_prodi, nama_pt, jenjang, peringkat, tgl_sk, tgl_expired
        nama_pt_raw = clean[2]
        nama_pt = strip_city(nama_pt_raw)
        records.append({
            "nama_pt_raw": nama_pt_raw,
            "nama_pt":     nama_pt,
            "nama_prodi":  clean[1],
            "jenjang":     clean[3],
            "peringkat":   clean[4],
            "nomor_sk":    nomor_sk,
            "tgl_sk":      clean[5] if len(clean) > 5 else None,
            "tgl_expired": clean[6] if len(clean) > 6 and clean[6] not in ("-", "") else None,
        })
    return records


def main():
    ctx = make_ctx()
    print("Fetching halaman pertama LAM Teknik...")
    first = fetch_page(1, ctx)
    last_page = get_last_page(first)
    print(f"Total halaman: {last_page} (~{last_page * 10} prodi)")

    all_records = parse_rows(first)
    for page in range(2, last_page + 1):
        if page % 20 == 0:
            print(f"  Halaman {page}/{last_page} ({len(all_records)} prodi)...")
        html_text = fetch_page(page, ctx)
        all_records.extend(parse_rows(html_text))
        time.sleep(0.1)

    print(f"Total parsed: {len(all_records)} prodi")
    OUT.write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {OUT}")
    print("\nPer jenjang:", dict(Counter(r["jenjang"] for r in all_records).most_common()))
    print("Per peringkat:", dict(Counter(r["peringkat"] for r in all_records).most_common()))


if __name__ == "__main__":
    main()
