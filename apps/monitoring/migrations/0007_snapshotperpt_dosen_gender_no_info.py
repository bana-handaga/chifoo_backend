from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0006_snapshotlaporan_total_pt_non_aktif'),
    ]

    operations = [
        migrations.AddField(
            model_name='snapshotperpt',
            name='dosen_gender_no_info',
            field=models.IntegerField(default=0),
        ),
    ]
