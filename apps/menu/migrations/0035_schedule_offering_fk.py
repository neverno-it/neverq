from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0034_product_featured_in_web'),
    ]

    operations = [
        migrations.AddField(
            model_name='schedule',
            name='offering',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='schedules',
                to='menu.offering',
            ),
        ),
    ]
