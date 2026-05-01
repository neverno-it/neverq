from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0027_category_slug_unique_product_slug_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='preparation_time_minutes',
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    'Category-level preparation time in minutes. '
                    'Used as the auto-ready timer when no product-level override exists. '
                    '0 = no auto-ready for this category (cashier marks ready manually).'
                ),
            ),
        ),
    ]
