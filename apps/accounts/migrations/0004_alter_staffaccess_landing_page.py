from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0003_staffaccess'),
    ]
    operations = [
        migrations.AlterField(
            model_name='staffaccess',
            name='landing_page',
            field=models.CharField(blank=True, default='', help_text='URL name for landing page e.g. dashboard:home', max_length=60),
        ),
    ]
