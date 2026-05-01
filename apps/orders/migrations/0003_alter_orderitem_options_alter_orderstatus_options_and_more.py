import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0002_alter_product_company_price_alter_product_pos_qty_and_more'),
        ('orders', '0002_alter_orderitem_options_alter_orderstatus_options_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='orderitem',
            options={'ordering': ['id']},
        ),
        migrations.AlterModelOptions(
            name='orderstatus',
            options={'ordering': ['created_at']},
        ),
        migrations.AlterField(
            model_name='order',
            name='bill_to_company',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AlterField(
            model_name='order',
            name='my_pay',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AlterField(
            model_name='order',
            name='order_type',
            field=models.IntegerField(
                choices=[
                    (0, 'Home / Office Delivery'),
                    (1, 'Pickup from Counter'),
                    (2, 'Office Cafeteria'),
                ],
                default=0,
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='payment_mode',
            field=models.CharField(
                choices=[
                    ('cash', 'Cash on Delivery'),
                    ('online', 'Online Payment'),
                    ('monthly', 'Monthly Billing'),
                    ('company', 'Bill to Company'),
                ],
                default='online',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='orderitem',
            name='created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='orderstatus',
            name='created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
