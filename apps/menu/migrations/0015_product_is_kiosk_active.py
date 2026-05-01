from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0014_alter_cafe_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='is_kiosk_active',
            field=models.BooleanField(
                default=True,
                help_text='Controls visibility in the self-service kiosk. Independent of web active status.'
            ),
        ),
    ]
