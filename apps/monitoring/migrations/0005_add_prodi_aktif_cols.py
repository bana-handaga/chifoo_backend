from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0004_add_dosen_detail_cols'),
    ]

    operations = [
        migrations.AddField(
            model_name='snapshotperpt',
            name='prodi_aktif',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='snapshotperpt',
            name='prodi_non_aktif',
            field=models.IntegerField(default=0),
        ),
    ]
