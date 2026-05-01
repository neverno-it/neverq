from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_customer_cod_payment_alter_customer_created_at_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DashboardMenuAccess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allowed_keys', models.JSONField(blank=True, default=list)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('staff_user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='dashboard_menu_access', to='accounts.staffuser')),
            ],
            options={
                'verbose_name': 'Dashboard Menu Access',
                'verbose_name_plural': 'Dashboard Menu Access',
            },
        ),
    ]
