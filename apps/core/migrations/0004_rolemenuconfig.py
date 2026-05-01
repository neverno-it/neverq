from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [('core', '0003_staticpage_notification_coupon')]
    operations = [
        migrations.CreateModel(
            name='RoleMenuConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(max_length=20, unique=True)),
                ('visible_keys', models.JSONField(default=list, help_text='List of menu key strings')),
            ],
        ),
    ]
