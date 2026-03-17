"""
Script untuk mengambil data akreditasi program studi dari LAM-PTKes
Sumber: https://lamptkes.org/Tampil-Database-Hasil-Akreditasi

Output: outs/lamptkes_prodi.json
"""

import json
import re
import os
import urllib.request
from datetime import datetime

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outs/lamptkes_prodi.json")
URL = "https://lamptkes.org/Tampil-Database-Hasil-Akreditasi"


def fetch_page() -> str:
    print(f"Fetching: {URL}")
    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_tgl(raw: str) -> str | None:
    """Konversi '24 Agustus 2026' -> '2026-08-24'"""
    BULAN = {
        "januari": 1, "februari": 2, "maret": 3, "april": 4,
        "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
        "september": 9, "oktober": 10, "november": 11, "desember": 12,
    }
    raw = raw.strip()
    if not raw:
        return None
    parts = raw.lower().split()
    if len(parts) == 3:
        try:
            d, m, y = parts
            month = BULAN.get(m)
            if month:
                return f"{int(y):04d}-{month:02d}-{int(d):02d}"
        except Exception:
            pass
    return raw if raw else None


def strip_city_suffix(name: str) -> str:
    """'STIKES YARSI PONTIANAK, PONTIANAK' → 'STIKES YARSI PONTIANAK'"""
    m = re.search(r",\s+[A-Z\s]+$", name)
    if m:
        return name[: m.start()].strip()
    return name


def parse_html(html: str) -> list[dict]:
    tbody = re.findall(r"<tbody[^>]*>(.*?)</tbody>", html, re.DOTALL)
    if not tbody:
        raise ValueError("Tidak ada <tbody> ditemukan di halaman")

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbody[0], re.DOTALL)
    records = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 9:
            continue
        cols = [clean(c) for c in cells]
        nama_pt_raw = cols[2]
        records.append({
            "nama_pt":     strip_city_suffix(nama_pt_raw),
            "nama_pt_raw": nama_pt_raw,
            "jenjang":     cols[1],
            "nama_prodi":  cols[3],
            "peringkat":   cols[4],
            "nomor_sk":    cols[5],
            "tahun":       cols[6],
            "tgl_expired": parse_tgl(cols[7]),
            "status":      cols[8],
        })
    return records


def main():
    html = fetch_page()
    records = parse_html(html)
    print(f"Total prodi LAM-PTKes: {len(records)}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"Saved to: {OUTPUT_FILE}")

    # Ringkasan peringkat
    from collections import Counter
    peringkat = Counter(r["peringkat"] for r in records)
    print("\nRingkasan peringkat:")
    for p, n in peringkat.most_common():
        print(f"  {n:>5}  {p}")


if __name__ == "__main__":
    main()
