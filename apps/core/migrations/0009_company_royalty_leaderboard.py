from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_company_payment_theme_royalty'),
        ('accounts', '0010_customer_wallet_approval'),
    ]

    operations = [
        migrations.AddField(model_name='company', name='royalty_reward_mode',
            field=models.CharField(choices=[('amount','Highest spend amount'),('count','Most number of orders')],
                                   default='amount', max_length=10)),
        migrations.AddField(model_name='company', name='royalty_reward_period',
            field=models.CharField(choices=[('daily','Daily'),('weekly','Weekly'),('monthly','Monthly')],
                                   default='monthly', max_length=10)),
        migrations.AddField(model_name='company', name='royalty_rank1_points',
            field=models.IntegerField(default=500)),
        migrations.AddField(model_name='company', name='royalty_rank2_points',
            field=models.IntegerField(default=250)),
        migrations.AddField(model_name='company', name='royalty_rank3_points',
            field=models.IntegerField(default=100)),
        migrations.CreateModel(
            name='RoyaltyAward',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('period_key', models.CharField(max_length=20)),
                ('rank', models.IntegerField()),
                ('points', models.IntegerField(default=0)),
                ('awarded_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='royalty_awards', to='core.company')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='royalty_awards', to='accounts.customer')),
            ],
            options={'ordering': ['-awarded_at']},
        ),
        migrations.AlterUniqueTogether(
            name='royaltyaward',
            unique_together={('company', 'period_key', 'rank')},
        ),
    ]
