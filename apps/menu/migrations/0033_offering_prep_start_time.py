from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0032_offering_image_and_galleries'),
    ]

    operations = [
        migrations.AddField(
            model_name='offering',
            name='prep_start_time',
            field=models.TimeField(
                blank=True,
                null=True,
                help_text=(
                    'Kitchen prep gate: auto-ready countdown will not start before this time. '
                    'Leave blank to keep existing behaviour (countdown starts from order time). '
                    'Example: 11:30 means kitchen starts preparing at 11:30 AM regardless of when the order was placed.'
                ),
            ),
        ),
    ]
