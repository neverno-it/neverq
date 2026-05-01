from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0014_alter_customer_meal_benefit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customer',
            name='meal_benefit',
            field=models.CharField(
                choices=[
                    ('none', 'No benefit'),
                    ('subsidy', 'Subsidized meals per day'),
                    ('company_pay', 'Company-paid meals per day'),
                ],
                default='none',
                help_text='Per-customer meal benefit mode for the company-defined daily limit.',
                max_length=20,
            ),
        ),
    ]
