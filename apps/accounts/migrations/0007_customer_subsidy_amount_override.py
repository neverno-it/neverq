from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_customer_subsidy_eligible'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='subsidy_amount_override',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Optional per-employee subsidy amount. Leave blank to use the company default subsidy.',
                max_digits=10,
                null=True,
            ),
        ),
    ]
