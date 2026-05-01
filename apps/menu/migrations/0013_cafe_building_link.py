from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_building_state_city_building_city'),
        ('menu', '0012_expand_site_price_scope'),
    ]

    operations = [
        migrations.AddField(
            model_name='cafe',
            name='building',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cafes', to='core.building'),
        ),
    ]
