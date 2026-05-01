from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0005_companysettlement'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='auto_ready_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
