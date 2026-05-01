from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_webviewconfig'),
    ]

    operations = [
        migrations.CreateModel(
            name='DisplayBoardConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='e.g. "Main Cafeteria Display"', max_length=120)),
                ('slug', models.SlugField(blank=True, help_text='Auto-set. Used in preview URL: /display-board/?board=<slug>', max_length=120, unique=True)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='display_board_configs/')),
                ('footer_logo', models.ImageField(blank=True, null=True, upload_to='display_board_configs/footer/')),
                ('background_image', models.ImageField(blank=True, null=True, upload_to='display_board_configs/background/')),
                ('theme_color', models.CharField(blank=True, help_text='Primary accent colour e.g. #1e3a5f', max_length=20)),
                ('heading_text', models.CharField(blank=True, max_length=160)),
                ('side_text', models.CharField(blank=True, help_text='Large vertical/side text', max_length=120)),
                ('waiting_text', models.CharField(blank=True, help_text='Small waiting/status text', max_length=120)),
                ('promo_embed_url', models.URLField(blank=True, help_text='YouTube watch/share/embed URL')),
                ('footer_text', models.CharField(blank=True, max_length=255)),
                ('pending_label', models.CharField(default='Pending', max_length=40)),
                ('confirmed_label', models.CharField(default='Order Placed', max_length=40)),
                ('preparing_label', models.CharField(default='Preparing', max_length=40)),
                ('ready_label', models.CharField(default='Food Ready', max_length=40)),
                ('show_clock', models.BooleanField(default=True)),
                ('show_company_filter', models.BooleanField(default=True)),
                ('show_status_legend', models.BooleanField(default=True)),
                ('sound_enabled', models.BooleanField(default=True)),
                ('voice_enabled', models.BooleanField(default=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('building', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='display_board_configs', to='core.building')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='display_board_configs', to='core.company')),
            ],
            options={
                'verbose_name': 'Display Board Configuration',
                'verbose_name_plural': 'Display Board Configurations',
                'ordering': ['company__name', 'name'],
            },
        ),
    ]
