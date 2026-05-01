
from django.db import migrations, models


def forwards(apps, schema_editor):
    Customer = apps.get_model('accounts', 'Customer')
    Customer.objects.filter(subsidy_eligible=True).update(meal_benefit='subsidy')
    Customer.objects.filter(subsidy_eligible=False).update(meal_benefit='none')


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0007_customer_subsidy_amount_override'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='meal_benefit',
            field=models.CharField(
                choices=[('none', 'No benefit'), ('subsidy', 'Subsidy once per day'), ('company_pay', 'Company pay once per day')],
                default='none',
                help_text='Per-customer meal benefit mode for one order per day.',
                max_length=20,
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
