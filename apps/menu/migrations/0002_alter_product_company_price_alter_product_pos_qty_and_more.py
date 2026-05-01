from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='company_price',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AlterField(
            model_name='product',
            name='pos_qty',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='schedule',
            name='display_day',
            field=models.CharField(max_length=20),
        ),
    ]
