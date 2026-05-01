from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0018_alter_product_is_kiosk_active_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='featured_in_kiosk_extra',
            field=models.BooleanField(
                default=False,
                help_text='Show in the "Featured" section on the kiosk (max 10 shown).',
            ),
        ),
    ]
