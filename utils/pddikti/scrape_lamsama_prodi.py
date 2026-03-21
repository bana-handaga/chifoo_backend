"""
Scrape data akreditasi prodi dari LAMSAMA
https://lamsama.or.id/pencarian-data-akreditasi/
Simpan ke utils/ext/lamsama_prodi.json
"""

import html as html_module
import json
import re
import ssl
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

URL = "https://lamsama.or.id/wp-admin/admin-ajax.php"
OUT = Path(__file__).parent / "ext" / "lamsama_prodi.json"


def fetch_all():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # Ambil total dulu
    params = urllib.parse.urlencode({
        "action": "fetch_prodi_data",
        "draw": 1, "start": 0, "length": 1,
    }).encode()
    req = urllib.request.Request(URL, data=params, headers={
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        first = json.loads(r.read())
    total = first["recordsTotal"]
    print(f"Total records: {total}")

    # Ambil semua sekaligus
    params = urllib.parse.urlencode({
        "action": "fetch_prodi_data",
        "draw": 2, "start": 0, "length": total,
    }).encode()
    req = urllib.request.Request(URL, data=params, headers={
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        return json.loads(r.read())["data"]


def strip_city(name):
    m = re.search(r",\s+[A-Z][A-Z\s]+$", name)
    return name[: m.start()].strip() if m else name


def main():
    print("Fetching LAMSAMA...")
    rows = fetch_all()
    print(f"Fetched: {len(rows)} prodi")

    records = []
    for r in rows:
        nama_pt_raw = html_module.unescape(r.get("nama_pt", "")).strip()
        nama_pt = strip_city(nama_pt_raw)
        records.append({
            "kode_pt":     r.get("kode_pt"),
            "nama_pt_raw": nama_pt_raw,
            "nama_pt":     nama_pt,
            "kode_ps":     r.get("kode_ps"),
            "nama_prodi":  html_module.unescape(r.get("nama_ps", "")).strip(),
            "jenjang":     r.get("jenjang"),
            "peringkat":   r.get("peringkat"),
            "jenis":       r.get("jenis_akreditasi"),
            "nomor_sk":    r.get("no_sk"),
            "tgl_sk":      r.get("tgl_sk"),
            "tgl_expired": r.get("tgl_kadaluarsa") or None,
        })

    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {OUT}")
    print("\nPer jenjang:", dict(Counter(r["jenjang"] for r in records).most_common()))
    print("Per peringkat:", dict(Counter(r["peringkat"] for r in records).most_common()))


if __name__ == "__main__":
    main()
