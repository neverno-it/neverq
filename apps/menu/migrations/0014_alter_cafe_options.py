from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0013_cafe_building_link'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='cafe',
            options={'ordering': ['name']},
        ),
    ]
