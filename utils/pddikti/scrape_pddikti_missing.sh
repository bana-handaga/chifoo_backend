#!/bin/bash
# Scrape ulang PDDIKTI untuk PT yang punya prodi belum terfile
# --resume: skip prodi yang file output-nya sudah ada

set -e
cd /home/ubuntu/_chifoo/chifoo_backend
PYTHON="conda run -n chifoo python3"
SCRIPT="utils/scrape_pddikti_detailprodi.py"

run() {
    local keyword="$1"
    local nama="$2"
    local kode="$3"
    echo ""
    echo "========================================"
    echo "PT: $nama ($kode)"
    echo "========================================"
    $PYTHON $SCRIPT --keyword "$keyword" --nama "$nama" --kode "$kode" --resume
}

# 1. Institut 'Aisyiyah Sulawesi Selatan (0 file)
run "institut \`aisyiyah sulawesi selatan" \
    "INSTITUT \`AISYIYAH SULAWESI SELATAN" "212184"

# 2. Institut Bisnis Muhammadiyah Bekasi (0 file)
run "institut bisnis muhammadiyah bekasi" \
    "INSTITUT BISNIS MUHAMMADIYAH BEKASI" "042010"

# 3. Institut Pendidikan dan Teknologi Aisyiyah Riau (0 file)
run "institut pendidikan dan teknologi \`aisyiyah riau" \
    "INSTITUT PENDIDIKAN DAN TEKNOLOGI \`AISYIYAH RIAU" "172025"

# 4. Politeknik Muhammadiyah Magelang (0 file)
run "politeknik muhammadiyah magelang" \
    "POLITEKNIK MUHAMMADIYAH MAGELANG" "065004"

# 5. STAI Muhammadiyah Blora (0 file)
run "stai muhammadiyah (staim) blora, jawa tengah" \
    "STAI MUHAMMADIYAH (STAIM) BLORA, JAWA TENGAH" "213388"

# 6. STIT Muhammadiyah Banjar (0 file)
run "stit muhammadiyah banjar" \
    "STIT MUHAMMADIYAH BANJAR" "213137"

# 7. UM A.R. Fachruddin — ada file, scrape ulang yang kurang
run "universitas muhammadiyah a.r. fachruddin" \
    "UNIVERSITAS MUHAMMADIYAH A.R. FACHRUDDIN" "041101"

# 8. UM Bulukumba (0 file)
run "universitas muhammadiyah bulukumba" \
    "UNIVERSITAS MUHAMMADIYAH BULUKUMBA" "091061"

# 9. UM Madiun — ada file, scrape ulang yang kurang
run "universitas muhammadiyah madiun" \
    "UNIVERSITAS MUHAMMADIYAH MADIUN" "071102"

# 10. UM Makassar — ada file, scrape ulang yang kurang
run "universitas muhammadiyah makassar" \
    "UNIVERSITAS MUHAMMADIYAH MAKASSAR" "091004"

# 11. UM Pare-pare (0 file)
run "universitas muhammadiyah pare-pare" \
    "UNIVERSITAS MUHAMMADIYAH PARE-PARE" "091024"

# 12. UM Semarang — ada file, scrape ulang yang kurang
run "universitas muhammadiyah semarang" \
    "UNIVERSITAS MUHAMMADIYAH SEMARANG" "061026"

echo ""
echo "========================================"
echo "Semua selesai. Jalankan update_akreditasi_pddikti.py untuk update DB."
echo "========================================"
