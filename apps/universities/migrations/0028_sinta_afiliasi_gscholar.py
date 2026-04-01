from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('universities', '0027_add_sinta_author_sync'),
    ]

    operations = [
        # Tambah choices GScholar ke SintaTrendTahunan.jenis (choices tidak ubah schema)
        migrations.AlterField(
            model_name='sintatrendtahunan',
            name='jenis',
            field=models.CharField(
                max_length=10,
                choices=[
                    ('scopus',   'Publikasi Scopus'),
                    ('research', 'Penelitian'),
                    ('service',  'Pengabdian Masyarakat'),
                    ('gs_pub',   'Google Scholar Publikasi'),
                    ('gs_cite',  'Google Scholar Sitasi'),
                ],
                verbose_name='Jenis',
            ),
        ),
        # Model baru: SintaAfiliasiGScholarArtikel
        migrations.CreateModel(
            name='SintaAfiliasiGScholarArtikel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pub_id',     models.CharField(db_index=True, max_length=200, verbose_name='Publication ID / URL key')),
                ('judul',      models.CharField(max_length=1000, verbose_name='Judul')),
                ('penulis',    models.TextField(blank=True, verbose_name='Penulis')),
                ('jurnal',     models.CharField(blank=True, max_length=500, verbose_name='Jurnal')),
                ('tahun',      models.PositiveSmallIntegerField(blank=True, db_index=True, null=True, verbose_name='Tahun')),
                ('sitasi',     models.PositiveIntegerField(default=0, verbose_name='Jumlah Sitasi')),
                ('url',        models.URLField(blank=True, max_length=800, verbose_name='URL Artikel')),
                ('scraped_at', models.DateTimeField(auto_now=True, verbose_name='Waktu Scrape')),
                ('afiliasi',   models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='gscholar_artikels',
                    to='universities.sintaafiliasi',
                    verbose_name='SINTA Afiliasi',
                )),
            ],
            options={
                'verbose_name':        'SINTA Afiliasi GScholar Artikel',
                'verbose_name_plural': 'SINTA Afiliasi GScholar Artikel',
                'ordering':            ['-tahun', '-sitasi'],
                'unique_together':     {('afiliasi', 'pub_id')},
                'indexes': [
                    models.Index(fields=['afiliasi', 'tahun'], name='univ_affil_gs_art_idx'),
                ],
            },
        ),
    ]
