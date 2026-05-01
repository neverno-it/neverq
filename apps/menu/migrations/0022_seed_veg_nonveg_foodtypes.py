"""
Migration 0022 — Seed mandatory FoodType records + clean up non-dietary ones.

Ensures 'Veg' and 'Non-Veg' FoodType rows always exist.
Also deactivates any FoodType records whose names don't contain 'veg'
(e.g. accidentally-created records like "Home Delivery", "Office Cafeteria")
so they no longer appear in the product form or affect filter logic.
Uses get_or_create so it is safe to run on databases that already have
the correct rows.
"""
from django.db import migrations


def seed_and_clean_food_types(apps, schema_editor):
    FoodType = apps.get_model('menu', 'FoodType')

    # 1. Ensure Veg and Non-Veg exist
    for name in ('Veg', 'Non-Veg'):
        FoodType.objects.get_or_create(name=name, defaults={'is_active': True})

    # 2. Deactivate any record whose name does not contain 'veg' (case-insensitive).
    #    These are non-dietary records that should never appear in the food-type selector.
    FoodType.objects.exclude(name__icontains='veg').update(is_active=False)


def reverse_seed(apps, schema_editor):
    # No-op: we never delete or re-activate data in a reverse migration.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0021_product_calories'),
    ]

    operations = [
        migrations.RunPython(seed_and_clean_food_types, reverse_code=reverse_seed),
    ]
