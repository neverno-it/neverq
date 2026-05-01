from django.db import migrations, models
import django.db.models.deletion
import apps.menu.models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_customer_wallet_approval'),
        ('menu', '0015_product_is_kiosk_active'),
        ('core', '0008_company_payment_theme_royalty'),
    ]

    operations = [
        # Category: day scheduling
        migrations.AddField(model_name='category', name='open_days',
            field=models.JSONField(blank=True, default=list,
                help_text='Days this category is shown e.g. ["Mon","Tue"]. Empty = every day.')),
        # Offering: day scheduling
        migrations.AddField(model_name='offering', name='open_days',
            field=models.JSONField(blank=True, default=list,
                help_text='Days offering is available e.g. ["Mon","Tue"]. Empty = every day.')),
        # ProductGallery
        migrations.CreateModel(
            name='ProductGallery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('image', models.ImageField(upload_to=apps.menu.models.product_gallery_image_path)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='product_gallery', to='core.company')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='accounts.staffuser')),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Product Gallery Image',
                     'verbose_name_plural': 'Product Gallery'},
        ),
    ]
