from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        """
        Patch Django MySQL SchemaEditor saat app sudah siap.
        Memaksa semua CREATE TABLE pakai utf8mb4_unicode_ci.
        """
        try:
            from django.db.backends.mysql import schema as mysql_schema
            mysql_schema.DatabaseSchemaEditor.sql_create_table = (
                "CREATE TABLE %(table)s (%(definition)s) "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        except Exception:
            pass
