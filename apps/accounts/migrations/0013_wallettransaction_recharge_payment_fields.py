from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_customer_date_of_birth'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallettransaction',
            name='payment_mode',
            field=models.CharField(blank=True, choices=[('cash', 'Cash'), ('upi', 'UPI'), ('card', 'Card'), ('online', 'Online')], default='', max_length=20),
        ),
        migrations.AddField(
            model_name='wallettransaction',
            name='card_fee_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='wallettransaction',
            name='gross_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
