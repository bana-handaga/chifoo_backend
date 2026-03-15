"""
ptma/db_backend.py
==================
Custom MySQL/MariaDB backend untuk PTMA Monitor.

Memaksa semua tabel dibuat dengan:
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci

Ini menyelesaikan error:
  "Foreign key constraint is incorrectly formed"
yang muncul di shared hosting cPanel karena default charset server = latin1.

Cara pakai — di settings/production.py ubah ENGINE:
  'ENGINE': 'ptma.db_backend'
"""

from django.db.backends.mysql import base, schema as mysql_schema


class DatabaseSchemaEditor(mysql_schema.DatabaseSchemaEditor):
    """
    Override sql_create_table untuk inject charset eksplisit
    di setiap DDL CREATE TABLE, sehingga tidak bergantung pada
    default charset server hosting.
    """
    sql_create_table = (
        "CREATE TABLE %(table)s (%(definition)s) "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )


class DatabaseWrapper(base.DatabaseWrapper):
    SchemaEditorClass = DatabaseSchemaEditor
