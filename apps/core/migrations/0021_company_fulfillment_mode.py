from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_remove_company_delivery_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='fulfillment_mode',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('pickup', 'Pickup (QR-based collection at counter)'),
                    ('packet_delivery', 'Packet Delivery (our staff delivers to company)'),
                ],
                default='pickup',
                help_text=(
                    'Pickup: customers collect at counter using QR. '
                    'Packet Delivery: our staff delivers packed food to company — no QR used.'
                ),
            ),
        ),
    ]
