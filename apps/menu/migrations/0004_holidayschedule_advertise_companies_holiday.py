import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0003_mediaasset_advertise_scheduling_approval'),
        ('core', '0002_alter_company_cod_payment_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ── 1. HolidaySchedule table ─────────────────────────────
        migrations.CreateModel(
            name='HolidaySchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('name',        models.CharField(max_length=255,
                                                  help_text='e.g. Independence Day')),
                ('month',       models.IntegerField(help_text='Month number 1–12')),
                ('day',         models.IntegerField(help_text='Day number 1–31')),
                ('description', models.TextField(blank=True)),
                ('is_active',   models.BooleanField(default=True)),
                ('created_at',  models.DateTimeField(auto_now_add=True)),
                ('created_by',  models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_holidays',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Holiday Schedule',
                'ordering': ['month', 'day'],
                'unique_together': {('month', 'day')},
            },
        ),

        # ── 2. Advertise.companies (M2M — which sites to run on) ─
        migrations.AddField(
            model_name='advertise',
            name='companies',
            field=models.ManyToManyField(
                blank=True,
                related_name='targeted_adverts',
                to='core.company',
                help_text='Select which sites to show this banner on.',
            ),
        ),

        # ── 3. Advertise.holiday_schedules M2M ───────────────────
        migrations.AddField(
            model_name='advertise',
            name='holiday_schedules',
            field=models.ManyToManyField(
                blank=True,
                related_name='adverts',
                to='menu.holidayschedule',
                help_text='Also run this ad automatically on selected national holidays every year.',
            ),
        ),

        # ── 4. MediaAsset.companies (shared-with M2M) ─────────────
        migrations.AddField(
            model_name='mediaasset',
            name='companies',
            field=models.ManyToManyField(
                blank=True,
                related_name='shared_assets',
                to='core.company',
                help_text='Additional sites that can use this image.',
            ),
        ),
    ]
