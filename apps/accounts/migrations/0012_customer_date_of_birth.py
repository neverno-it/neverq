from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_alter_customer_is_approved_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True),
        ),
    ]
