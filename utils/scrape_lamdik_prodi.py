"""
Scrape data akreditasi prodi dari LAMDIK
https://lamdik.or.id/hasil-akreditasi/
Simpan ke utils/ext/lamdik_prodi.json
"""

import re
import html as html_module
import json
import urllib.request
from pathlib import Path

URL = "https://lamdik.or.id/hasil-akreditasi/"
OUT = Path(__file__).parent / "ext" / "lamdik_prodi.json"


def fetch_html():
    req = urllib.request.Request(URL, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": URL,
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def strip_city(name):
    """Hilangkan suffix ', KOTA' jika ada (format uppercase)."""
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
        nama_pt_raw = clean[1]
        nama_pt = strip_city(nama_pt_raw)
        tgl_sk       = clean[6] or None
        tgl_expired  = clean[7] or None
        records.append({
            "nama_pt_raw":  nama_pt_raw,
            "nama_pt":      nama_pt,
            "nama_prodi":   clean[2],
            "jenjang":      clean[3],
            "peringkat":    clean[4],
            "nomor_sk":     clean[5],
            "tgl_sk":       tgl_sk,
            "tgl_expired":  tgl_expired,
        })
    return records


def main():
    print("Fetching LAMDIK...")
    html_text = fetch_html()
    records = parse(html_text)
    print(f"Parsed: {len(records)} prodi")
    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {OUT}")

    # Ringkasan
    from collections import Counter
    print("\nPer jenjang:", dict(Counter(r["jenjang"] for r in records).most_common()))
    print("Per peringkat:", dict(Counter(r["peringkat"] for r in records).most_common()))


if __name__ == "__main__":
    main()
