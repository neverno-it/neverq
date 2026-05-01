from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_remove_company_kiosk_order_prefix_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='web_order_prefix',
            field=models.CharField(
                max_length=10, blank=True, default='',
                help_text='Prefix for web orders (e.g. "WEB"). Leave blank for default "WEB".',
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='kiosk_order_prefix',
            field=models.CharField(
                max_length=10, blank=True, default='',
                help_text='Prefix for kiosk orders (e.g. "KIO"). Leave blank for default "KIO".',
            ),
        ),
    ]
