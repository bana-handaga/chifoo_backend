from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('universities', '0016_expand_trend_jenis_maxlength'),
    ]

    operations = [
        migrations.CreateModel(
            name='SintaScopusArtikel',
            fields=[
                ('id',          models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('eid',         models.CharField(db_index=True, max_length=50, unique=True, verbose_name='Scopus EID')),
                ('judul',       models.CharField(max_length=1000, verbose_name='Judul')),
                ('tahun',       models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Tahun')),
                ('sitasi',      models.PositiveIntegerField(default=0, verbose_name='Jumlah Sitasi')),
                ('kuartil',     models.CharField(blank=True, choices=[('Q1', 'Q1'), ('Q2', 'Q2'), ('Q3', 'Q3'), ('Q4', 'Q4'), ('', 'No Quartile')], max_length=2, verbose_name='Kuartil Jurnal')),
                ('jurnal_nama', models.CharField(blank=True, max_length=500, verbose_name='Nama Jurnal')),
                ('jurnal_url',  models.URLField(blank=True, max_length=400, verbose_name='URL Jurnal Scopus')),
                ('scopus_url',  models.URLField(blank=True, max_length=600, verbose_name='URL Artikel Scopus')),
                ('scraped_at',  models.DateTimeField(auto_now=True, verbose_name='Waktu Scrape')),
            ],
            options={
                'verbose_name': 'Scopus Artikel',
                'verbose_name_plural': 'Scopus Artikel',
                'ordering': ['-sitasi', '-tahun'],
            },
        ),
        migrations.AddIndex(
            model_name='sintascopusartikel',
            index=models.Index(fields=['tahun'], name='univ_scopus_tahun_idx'),
        ),
        migrations.AddIndex(
            model_name='sintascopusartikel',
            index=models.Index(fields=['kuartil'], name='univ_scopus_kuartil_idx'),
        ),
        migrations.CreateModel(
            name='SintaScopusArtikelAuthor',
            fields=[
                ('id',              models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('urutan_penulis',  models.PositiveSmallIntegerField(default=0, verbose_name='Urutan Penulis')),
                ('total_penulis',   models.PositiveSmallIntegerField(default=0, verbose_name='Total Penulis')),
                ('nama_singkat',    models.CharField(blank=True, max_length=100, verbose_name='Nama Singkat')),
                ('artikel',         models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='artikel_authors', to='universities.sintascopusartikel', verbose_name='Artikel')),
                ('author',          models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='scopus_artikels', to='universities.sintaauthor', verbose_name='Author')),
            ],
            options={
                'verbose_name': 'Scopus Artikel Author',
                'verbose_name_plural': 'Scopus Artikel Authors',
                'ordering': ['urutan_penulis'],
            },
        ),
        migrations.AddConstraint(
            model_name='sintascopusartikelauthor',
            constraint=models.UniqueConstraint(fields=['artikel', 'author'], name='uniq_scopus_artikel_author'),
        ),
        migrations.AddIndex(
            model_name='sintascopusartikelauthor',
            index=models.Index(fields=['author'], name='univ_scopus_author_idx'),
        ),
    ]
