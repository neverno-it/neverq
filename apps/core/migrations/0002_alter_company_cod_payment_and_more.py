from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='company',
            name='cod_payment',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='company',
            name='delivery_time',
            field=models.IntegerField(default=12),
        ),
        migrations.AlterField(
            model_name='company',
            name='store_status',
            field=models.BooleanField(default=True),
        ),
    ]
