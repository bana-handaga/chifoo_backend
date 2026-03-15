"""
Management command: fetch_akreditasi_banpt

Mengambil data akreditasi institusi dari BAN-PT dan mengupdate tabel
universities_perguruantinggi (nomor_sk_akreditasi, tanggal_sk_akreditasi,
tanggal_kadaluarsa_akreditasi, akreditasi_institusi).

Usage:
    python manage.py fetch_akreditasi_banpt            # dry-run (preview)
    python manage.py fetch_akreditasi_banpt --apply    # simpan ke database
    python manage.py fetch_akreditasi_banpt --apply --min-score 80


    # Preview dulu (tanpa simpan)
    python manage.py fetch_akreditasi_banpt

    # Simpan ke database
    python manage.py fetch_akreditasi_banpt --apply

    # Turunkan threshold kecocokan nama (default 75%)
    python manage.py fetch_akreditasi_banpt --apply --min-score 60

    # Proses hanya satu PT (by ID)
    python manage.py fetch_akreditasi_banpt --apply --pt-id 5


    Yang diambil dari BAN-PT:

Field	Sumber BAN-PT
nomor_sk_akreditasi	Nomor SK
tanggal_sk_akreditasi	Diekstrak dari format /III/2026 di nomor SK → 2026-03-01
tanggal_kadaluarsa_akreditasi	Tanggal Kedaluwarsa
akreditasi_institusi	Peringkat (Unggul/Baik Sekali/Baik)


"""

import re
import requests
from datetime import date, datetime
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.universities.models import PerguruanTinggi


BANPT_URL = (
    "https://www.banpt.or.id/direktori/model/dir_aipt/get_data_institusi.php"
)
BANPT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Referer": (
        "https://www.banpt.or.id/direktori/institusi/pencarian_institusi.php"
    ),
}

# Pemetaan manual: nama PT di database → nama PT di BAN-PT (exact match)
# Tambahkan di sini jika nama di DB berbeda dengan nama di BAN-PT.
ALIAS_MAP = {
    # Nama DB berbeda dengan BAN-PT → petakan ke nama BAN-PT yang benar
    "Universitas Muhammadiyah Luwuk": "Universitas Muhammadiyah Luwuk Banggai",

    # Belum / tidak terakreditasi di BAN-PT → set None agar dilewati
    "Institut Muhammadiyah Darul Arqam Garut": None,
    "STIT Muhammadiyah Bangil, Pasuruan": None,
}

# Mapping peringkat BAN-PT → choices model
PERINGKAT_MAP = {
    "unggul": "unggul",
    "baik sekali": "baik_sekali",
    "baik": "baik",
    "terakreditasi": "baik",   # fallback
    "b": "baik",
    "a": "baik_sekali",
}

# Prefiks yang diabaikan saat matching nama
_STRIP = re.compile(
    r"^(universitas|institut|sekolah tinggi|politeknik|akademi|stmik|stie|stik|stkip"
    r"|stit|stai|stis|stt|amik|amd|amk|ama)\s+",
    re.I,
)


def _normalize(name: str) -> str:
    """Lowercase, hapus prefiks umum, strip spasi."""
    name = name.lower().strip()
    name = _STRIP.sub("", name)
    return re.sub(r"\s+", " ", name)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio() * 100


def _best_match(pt_nama: str, banpt_records: list, min_score: float):
    """Kembalikan (record, score) terbaik atau (None, 0) jika tidak cukup.

    Cek ALIAS_MAP terlebih dahulu untuk pemetaan manual (score 100%).
    """
    # 1. Cek alias manual
    if pt_nama in ALIAS_MAP:
        target_nama = ALIAS_MAP[pt_nama]
        if target_nama is None:
            # Eksplisit tidak ada di BAN-PT, lewati
            return None, -1.0
        for rec in banpt_records:
            if rec["nama"].strip().lower() == target_nama.strip().lower():
                return rec, 100.0
        # Alias didefinisikan tapi nama BAN-PT tidak ditemukan
        return None, 0.0

    # 2. Fuzzy matching
    best_rec, best_score = None, 0.0
    for rec in banpt_records:
        score = _similarity(pt_nama, rec["nama"])
        if score > best_score:
            best_score = score
            best_rec = rec
    if best_score >= min_score:
        return best_rec, best_score
    return None, best_score


def _parse_date(val: str):
    """Parse tanggal YYYY-MM-DD dari BAN-PT."""
    if not val or val.strip() == "-":
        return None
    try:
        return datetime.strptime(val.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_tanggal_sk(no_sk: str) -> date | None:
    """
    Coba ekstrak tanggal dari nomor SK.
    Format umum: .../<bulan_romawi>/<tahun>
    Contoh: 137/SK/BAN-PT/Ak.PNB/2.0/PT/III/2026
    """
    romawi = {
        "I": 1, "II": 2, "III": 3, "IV": 4,
        "V": 5, "VI": 6, "VII": 7, "VIII": 8,
        "IX": 9, "X": 10, "XI": 11, "XII": 12,
    }
    # Cari pola /ROMAWI/TAHUN di akhir
    m = re.search(r"/([IVX]+)/(\d{4})\s*$", no_sk.replace("\\", "/"))
    if m:
        bulan = romawi.get(m.group(1))
        tahun = int(m.group(2))
        if bulan and 2000 <= tahun <= 2100:
            return date(tahun, bulan, 1)
    return None


class Command(BaseCommand):
    help = "Ambil data akreditasi dari BAN-PT dan update database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Simpan perubahan ke database (default: dry-run).",
        )
        parser.add_argument(
            "--min-score",
            type=float,
            default=75.0,
            help="Skor minimum kecocokan nama (0–100, default: 75).",
        )
        parser.add_argument(
            "--pt-id",
            type=int,
            default=None,
            help="Proses hanya satu PT berdasarkan ID.",
        )

    def handle(self, *args, **options):
        apply    = options["apply"]
        min_score = options["min_score"]
        pt_id    = options["pt_id"]

        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(self.style.WARNING(
            f"\n{'='*60}\n  Mode: {mode}  |  Min-score: {min_score}\n{'='*60}"
        ))

        # 1. Ambil semua data BAN-PT
        self.stdout.write("Mengambil data dari BAN-PT...")
        try:
            resp = requests.get(BANPT_URL, headers=BANPT_HEADERS, timeout=30)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as exc:
            raise CommandError(f"Gagal mengambil data BAN-PT: {exc}")

        banpt_records = []
        for row in raw.get("data", []):
            banpt_records.append({
                "nama":        row[0],
                "peringkat":   row[1],
                "nomor_sk":    row[2].replace("\\/", "/"),
                "tanggal_exp": row[5],
            })

        self.stdout.write(
            self.style.SUCCESS(f"  {len(banpt_records)} data institusi dimuat dari BAN-PT.")
        )

        # 2. Ambil PT dari database
        qs = PerguruanTinggi.objects.all()
        if pt_id:
            qs = qs.filter(pk=pt_id)
        pt_list = list(qs.order_by("nama"))
        self.stdout.write(f"  {len(pt_list)} PT ditemukan di database.\n")

        matched, unmatched, updated = [], [], 0

        for pt in pt_list:
            rec, score = _best_match(pt.nama, banpt_records, min_score)

            if rec is None:
                unmatched.append((pt, score))
                continue

            matched.append((pt, rec, score))

        # 3. Tampilkan & simpan
        self.stdout.write(
            self.style.HTTP_INFO(
                f"{'PT (database)':<45} {'BAN-PT Match':<45} {'Score':>6}  Perubahan"
            )
        )
        self.stdout.write("-" * 120)

        changes = []
        for pt, rec, score in matched:
            nomor_sk   = rec["nomor_sk"]
            tgl_sk     = _parse_tanggal_sk(nomor_sk)
            tgl_exp    = _parse_date(rec["tanggal_exp"])
            peringkat  = PERINGKAT_MAP.get(rec["peringkat"].lower(), None)

            diff_parts = []
            if pt.nomor_sk_akreditasi != nomor_sk:
                diff_parts.append(f"sk: {pt.nomor_sk_akreditasi or '-'} → {nomor_sk}")
            if pt.tanggal_kadaluarsa_akreditasi != tgl_exp:
                diff_parts.append(
                    f"exp: {pt.tanggal_kadaluarsa_akreditasi or '-'} → {tgl_exp or '-'}"
                )
            if peringkat and pt.akreditasi_institusi != peringkat:
                diff_parts.append(
                    f"akr: {pt.akreditasi_institusi} → {peringkat}"
                )

            diff_str = " | ".join(diff_parts) if diff_parts else "(tidak ada perubahan)"
            self.stdout.write(
                f"{pt.nama[:44]:<45} {rec['nama'][:44]:<45} {score:>5.1f}%  {diff_str}"
            )

            if diff_parts:
                changes.append((pt, nomor_sk, tgl_sk, tgl_exp, peringkat))

        # 4. Simpan jika --apply
        if apply and changes:
            with transaction.atomic():
                for pt, nomor_sk, tgl_sk, tgl_exp, peringkat in changes:
                    pt.nomor_sk_akreditasi = nomor_sk
                    if tgl_sk:
                        pt.tanggal_sk_akreditasi = tgl_sk
                    if tgl_exp:
                        pt.tanggal_kadaluarsa_akreditasi = tgl_exp
                    if peringkat:
                        pt.akreditasi_institusi = peringkat
                    pt.save(update_fields=[
                        "nomor_sk_akreditasi",
                        "tanggal_sk_akreditasi",
                        "tanggal_kadaluarsa_akreditasi",
                        "akreditasi_institusi",
                    ])
                    updated += 1

        # 5. Ringkasan
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS(
            f"  Cocok   : {len(matched)} PT"
        ))
        self.stdout.write(self.style.WARNING(
            f"  Berubah : {len(changes)} PT"
        ))
        if apply:
            self.stdout.write(self.style.SUCCESS(
                f"  Disimpan: {updated} PT"
            ))
        else:
            self.stdout.write(self.style.NOTICE(
                "  (gunakan --apply untuk menyimpan ke database)"
            ))

        excluded = [(pt, s) for pt, s in unmatched if s == -1.0]
        no_match = [(pt, s) for pt, s in unmatched if s != -1.0]

        if excluded:
            self.stdout.write(self.style.NOTICE(
                f"\n  Dikecualikan (ALIAS_MAP=None, {len(excluded)} PT):"
            ))
            for pt, _ in excluded:
                self.stdout.write(f"    {pt.nama}")

        if no_match:
            self.stdout.write(self.style.ERROR(
                f"\n  Tidak cocok ({len(no_match)} PT, "
                f"skor tertinggi di bawah {min_score}%):"
            ))
            for pt, score in sorted(no_match, key=lambda x: -x[1]):
                self.stdout.write(
                    f"    [{score:>4.1f}%] {pt.nama}"
                )
        self.stdout.write("")
