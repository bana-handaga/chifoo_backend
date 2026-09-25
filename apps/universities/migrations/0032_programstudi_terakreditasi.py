from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('universities', '0031_add_terakreditasi_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='programstudi',
            name='akreditasi',
            field=models.CharField(choices=[('unggul', 'Unggul'), ('baik_sekali', 'Baik Sekali'), ('baik', 'Baik'), ('c', 'C'), ('terakreditasi', 'Terakreditasi'), ('belum', 'Belum Terakreditasi')], default='belum', max_length=20),
        ),
    ]
