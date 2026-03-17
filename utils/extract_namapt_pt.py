"""
Extract namapt dan kodept dari ept_itpt.json
Output: list dengan field keyword (lowercase), target (uppercase), kode
"""

import json
import os

INPUT_FILE = os.path.join(os.path.dirname(__file__), "ept", "ept_itpt.json")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "ept", "namapt_list.json")


def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        records = json.load(f)

    results = []
    seen = set()

    for rec in records:
        pt_raw = rec.get("fields", {}).get("pt", "{}")
        try:
            pt = json.loads(pt_raw) if isinstance(pt_raw, str) else pt_raw
        except json.JSONDecodeError:
            continue

        namapt = pt.get("namapt", "").strip()
        kode   = pt.get("kode", "").strip()

        if not namapt or not kode:
            continue
        key = (namapt.lower(), kode)
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "keyword": namapt.lower(),
            "target":  namapt.upper(),
            "kode":    kode,
        })

    results.sort(key=lambda x: x["kode"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Total PT: {len(results)}")
    print(f"Output  : {OUTPUT_FILE}")

    # Preview 5 baris pertama
    for item in results[:5]:
        print(f"  keyword : {item['keyword']}")
        print(f"  target  : {item['target']}")
        print(f"  kode    : {item['kode']}")
        print()


if __name__ == "__main__":
    main()
