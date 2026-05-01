from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='posorder',
            name='base_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='posorder',
            name='card_fee_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
