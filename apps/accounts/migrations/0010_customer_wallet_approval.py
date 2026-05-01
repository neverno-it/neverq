from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_alter_customer_subsidy_amount_override_and_more'),
    ]

    operations = [
        migrations.AddField(model_name='customer', name='is_approved',
            field=models.BooleanField(default=True)),
        migrations.AddField(model_name='customer', name='wallet_balance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10)),
        migrations.AddField(model_name='customer', name='royalty_points',
            field=models.IntegerField(default=0)),
        migrations.CreateModel(
            name='WalletTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('txn_type', models.CharField(choices=[
                    ('topup','Wallet Top-up'),('order_debit','Order Payment'),
                    ('royalty_earned','Royalty Points Earned'),('royalty_redeem','Royalty Points Redeemed'),
                    ('refund','Refund'),('adjustment','Manual Adjustment'),
                ], max_length=30)),
                ('wallet_delta', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('points_delta', models.IntegerField(default=0)),
                ('balance_after', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('points_after', models.IntegerField(default=0)),
                ('order_ref', models.CharField(blank=True, max_length=50)),
                ('note', models.CharField(blank=True, max_length=255)),
                ('created_by', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='wallet_transactions', to='accounts.customer')),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Wallet Transaction'},
        ),
    ]
