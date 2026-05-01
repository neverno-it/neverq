from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_company_royalty_leaderboard'),
    ]

    operations = [
        migrations.CreateModel(
            name='KioskConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120)),
                ('slug', models.SlugField(blank=True, unique=True)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='kiosk_configs/')),
                ('theme_color', models.CharField(blank=True, max_length=20)),
                ('welcome_title', models.CharField(blank=True, max_length=160)),
                ('welcome_subtitle', models.CharField(blank=True, max_length=255)),
                ('hero_image', models.ImageField(blank=True, null=True, upload_to='kiosk_configs/hero/')),
                ('show_offerings', models.BooleanField(default=True)),
                ('show_categories', models.BooleanField(default=True)),
                ('card_style', models.CharField(
                    choices=[('standard','Standard'),('compact','Compact'),('large','Large')],
                    default='standard', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='kiosk_configs', to='core.company')),
                ('building', models.ForeignKey(blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='kiosk_configs', to='core.building')),
            ],
            options={'ordering': ['company__name', 'name'],
                     'verbose_name': 'Kiosk Configuration',
                     'verbose_name_plural': 'Kiosk Configurations'},
        ),
    ]
