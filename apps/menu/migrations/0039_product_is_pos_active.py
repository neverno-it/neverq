from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0038_site_category_availability'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='is_pos_active',
            field=models.BooleanField(
                default=True,
                help_text='Controls whether this product appears on the POS terminal. '
                          'Independent of the web and kiosk active status.'
            ),
        ),
    ]
