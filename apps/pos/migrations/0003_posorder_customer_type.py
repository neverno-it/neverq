from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0002_posorder_card_fee'),
    ]

    operations = [
        migrations.AddField(
            model_name='posorder',
            name='customer_type',
            field=models.CharField(
                choices=[
                    ('staff',        'Staff'),
                    ('visitor',      'Visitor'),
                    ('room_service', 'Room Service'),
                ],
                default='visitor',
                max_length=20,
            ),
        ),
    ]
