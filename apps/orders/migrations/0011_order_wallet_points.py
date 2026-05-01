from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0010_counterticket_collected_at_counterticket_scan_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='wallet_used',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='order',
            name='points_redeemed',
            field=models.IntegerField(default=0),
        ),
    ]
