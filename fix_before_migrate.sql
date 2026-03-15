-- ============================================================
--  Jalankan ini di phpMyAdmin SEBELUM python manage.py migrate
--  Menu: phpMyAdmin → pilih database → tab SQL → paste → Go
-- ============================================================

-- Pastikan database menggunakan utf8mb4
ALTER DATABASE `birotium_cpt`
    CHARACTER SET = utf8mb4
    COLLATE = utf8mb4_unicode_ci;
