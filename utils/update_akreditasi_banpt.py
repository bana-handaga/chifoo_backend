"""Update akreditasi institusi di tabel universities_perguruantinggi
berdasarkan data dari outs/banpt_pt.json
"""

import json
import sys
import os
import MySQLdb
from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = dotenv_values(os.path.join(BASE_DIR, '.env'))

PERINGKAT_MAP = {
    'Unggul':               'unggul',
    'Baik Sekali':          'baik_sekali',
    'Baik':                 'baik',
    'B':                    'baik_sekali',   # rating lama BAN-PT
    'Terakreditasi':        'baik',          # rating lama generik
    'Tidak Terakreditasi':  'belum',
}

def main():
    with open(os.path.join(BASE_DIR, 'utils/outs/banpt_pt.json'), encoding='utf-8') as f:
        data = json.load(f)

    db = MySQLdb.connect(
        host=env['DB_HOST'], user=env['DB_USER'],
        passwd=env['DB_PASSWORD'], db=env['DB_NAME'],
        port=int(env['DB_PORT']), charset='utf8mb4',
    )
    cur = db.cursor()

    updated = skipped = not_found = 0
    issues = []

    for item in data:
        kode = item.get('kode')
        peringkat_raw = item.get('peringkat') or 'Tidak Terakreditasi'
        akreditasi = PERINGKAT_MAP.get(peringkat_raw)

        if akreditasi is None:
            issues.append(f"  UNKNOWN peringkat '{peringkat_raw}' for kode {kode}")
            skipped += 1
            continue

        nomor_sk      = item.get('nomor_sk') or ''
        tgl_expired   = item.get('tgl_expired') or None  # "YYYY-MM-DD" or None

        # Cek apakah kode_pt ada di DB
        cur.execute(
            'SELECT id, akreditasi_institusi FROM universities_perguruantinggi WHERE kode_pt = %s',
            (kode,)
        )
        row = cur.fetchone()
        if not row:
            issues.append(f"  NOT IN DB: kode={kode}  target={item['target']}")
            not_found += 1
            continue

        cur.execute(
            '''UPDATE universities_perguruantinggi
               SET akreditasi_institusi          = %s,
                   nomor_sk_akreditasi            = %s,
                   tanggal_kadaluarsa_akreditasi  = %s
               WHERE kode_pt = %s''',
            (akreditasi, nomor_sk, tgl_expired, kode)
        )
        updated += 1

    db.commit()
    db.close()

    print(f'Updated  : {updated}')
    print(f'Skipped  : {skipped}')
    print(f'Not in DB: {not_found}')
    if issues:
        print('\nIssues:')
        for i in issues:
            print(i)

if __name__ == '__main__':
    main()
