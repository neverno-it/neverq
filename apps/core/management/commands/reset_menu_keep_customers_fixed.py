from pathlib import Path
import shutil
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Delete products/menu data while keeping customers, passwords, banners, and product gallery. "
        "Optionally import image files into Product Gallery."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show counts only. Do not modify data.')
        parser.add_argument('--full-menu-reset', action='store_true', help='Also delete categories, offerings, offers, and offer usages.')
        parser.add_argument('--wipe-pos-products', action='store_true', help='Also delete POSProduct records.')
        parser.add_argument('--import-gallery-dir', type=str, default='', help='Folder path containing product image files to import into Product Gallery.')
        parser.add_argument('--company-id', type=int, default=None, help='Optional company id for imported Product Gallery images.')

    def handle(self, *args, **options):
        from apps.menu.models import (
            Product,
            Category,
            Offering,
            Offer,
            OfferUsage,
            ProductCounter,
            ProductCompanyPrice,
            StockLedger,
            ProductGallery,
        )
        from apps.pos.models import POSProduct
        from apps.core.models import Company

        dry_run = options['dry_run']
        full_menu_reset = options['full_menu_reset']
        wipe_pos_products = options['wipe_pos_products']
        import_gallery_dir = (options.get('import_gallery_dir') or '').strip()
        company_id = options.get('company_id')

        company = None
        if company_id is not None:
            try:
                company = Company.objects.get(pk=company_id)
            except Company.DoesNotExist as exc:
                raise CommandError(f'Company id {company_id} does not exist.') from exc

        counts = {
            'products': Product.objects.count(),
            'product_counter_mappings': ProductCounter.objects.count(),
            'product_company_prices': ProductCompanyPrice.objects.count(),
            'stock_ledger': StockLedger.objects.count(),
            'offers': Offer.objects.count(),
            'offer_usages': OfferUsage.objects.count(),
            'offerings': Offering.objects.count(),
            'categories': Category.objects.count(),
            'pos_products': POSProduct.objects.count(),
            'product_gallery': ProductGallery.objects.count(),
        }

        self.stdout.write(self.style.WARNING('Reset summary'))
        for key, value in counts.items():
            self.stdout.write(f'  - {key}: {value}')

        if import_gallery_dir:
            src = Path(import_gallery_dir)
            if not src.exists() or not src.is_dir():
                raise CommandError(f'Gallery import folder not found: {src}')
            image_files = [
                p for p in src.iterdir()
                if p.is_file() and p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
            ]
            self.stdout.write(f'  - gallery files found for import: {len(image_files)}')
        else:
            image_files = []

        if dry_run:
            self.stdout.write(self.style.SUCCESS('Dry run only. No changes made.'))
            return

        with transaction.atomic():
            # Explicit cleanup of dependent product tables first
            StockLedger.objects.all().delete()
            ProductCompanyPrice.objects.all().delete()
            ProductCounter.objects.all().delete()

            # Offers can point to products; clear them before product delete when doing a full menu reset.
            if full_menu_reset:
                OfferUsage.objects.all().delete()
                Offer.objects.all().delete()

            # Product delete will set historical OrderItem.product to NULL because that FK is SET_NULL.
            deleted_products, _ = Product.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'Deleted product rows via collector: {deleted_products}'))

            if wipe_pos_products:
                deleted_pos, _ = POSProduct.objects.all().delete()
                self.stdout.write(self.style.SUCCESS(f'Deleted POS product rows via collector: {deleted_pos}'))

            if full_menu_reset:
                deleted_offerings, _ = Offering.objects.all().delete()
                deleted_categories, _ = Category.objects.all().delete()
                self.stdout.write(self.style.SUCCESS(f'Deleted offering rows via collector: {deleted_offerings}'))
                self.stdout.write(self.style.SUCCESS(f'Deleted category rows via collector: {deleted_categories}'))

            imported = 0
            skipped = 0
            if image_files:
                media_root = Path(__import__('django.conf').conf.settings.MEDIA_ROOT)
                target_dir = media_root / 'product_gallery'
                target_dir.mkdir(parents=True, exist_ok=True)

                for path in image_files:
                    target_name = path.name
                    dest = target_dir / target_name
                    if dest.exists():
                        stem = dest.stem
                        suffix = dest.suffix
                        n = 1
                        while True:
                            candidate = target_dir / f'{stem}_{n}{suffix}'
                            if not candidate.exists():
                                dest = candidate
                                target_name = candidate.name
                                break
                            n += 1
                    shutil.copy2(path, dest)
                    ProductGallery.objects.create(
                        company=company,
                        name=path.stem,
                        image=f'product_gallery/{target_name}',
                    )
                    imported += 1
                self.stdout.write(self.style.SUCCESS(f'Imported {imported} images into Product Gallery.'))
            else:
                skipped = 0

        self.stdout.write(self.style.SUCCESS('Done. Customers, passwords, banners, and existing product gallery were kept intact.'))
