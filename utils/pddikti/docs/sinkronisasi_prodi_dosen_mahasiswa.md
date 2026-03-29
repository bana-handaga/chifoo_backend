# Sinkronisasi Jabatan dosen

## Sumber Data

LINK_SUMBER: https://pddikti.kemdiktisaintek.go.id/

## Target Semester

Semester: **Genap**
Tahun_Akademik: **2025/2026**
Label: **Genap 2025**

## Langkah-lagnkah:

1. **Buka halaman profile perguruan tinggi (pt)** 
    a. Baca nama dan KODEPT dari perguruan tinggi dari tabel universities_perguruantinggi, 
    b. Cari link halaman profil pt dengan link : https://pddikti.kemdiktisaintek.go.id/search/[nama perguruan tinggi], tunggu selama 2 menit, jika ada rsponse sebelum 2 menit lanjutkan proses yang lain batalkan proses sinkronisai,
    c. Jika nama perguruan tinggi ditemukan, akan ada tabel dengan kolom terdiri "KodePT", "Singkatan", "Nama Perguruan Tinggi" dan "Aksi". Selanjutnya dibawah kolom "Nama Perguruan Tinggi" cari nama yang persis sama dengan nama pt yang dicari, jika nama pt itu ditemukan lanjut cari link profil pt di bawah kolom "Aksi", dan buka linknya, ini akan menampilkan halaman profile pt, yang terdiri dari informasi profile pt dan daftar program studi, selanjutnya kita fokus ke daftar program studi.

2. **Baca SEMESTER AKTIF**
    a. Setelah halaman profile terbuka, cari daftar program studi di bawah tab 'Program Studi', 
    b. Kemudian lihat elemen dropdown di sebelah kanan label 'Data Pelaporan Tahunan', dan baca informasi tentang semester aktif saat ini
    c. Jika terbaca 'Ganjil 2025' maka ini berarti aktif di semester 'ganjil' tahun akademik '2025/2026', jika terbaca 'Genap 2025' berarti semester aktifnya adalah 'genap' tahun akademik '2025/2026'.

3. **Baca informasi Program studi (prodi)** 
    a. Cari tab dengan label program studi, dibawahnya ada elemen tabel terdiri 11 kolom, yaitu 'Kode',, 'Nama Program Studi', 'Status', 'Jenjang', 'Akreditasi', 'Jumlah Dosen Penghitung Rasio', 'Tetap', 'Tidak Tetap','Total', 'jumlah Mahasiswa', dan 'Rasio Dosen/Mahasiswa,
    b. Baca seluruh kolom termasuk link ke halaman detail program studi yang nempel di kolom 'Nama Program Studi'

4. **Update data prodi**
    a. Baca informasi prodi dari semua kolom, gunakan kolom 'Kode' sebagai acuan untuk mengupdate data prodi pada tabel universities_programstudi, 
    b. Kolom pada universities_programstudi yang perlu diupdate adalah kolom 'jenjang', 'akreditasi', dan 'is_active', is_active = True jika Status=Aktif.
    c. Cari id pt dan id prodi, dari KODEPT pada langkah 1a, cari perguruan_tinggi_id dari  tabel universities_perguruantinggi, dan dengan perguruan_tinggi_id (KODEPT) dan KODEPS cari program_studi_id di tabel universities_programstudi. 
    d. Selanjutnya dengan tambahan informasi semester-aktif yang diperoleh dari langkah 2, update entry dalam tabel universities_datadosen, jika tidak ditemukan insert data baru, kolom yang perlu di update adalah, 'dosen_tetap', 'dosen_tidak_tetap', 'dosen_rasio' dari 'Jumlah Dosen penghitung Rasio' dan update kolom 'rasio' dari 'Rasio Dosen/Mahasiswa'

5. **Update detail profile Prodi**
    a. Simpan link halaman profile pt saat ini.
    b. Buka link halaman detail program studi, yang melekat di label 'Nama Program Studi' perlu trigger 'on-hover', tunggu 2 menit jika tidak ada response batalkan kembali ke halaman profile pt. Link ke detail program studi ini bersifat dinamis jadi tidak perlu disimpan
    c. Cari tab dengan label [nama prodi], area dibawahnya ada informasi profile prodi, yang diperlukan untuk update tabel universities_programstudi adalah, 'Akreditasi', 'Taggal_berdiri', 'sk_selenggara'->'no_sk_akreditasi', 'Tanggal SK Selengara'->'Tanggal_kedaluarsa_akreditasi', 'phone'->telepon, 'email', 'website'. Kemudian pergi ke area teks dibawahnya ada heading tentang 'Informasi Umum'->'informasi_umum', 'Ilmu yang Dipelajari'->'ilmu_dipelajari', 'Kompetensi'->'Kompetensi'
    d. Eksekusi update tabel univerities_programstudi

6. **Update Tabel universities_profildosen**
    a. Masih di halaman profile program studi, scroll ke bawah cari tab 'Tenaga Pendidik', 
    b. Akan ditampilkan daftar dosen homebase yang ada di program studi saat ini dalam sebuah tabel yang terdiri atas 7 kolom,yaitu 'No', 'Nama', 'NIDN', 'NUPTK', 'Pendidikan', 'Status', 'Ikatan Kerja'.
    c. Gunakan NIDN sebagai ID untuk update ke table universities_profildosen, jika NIDN kosong gunakan 'NUPTK'. Insert data baru jika keduanya tidak ditemukan.
    d. Ulangi untuk  seluruh dosen yang ditampilkan,
    e. Jika ada nama dosen di halaman selanjutnya ikuti sampai ke halaman yang terakhir.

7. **Update Tabel universities_datamahasiswa**
    a. Cari Tab dengan label 'Mahasiswa' posisi ada disamping kanan tab 'Tenaga Tendik'.
    b. Ditampilkan tabel terdiri dari dua kolom, 'Semester' dan 'Jumlah Mahasiswa'. Penulisan semester terdiri dari Tahun akademik + Semester, contoh: '2025/2026 Genap'  sama dengan semester 'genap' tahun akademik '2025/2026'.
    c. Gunakan informasi perguruan_tinggi_id,  program_studi_id, semester dan tahun-akademik untuk mengupdate tabel universities_datamahasiswa, kombinasi empat kolom ini harus unik. Jika tidak ditemukan insert data baru.
    d. Lanjutkan baca baris data ini sampai tiga baris saja, tidak perlu ke halaman berikutnya.

8. **Selesai**