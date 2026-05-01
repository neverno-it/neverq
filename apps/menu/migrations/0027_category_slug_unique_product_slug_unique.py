"""
Migration 0027 — Enforce slug uniqueness (self-healing).

Automatically deduplicates any existing slug collisions before
adding the constraint, so this applies cleanly on any existing DB.

Category slugs are made globally unique by appending -2, -3, etc.
Product slugs are made unique per company by the same method.
"""
from django.db import migrations, models


def deduplicate_category_slugs(apps, schema_editor):
    """Fix duplicate category slugs before adding the unique constraint."""
    Category = apps.get_model('menu', 'Category')
    from collections import defaultdict

    # Group by slug, ordered by pk so the first one keeps the original
    seen = defaultdict(list)
    for cat in Category.objects.order_by('pk').values('id', 'slug'):
        seen[cat['slug']].append(cat['id'])

    for slug, ids in seen.items():
        if len(ids) <= 1:
            continue
        # Keep ids[0] as-is; rename ids[1], ids[2], ... to slug-2, slug-3, ...
        for n, cat_id in enumerate(ids[1:], start=2):
            new_slug = f'{slug}-{n}'
            # Make sure the new slug itself isn't taken
            while Category.objects.filter(slug=new_slug).exclude(id=cat_id).exists():
                n += 1
                new_slug = f'{slug}-{n}'
            Category.objects.filter(id=cat_id).update(slug=new_slug)


def deduplicate_product_slugs(apps, schema_editor):
    """Fix duplicate product slugs (scoped per company) before adding the constraint."""
    Product = apps.get_model('menu', 'Product')
    from collections import defaultdict

    seen = defaultdict(list)
    for p in Product.objects.filter(company__isnull=False).order_by('pk').values('id', 'company_id', 'slug'):
        seen[(p['company_id'], p['slug'])].append(p['id'])

    for (company_id, slug), ids in seen.items():
        if len(ids) <= 1:
            continue
        for n, prod_id in enumerate(ids[1:], start=2):
            new_slug = f'{slug}-{n}'
            while Product.objects.filter(company_id=company_id, slug=new_slug).exclude(id=prod_id).exists():
                n += 1
                new_slug = f'{slug}-{n}'
            Product.objects.filter(id=prod_id).update(slug=new_slug)


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0026_alter_offer_value'),
    ]

    operations = [
        # Step 1: Fix the data first
        migrations.RunPython(
            deduplicate_category_slugs,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            deduplicate_product_slugs,
            reverse_code=migrations.RunPython.noop,
        ),

        # Step 2: Now safe to add the constraints
        migrations.AddConstraint(
            model_name='category',
            constraint=models.UniqueConstraint(
                fields=['slug'],
                name='uniq_category_slug',
            ),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.UniqueConstraint(
                fields=['company', 'slug'],
                condition=models.Q(company__isnull=False),
                name='uniq_product_company_slug',
            ),
        ),
    ]
