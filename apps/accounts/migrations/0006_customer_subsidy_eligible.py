from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_merge_20260319_1444'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='subsidy_eligible',
            field=models.BooleanField(
                default=False,
                help_text='Whether this employee is eligible for company meal subsidy',
            ),
        ),
    ]
