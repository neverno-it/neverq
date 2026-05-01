from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_wallettransaction_recharge_payment_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customer',
            name='meal_benefit',
            field=models.CharField(choices=[('none', 'No benefit'), ('subsidy', 'Subsidy once per day'), ('company_pay', 'Company-paid meals per day')], default='none', help_text='Per-customer meal benefit mode for the company-defined daily limit.', max_length=20),
        ),
    ]