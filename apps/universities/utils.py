"""Utility helpers untuk apps.universities"""

# ── Deteksi PT Indonesia ────────────────────────────────────────────────────
# Kata kunci yang hanya muncul pada nama PT Indonesia
_INDO_KEYWORDS = (
    'universitas ', 'universitas_', 'institut ', 'sekolah tinggi',
    'politeknik', 'akademi ', 'poltekkes', 'amik ', 'akafarma',
    'uin ', 'iain ', 'stain ', 'stikes ', 'stie ', 'stkip ', 'stmik ',
    'stit ', 'stai ', 'stiab', 'stiba', 'stisip', 'stipar', 'stiper',
    'stipro', 'stisia', 'stimik', 'stimart', 'stisnu',
    'institu', 'akbid', 'akper', 'akfar', 'stt ',
)

# Nama PT Indonesia yang tidak mengandung kata kunci di atas
_INDO_EXACT = frozenset({
    'ipb', 'ipb university', 'itb', 'its', 'ui', 'ugm', 'undip', 'unair',
    'unhas', 'uns', 'uny', 'unesa', 'unm', 'unimed', 'unlam', 'unmul',
    'unsyiah', 'unram', 'undana', 'uncen', 'unipa', 'umm', 'ums', 'umy',
    'uii', 'uisb', 'umj', 'uin', 'iain',
})


def is_pt_indonesia(nama_pt: str) -> bool:
    """
    Kembalikan True jika nama_pt dikenali sebagai PT Indonesia.
    Kembalikan False (→ luar negeri) jika tidak dikenali.
    """
    if not nama_pt:
        return False
    n = nama_pt.lower().strip()
    # Cek kata kunci
    for kw in _INDO_KEYWORDS:
        if kw in n:
            return True
    # Cek nama pendek / akronim
    if n in _INDO_EXACT:
        return True
    # Angka prefiks (kadang nama PT Indonesia diawali kode, mis. "903095 Arellano")
    # → tetap false, biarkan logika utama memutuskan dari sisa nama
    return False


def flag_luar_negeri(nama_pt: str) -> bool:
    """Kembalikan True jika PT tersebut luar negeri."""
    if not nama_pt or nama_pt.strip() in ('N/A', '-', ''):
        return False          # data tidak diketahui → anggap bukan luar negeri
    return not is_pt_indonesia(nama_pt)
