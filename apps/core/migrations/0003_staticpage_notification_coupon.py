from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_company_cod_payment_and_more'),
        ('accounts', '0002_alter_customer_cod_payment_alter_customer_created_at_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Coupon',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=50, unique=True)),
                ('description', models.TextField(blank=True)),
                ('discount_type', models.CharField(choices=[('flat', 'Flat Amount'), ('percent', 'Percentage')], default='flat', max_length=10)),
                ('discount_value', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('min_order', models.DecimalField(decimal_places=2, default=0, help_text='Minimum order amount to apply', max_digits=10)),
                ('max_discount', models.DecimalField(decimal_places=2, default=0, help_text='Cap for percentage discount (0 = no cap)', max_digits=10)),
                ('usage_limit', models.IntegerField(default=0, help_text='0 = unlimited')),
                ('used_count', models.IntegerField(default=0)),
                ('valid_from', models.DateTimeField(blank=True, null=True)),
                ('valid_to', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(blank=True, help_text='Leave blank for site-wide coupon', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='coupons', to='core.company')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='StaticPage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=100, unique=True)),
                ('title', models.CharField(max_length=255)),
                ('content', models.TextField(blank=True, help_text='HTML content')),
                ('is_active', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['title'],
            },
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notif_type', models.CharField(choices=[('order', 'Order Update'), ('system', 'System'), ('promo', 'Promotion')], default='order', max_length=20)),
                ('title', models.CharField(max_length=255)),
                ('message', models.TextField(blank=True)),
                ('link', models.CharField(blank=True, max_length=500)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='core.company')),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='accounts.customer')),
                ('staff_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='accounts.staffuser')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
