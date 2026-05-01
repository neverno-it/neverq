from django.db import migrations, models
import django.db.models.deletion
import apps.menu.models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_company_order_prefixes'),
        ('menu', '0031_remove_offerusage_uniq_offer_customer_used_on_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='offering',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='offerings/'),
        ),
        migrations.CreateModel(
            name='CategoryGallery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('image', models.ImageField(upload_to=apps.menu.models.category_gallery_image_path)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(blank=True, help_text='Leave blank for a global/shared image', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='category_gallery', to='core.company')),
            ],
            options={
                'verbose_name': 'Category Gallery Image',
                'verbose_name_plural': 'Category Image Gallery',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='OfferingGallery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('image', models.ImageField(upload_to=apps.menu.models.offering_gallery_image_path)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(blank=True, help_text='Leave blank for a global/shared image', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='offering_gallery', to='core.company')),
            ],
            options={
                'verbose_name': 'Offering Gallery Image',
                'verbose_name_plural': 'Offering Image Gallery',
                'ordering': ['-created_at'],
            },
        ),
    ]
