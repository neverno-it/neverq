"""
Migration 0023 — Offer enhancements + OfferUsage tracking.

Changes:
  1. Offer.offer_type — adds 'cart' choice (Cart Total Discount %)
  2. Offer.products   — new M2M to Product for multi-product offers
  3. OfferUsage       — new model; unique_together (offer, customer) enforces
                        one-use-per-customer per offer
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0022_seed_veg_nonveg_foodtypes'),
        ('accounts', '0011_alter_customer_is_approved_and_more'),
        ('orders', '0011_order_wallet_points'),
    ]

    operations = [
        # 1. Widen offer_type choices to include 'cart'
        migrations.AlterField(
            model_name='offer',
            name='offer_type',
            field=models.CharField(
                max_length=20,
                default='percent',
                choices=[
                    ('bogo',    'Buy 1 Get 1'),
                    ('free',    'Full Free'),
                    ('percent', 'Percentage Off'),
                    ('cart',    'Cart Total Discount (%)'),
                ],
            ),
        ),

        # 2. Add M2M products field on Offer
        migrations.AddField(
            model_name='offer',
            name='products',
            field=models.ManyToManyField(
                to='menu.product',
                blank=True,
                related_name='multi_offers',
                help_text='Multiple products this offer applies to.',
            ),
        ),

        # 3. Create OfferUsage model
        migrations.CreateModel(
            name='OfferUsage',
            fields=[
                ('id',       models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('used_at',  models.DateTimeField(auto_now_add=True)),
                ('offer',    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='usages', to='menu.offer')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='offer_usages', to='accounts.customer')),
                ('order',    models.ForeignKey(blank=True, null=True,
                                               on_delete=django.db.models.deletion.SET_NULL,
                                               related_name='offer_usages', to='orders.order')),
            ],
            options={
                'ordering': ['-used_at'],
                'unique_together': {('offer', 'customer')},
            },
        ),
    ]
