from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0033_offering_prep_start_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='featured_in_web',
            field=models.BooleanField(
                default=False,
                help_text='Pin this product in the "Featured Products" section on the customer web portal.',
            ),
        ),
    ]