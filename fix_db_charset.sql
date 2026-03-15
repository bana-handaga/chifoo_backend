-- ============================================================
--  PTMA Monitor — Fix Database Charset
--  Jalankan script ini di cPanel > phpMyAdmin SEBELUM migrate
--  atau via Terminal sebelum python manage.py migrate
--
--  Ganti 'usercpanel_ptmadb' dengan nama database Anda
-- ============================================================

-- 1. Set charset & collation default database
ALTER DATABASE `birotium_cpt`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- 2. Jika migrate sudah pernah dijalankan dan tabel sudah ada,
--    jalankan juga perintah berikut untuk fix tabel yang ada:
-- (Uncomment jika perlu)
--
-- ALTER TABLE `auth_permission`    CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- ALTER TABLE `auth_group`         CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- ALTER TABLE `auth_group_permissions` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- ALTER TABLE `auth_user`          CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- ALTER TABLE `django_content_type` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- ALTER TABLE `django_admin_log`   CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
