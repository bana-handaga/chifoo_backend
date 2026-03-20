from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0005_add_prodi_aktif_cols'),
    ]

    operations = [
        migrations.AddField(
            model_name='snapshotlaporan',
            name='total_pt_non_aktif',
            field=models.IntegerField(default=0),
        ),
    ]
