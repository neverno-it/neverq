from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0016_productgallery_open_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='schedule_bypass',
            field=models.BooleanField(
                default=False,
                help_text='Superadmin only: product shows regardless of offering/category schedule.'
            ),
        ),
    ]
