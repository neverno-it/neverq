from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_alter_company_kiosk_order_prefix_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='WebViewConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('name', models.CharField(help_text='e.g. "IBM Bhubaneswar Web View"', max_length=120)),
                ('slug', models.SlugField(blank=True, help_text='Auto-set. Used in web URL preview: /menu/?web=<slug>', max_length=120, unique=True)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='web_view_configs/')),
                ('theme_color', models.CharField(blank=True, help_text='Hex colour override e.g. #c62828', max_length=20)),
                ('welcome_title', models.CharField(blank=True, max_length=160)),
                ('welcome_subtitle', models.CharField(blank=True, max_length=255)),
                ('hero_image', models.ImageField(blank=True, null=True, upload_to='web_view_configs/hero/')),
                ('show_offerings', models.BooleanField(default=True)),
                ('show_categories', models.BooleanField(default=True)),
                ('card_style', models.CharField(choices=[('standard', 'Standard'), ('compact', 'Compact'), ('large', 'Large')], default='standard', help_text='Product card display style', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('building', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='web_view_configs', to='core.building')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='web_view_configs', to='core.company')),
            ],
            options={
                'verbose_name': 'Web View Configuration',
                'verbose_name_plural': 'Web View Configurations',
                'ordering': ['company__name', 'name'],
            },
        ),
    ]
