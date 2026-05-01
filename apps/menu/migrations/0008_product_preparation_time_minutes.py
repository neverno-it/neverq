from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0007_alter_advertise_image_alter_mediaasset_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='preparation_time_minutes',
            field=models.PositiveIntegerField(default=10, help_text='Minutes after confirmation before this item should be marked ready.'),
        ),
    ]
