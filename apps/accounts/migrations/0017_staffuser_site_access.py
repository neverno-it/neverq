from django.db import migrations, models


def copy_primary_company_to_site_access(apps, schema_editor):
    StaffUser = apps.get_model('accounts', 'StaffUser')
    through = StaffUser.site_access.through
    rows = []
    existing = set(
        through.objects.values_list('staffuser_id', 'company_id')
    )
    for user in StaffUser.objects.exclude(company_id__isnull=True).only('id', 'company_id'):
        key = (user.id, user.company_id)
        if key not in existing:
            rows.append(through(staffuser_id=user.id, company_id=user.company_id))
    if rows:
        through.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_granular_permissions'),
    ]

    operations = [
        migrations.AlterField(
            model_name='staffuser',
            name='role',
            field=models.CharField(choices=[('superadmin', 'Super Admin'), ('admin', 'Operation Manager'), ('cafeman', 'Chef / Cafe Manager'), ('pos', 'Cashier / POS'), ('reports', 'Reports Viewer')], default='admin', max_length=20),
        ),
        migrations.AddField(
            model_name='staffuser',
            name='site_access',
            field=models.ManyToManyField(blank=True, help_text='Sites this staff member can control. Granular permissions decide what they can do inside those sites.', related_name='site_staff', to='core.company'),
        ),
        migrations.RunPython(copy_primary_company_to_site_access, migrations.RunPython.noop),
    ]
