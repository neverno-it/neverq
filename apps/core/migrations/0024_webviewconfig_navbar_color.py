from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_company_subsidy_meals_per_day'),
    ]

    operations = [
        migrations.AddField(
            model_name='webviewconfig',
            name='navbar_color',
            field=models.CharField(
                blank=True,
                max_length=20,
                help_text='Top navigation bar background colour e.g. #15233b. Solid — no transparency.',
            ),
        ),
    ]
