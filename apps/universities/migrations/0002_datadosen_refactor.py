from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('universities', '0001_initial'),
    ]

    operations = [
        # Hapus semua data lama terlebih dahulu
        migrations.RunSQL(
            sql='DELETE FROM universities_datadosen;',
            reverse_sql=migrations.RunSQL.noop,
        ),

        # Hapus unique_together lama
        migrations.AlterUniqueTogether(
            name='datadosen',
            unique_together=set(),
        ),

        # Hapus kolom tahun
        migrations.RemoveField(
            model_name='datadosen',
            name='tahun',
        ),

        # Tambah kolom tahun_akademik
        migrations.AddField(
            model_name='datadosen',
            name='tahun_akademik',
            field=models.CharField(max_length=10, verbose_name='Tahun Akademik', default=''),
            preserve_default=False,
        ),

        # Tambah kolom semester
        migrations.AddField(
            model_name='datadosen',
            name='semester',
            field=models.CharField(
                choices=[('ganjil', 'Ganjil'), ('genap', 'Genap')],
                max_length=10,
                default='ganjil',
            ),
            preserve_default=False,
        ),

        # Tambah kolom program_studi (nullable FK)
        migrations.AddField(
            model_name='datadosen',
            name='program_studi',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='data_dosen',
                to='universities.programstudi',
            ),
        ),

        # Terapkan unique_together baru
        migrations.AlterUniqueTogether(
            name='datadosen',
            unique_together={('perguruan_tinggi', 'program_studi', 'tahun_akademik', 'semester')},
        ),

        # Update ordering via AlterModelOptions
        migrations.AlterModelOptions(
            name='datadosen',
            options={
                'ordering': ['-tahun_akademik', 'semester'],
                'verbose_name': 'Data Dosen',
                'verbose_name_plural': 'Data Dosen',
            },
        ),
    ]
