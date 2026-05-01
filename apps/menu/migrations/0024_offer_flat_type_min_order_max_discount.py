"""
Migration 0024 — Offer: add Flat-off type + min_order_value + max_discount cap.

This unlocks Zomato/Swiggy-style offers:
  • Flat ₹20 off on orders above ₹80
  • 20% off capped at ₹100 on orders above ₹199
  • Any existing offer type with a minimum order threshold
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0023_offer_products_m2m_type_cart_offer_usage'),
    ]

    operations = [
        # Widen offer_type to include 'flat'
        migrations.AlterField(
            model_name='offer',
            name='offer_type',
            field=models.CharField(
                max_length=20,
                default='percent',
                choices=[
                    ('bogo',    'Buy 1 Get 1 Free'),
                    ('free',    '100% Free Product'),
                    ('percent', 'Percentage Off Product'),
                    ('cart',    'Cart % Discount'),
                    ('flat',    'Flat ₹ Off (Min Order)'),
                ],
            ),
        ),

        # Minimum cart value to unlock the offer
        migrations.AddField(
            model_name='offer',
            name='min_order_value',
            field=models.DecimalField(
                max_digits=10, decimal_places=2,
                null=True, blank=True,
                help_text='Minimum cart total (₹) needed to unlock this offer.',
            ),
        ),

        # Maximum discount cap for % offers
        migrations.AddField(
            model_name='offer',
            name='max_discount',
            field=models.DecimalField(
                max_digits=10, decimal_places=2,
                null=True, blank=True,
                help_text='Cap on discount amount (₹) for PERCENT/CART offers.',
            ),
        ),
    ]
