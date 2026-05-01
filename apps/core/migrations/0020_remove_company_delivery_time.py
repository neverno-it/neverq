from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_merge_20260405_1301'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='company',
            name='delivery_time',
        ),
    ]
