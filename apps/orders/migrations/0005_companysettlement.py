from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_company_order_open_days_company_free_meal_products'),
        ('orders', '0004_alter_order_cafe_alter_order_customer'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CompanySettlement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payment_date', models.DateField()),
                ('amount_received', models.DecimalField(decimal_places=2, max_digits=10)),
                ('reference_no', models.CharField(blank=True, max_length=100)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='settlements', to='core.company')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='company_settlement_entries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Company Settlement',
                'verbose_name_plural': 'Company Settlements',
                'ordering': ['-payment_date', '-created_at'],
            },
        ),
    ]