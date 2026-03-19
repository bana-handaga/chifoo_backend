"""
Scrape data akreditasi prodi dari LAM-INFOKOM
https://laminfokom.or.id/official/data-akreditasi-1.html
Simpan ke utils/ext/laminfokom_prodi.json
"""

import html as html_module
import json
import re
import ssl
import urllib.request
from collections import Counter
from pathlib import Path

URL = "https://laminfokom.or.id/official/data-akreditasi-1.html"
OUT = Path(__file__).parent / "ext" / "laminfokom_prodi.json"


def fetch_html():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        return r.read().decode("utf-8", errors="replace")


def strip_city(name):
    m = re.search(r",\s+[A-Z][A-Z\s]+$", name)
    return name[: m.start()].strip() if m else name


def parse(html_text):
    tbody = re.findall(r"<tbody[^>]*>(.*?)</tbody>", html_text, re.DOTALL)
    if not tbody:
        raise ValueError("tbody tidak ditemukan")

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbody[0], re.DOTALL)
    records = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        clean = [html_module.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in cells]
        if len(clean) < 8:
            continue
        # Kolom: nama_pt, nama_prodi, jenjang, wilayah, nomor_sk, peringkat, tahun, tgl_expired, status
        nama_pt_raw = clean[0]
        nama_pt = strip_city(nama_pt_raw)
        records.append({
            "nama_pt_raw": nama_pt_raw,
            "nama_pt":     nama_pt,
            "nama_prodi":  clean[1],
            "jenjang":     clean[2],
            "wilayah":     clean[3],
            "nomor_sk":    clean[4],
            "peringkat":   clean[5],
            "tahun":       clean[6],
            "tgl_expired": clean[7] if clean[7] not in ("-", "") else None,
            "status":      clean[8] if len(clean) > 8 else None,
        })
    return records


def main():
    print("Fetching LAM-INFOKOM...")
    html_text = fetch_html()
    records = parse(html_text)
    print(f"Parsed: {len(records)} prodi")
    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {OUT}")

    print("\nPer jenjang:", dict(Counter(r["jenjang"] for r in records).most_common()))
    print("Per peringkat:", dict(Counter(r["peringkat"] for r in records).most_common()))
    print("Per status:", dict(Counter(r["status"] for r in records).most_common()))


if __name__ == "__main__":
    main()
