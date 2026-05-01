from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_building_state_city_building_city'),
        ('menu', '0011_counter_auto_print_on_ready_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='productcompanyprice',
            name='building',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='product_prices', to='core.building'),
        ),
        migrations.AddField(
            model_name='productcompanyprice',
            name='cafe',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='product_prices', to='menu.cafe'),
        ),
        migrations.AlterUniqueTogether(
            name='productcompanyprice',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='productcompanyprice',
            constraint=models.UniqueConstraint(condition=models.Q(('building__isnull', True), ('cafe__isnull', True)), fields=('product', 'company'), name='uniq_product_company_price_company_only'),
        ),
        migrations.AddConstraint(
            model_name='productcompanyprice',
            constraint=models.UniqueConstraint(condition=models.Q(('building__isnull', False), ('cafe__isnull', True)), fields=('product', 'building'), name='uniq_product_company_price_building'),
        ),
        migrations.AddConstraint(
            model_name='productcompanyprice',
            constraint=models.UniqueConstraint(condition=models.Q(('cafe__isnull', False)), fields=('product', 'cafe'), name='uniq_product_company_price_cafe'),
        ),
    ]
