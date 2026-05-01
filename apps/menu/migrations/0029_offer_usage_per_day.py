from django.db import migrations, models
import django.utils.timezone


def backfill_used_on(apps, schema_editor):
    OfferUsage = apps.get_model('menu', 'OfferUsage')
    for usage in OfferUsage.objects.all().only('pk', 'used_at', 'used_on'):
        if getattr(usage, 'used_on', None):
            continue
        used_at = getattr(usage, 'used_at', None)
        usage.used_on = django.utils.timezone.localdate(used_at) if used_at else django.utils.timezone.localdate()
        usage.save(update_fields=['used_on'])


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0028_category_preparation_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='offerusage',
            name='used_on',
            field=models.DateField(db_index=True, default=django.utils.timezone.localdate),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_used_on, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='offerusage',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='offerusage',
            constraint=models.UniqueConstraint(fields=('offer', 'customer', 'used_on'), name='uniq_offer_customer_used_on'),
        ),
    ]
