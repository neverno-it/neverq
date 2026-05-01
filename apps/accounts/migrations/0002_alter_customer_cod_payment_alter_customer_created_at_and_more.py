from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customer',
            name='cod_payment',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='customer',
            name='created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='customer',
            name='monthly_payment',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='staffuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('superadmin', 'Super Admin'),
                    ('admin', 'Company Admin'),
                    ('cafeman', 'Chef / Cafe Manager'),
                    ('pos', 'Cashier / POS'),
                    ('reports', 'Reports Viewer'),
                ],
                default='admin',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='webcookie',
            name='delivery_type',
            field=models.CharField(blank=True, max_length=50),
        ),
    ]
