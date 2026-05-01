from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='orderitem',
            options={'ordering': ['id']},
        ),
        migrations.AlterModelOptions(
            name='orderstatus',
            options={'ordering': ['created_at']},
        ),
        migrations.AlterField(
            model_name='orderitem',
            name='created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='orderstatus',
            name='created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
