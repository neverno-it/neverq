from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0022_company_payment_controls'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='subsidy_meals_per_day',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='How many subsidized meals each eligible customer can use per day.',
            ),
        ),
    ]
