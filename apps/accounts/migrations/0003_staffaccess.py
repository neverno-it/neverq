from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0002_alter_customer_cod_payment_alter_customer_created_at_and_more'),
    ]
    operations = [
        migrations.CreateModel(
            name='StaffAccess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('landing_page', models.CharField(blank=True, default='', help_text='URL name for landing page', max_length=60)),
                ('visible_keys', models.JSONField(blank=True, default=list, help_text='List of menu keys this user can see/access')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='access_config', to='accounts.staffuser')),
            ],
            options={
                'verbose_name': 'Staff Access Config',
                'verbose_name_plural': 'Staff Access Configs',
            },
        ),
    ]
