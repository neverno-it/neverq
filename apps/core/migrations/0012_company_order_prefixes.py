from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_alter_company_kiosk_logo_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='web_order_prefix',
            field=models.CharField(
                max_length=10, blank=True, default='',
                help_text='Prefix for web orders, e.g. "WEB" → WEB-260401-0001. Leave blank to use the default "WEB".'
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='kiosk_order_prefix',
            field=models.CharField(
                max_length=10, blank=True, default='',
                help_text='Prefix for kiosk orders, e.g. "KIO" → KIO-260401-0001. Leave blank to use the default "KIO".'
            ),
        ),
    ]
