from django.db import migrations, models


DEFAULT_ORDER_OPEN_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0007_alter_advertise_image_alter_mediaasset_image'),
        ('core', '0004_rolemenuconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='order_open_days',
            field=models.JSONField(blank=True, default=DEFAULT_ORDER_OPEN_DAYS),
        ),
        migrations.AddField(
            model_name='company',
            name='free_meal_products',
            field=models.ManyToManyField(blank=True, help_text='Only these mapped products are eligible for free meal or subsidy cover for this company.', related_name='free_meal_companies', to='menu.product'),
        ),
    ]