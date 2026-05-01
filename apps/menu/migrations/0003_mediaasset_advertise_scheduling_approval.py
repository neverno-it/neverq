import apps.menu.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0002_alter_product_company_price_alter_product_pos_qty_and_more'),
        ('core', '0002_alter_company_cod_payment_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1. MediaAsset table ───────────────────────────────────
        migrations.CreateModel(
            name='MediaAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255,
                                          help_text='Friendly label for this image')),
                ('image', models.ImageField(upload_to=apps.menu.models.media_asset_path)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='media_assets',
                    to='core.company',
                )),
                ('uploaded_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='uploaded_assets',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'Media Asset'},
        ),

        # ── 2. New fields on Advertise ────────────────────────────
        migrations.AddField(
            model_name='advertise',
            name='start_date',
            field=models.DateField(blank=True, null=True,
                                   help_text='Run from this date (inclusive)'),
        ),
        migrations.AddField(
            model_name='advertise',
            name='end_date',
            field=models.DateField(blank=True, null=True,
                                   help_text='Run until this date (inclusive)'),
        ),
        migrations.AddField(
            model_name='advertise',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending',  'Pending Approval'),
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='advertise',
            name='review_note',
            field=models.TextField(blank=True,
                                   help_text='Admin note on approval/rejection'),
        ),
        migrations.AddField(
            model_name='advertise',
            name='created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='advertise',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_adverts',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='advertise',
            name='reviewed_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='reviewed_adverts',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='advertise',
            name='media_asset',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='adverts',
                to='menu.mediaasset',
                help_text='Pick from media library instead of uploading',
            ),
        ),

        # ── 3. Bulk-approve existing ads (created before approval existed) ──
        migrations.RunSQL(
            sql="UPDATE menu_advertise SET status = 'approved' WHERE status = 'pending' OR status = '';",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
