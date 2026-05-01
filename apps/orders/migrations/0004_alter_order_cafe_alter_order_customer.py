from django.db import migrations


class Migration(migrations.Migration):
    """
    Originally intended to AlterField order.cafe → SET_NULL and order.customer → PROTECT.
    Both fields were already defined correctly in 0001_initial, so this migration
    is a deliberate no-op that exists only to keep the dependency chain intact.
    """

    dependencies = [
        ('accounts', '0002_alter_customer_cod_payment_alter_customer_created_at_and_more'),
        ('menu', '0002_alter_product_company_price_alter_product_pos_qty_and_more'),
        ('orders', '0003_alter_orderitem_options_alter_orderstatus_options_and_more'),
    ]

    operations = []
