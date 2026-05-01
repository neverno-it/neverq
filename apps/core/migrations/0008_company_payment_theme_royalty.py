from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_building_state_city_building_city'),
    ]

    operations = [
        migrations.AddField(model_name='company', name='online_payment',
            field=models.BooleanField(default=True, help_text='Allow online/UPI payment')),
        migrations.AddField(model_name='company', name='monthly_payment',
            field=models.BooleanField(default=False, help_text='Allow monthly billing')),
        migrations.AddField(model_name='company', name='logo',
            field=models.ImageField(blank=True, null=True, upload_to='company/logos/')),
        migrations.AddField(model_name='company', name='kiosk_theme_color',
            field=models.CharField(blank=True, default='#1e3a5f', max_length=20)),
        migrations.AddField(model_name='company', name='kiosk_logo',
            field=models.ImageField(blank=True, null=True, upload_to='company/kiosk_logos/')),
        migrations.AddField(model_name='company', name='kiosk_welcome_text',
            field=models.CharField(blank=True, default='Touch to order', max_length=160)),
        migrations.AddField(model_name='company', name='require_customer_approval',
            field=models.BooleanField(default=False)),
        migrations.AddField(model_name='company', name='royalty_enabled',
            field=models.BooleanField(default=False)),
        migrations.AddField(model_name='company', name='royalty_points_per_rupee',
            field=models.DecimalField(decimal_places=2, default=1, max_digits=5)),
        migrations.AddField(model_name='company', name='royalty_min_redeem',
            field=models.IntegerField(default=100)),
        migrations.AddField(model_name='company', name='royalty_max_redeem_pct',
            field=models.IntegerField(default=50)),
    ]
