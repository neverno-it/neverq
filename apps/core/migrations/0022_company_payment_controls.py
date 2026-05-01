from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_company_fulfillment_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='company_pay_meals_per_day',
            field=models.PositiveSmallIntegerField(default=1, help_text='How many fully company-paid meals each eligible customer can use per day.'),
        ),
        migrations.AddField(
            model_name='company',
            name='pos_cash_enabled',
            field=models.BooleanField(default=True, help_text='Allow cash payments in POS terminal'),
        ),
        migrations.AddField(
            model_name='company',
            name='pos_upi_enabled',
            field=models.BooleanField(default=True, help_text='Allow UPI payments in POS terminal'),
        ),
        migrations.AddField(
            model_name='company',
            name='pos_card_enabled',
            field=models.BooleanField(default=True, help_text='Allow card payments in POS terminal'),
        ),
        migrations.AddField(
            model_name='company',
            name='pos_card_fee_percent',
            field=models.DecimalField(decimal_places=2, default=Decimal('3.50'), help_text='Extra percentage charged on POS card payments and wallet recharge by card.', max_digits=5),
        ),
    ]
