"""
Scrape data akreditasi prodi dari LAMEMBA
https://lamemba.or.id/hasil_akreditasi/
Detail data (no SK, peringkat, tanggal) ada di atribut data-child (base64 JSON)
Simpan ke utils/ext/lamemba_prodi.json
"""

import base64
import html as html_module
import json
import re
import ssl
import urllib.request
from collections import Counter
from pathlib import Path

URL = "https://lamemba.or.id/hasil_akreditasi/"
OUT = Path(__file__).parent / "ext" / "lamemba_prodi.json"


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
    # Cari semua <tr data-child="...">...</tr>
    tr_pattern = re.compile(
        r'<tr[^>]+data-child="([^"]+)"[^>]*>(.*?)</tr>', re.DOTALL
    )
    records = []
    for m in tr_pattern.finditer(html_text):
        encoded = m.group(1)
        row_html = m.group(2)

        # Decode detail dari data-child
        try:
            detail = json.loads(base64.b64decode(encoded))
        except Exception:
            continue

        # Ambil kolom dari td
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
        clean = [html_module.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in cells]
        if len(clean) < 3:
            continue

        nama_pt_raw = clean[1]
        nama_pt = strip_city(nama_pt_raw)
        peringkat = html_module.unescape(re.sub(r"<[^>]+>", "", detail.get("Peringkat", ""))).strip()

        records.append({
            "nama_pt_raw": nama_pt_raw,
            "nama_pt":     nama_pt,
            "nama_prodi":  clean[2],
            "jenjang":     clean[3] if len(clean) > 3 else "",
            "peringkat":   peringkat,
            "nomor_sk":    detail.get("No. SK"),
            "tgl_sk":      detail.get("Tanggal SK"),
            "tgl_expired": detail.get("Kadaluarsa") or None,
        })
    return records


def main():
    print("Fetching LAMEMBA...")
    html_text = fetch_html()
    records = parse(html_text)
    print(f"Parsed: {len(records)} prodi")
    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {OUT}")
    print("\nPer jenjang:", dict(Counter(r["jenjang"] for r in records).most_common()))
    print("Per peringkat:", dict(Counter(r["peringkat"] for r in records).most_common()))


if __name__ == "__main__":
    main()
