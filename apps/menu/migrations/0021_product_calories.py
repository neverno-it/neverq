from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0020_alter_product_featured_in_kiosk_extra'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='calories',
            field=models.PositiveIntegerField(
                null=True,
                blank=True,
                help_text='Approximate calorie count (kcal) per serving. Leave blank if unknown.',
            ),
        ),
    ]
