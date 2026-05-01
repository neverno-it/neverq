from __future__ import annotations

from pathlib import Path

from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from .import_legacy_catalog import Command as LegacyCatalogCommand


class Command(LegacyCatalogCommand):
    help = (
        "Import only the selected legacy NeverQ data into the new software: "
        "companies, customers, product images into Product Gallery, "
        "category images into Category Image Gallery, and banner images into "
        "the banner Media Library. This does NOT import orders, products, "
        "categories, POS history, reviews, or cookies."
    )

    def add_arguments(self, parser):
        parser.add_argument("sql_file", type=str, help="Path to the legacy NeverQ SQL dump")
        parser.add_argument(
            "--uploads-dir",
            default="",
            help="Path to the old uploads folder that contains the actual image files",
        )
        parser.add_argument("--flush", action="store_true", help="Flush database before import")
        parser.add_argument(
            "--skip-media-copy",
            action="store_true",
            help="Import companies and customers only; skip all gallery image import",
        )

    def handle(self, *args, **options):
        sql_file = options["sql_file"]
        uploads_dir_raw = (options.get("uploads_dir") or "").strip()
        skip_media_copy = bool(options.get("skip_media_copy"))

        try:
            with open(sql_file, "r", encoding="utf-8", errors="replace") as f:
                self.sql = f.read()
        except FileNotFoundError as exc:
            raise CommandError(f"SQL file not found: {sql_file}") from exc

        self._table_cache = {}
        self._copied_media = {
            "products": 0,
            "categories": 0,
            "adverts": 0,
            "customers": 0,
            "banner_assets": 0,
            "missing": 0,
        }

        self.uploads_dir = None
        if not skip_media_copy:
            if not uploads_dir_raw:
                raise CommandError(
                    "--uploads-dir is required unless you use --skip-media-copy. "
                    "The SQL dump contains image file names, but the actual gallery images "
                    "must be copied from the old uploads folder."
                )
            uploads_dir = Path(uploads_dir_raw).expanduser().resolve()
            if not uploads_dir.exists() or not uploads_dir.is_dir():
                raise CommandError(f"Uploads directory not found or not a folder: {uploads_dir}")
            self.uploads_dir = uploads_dir

        if options["flush"]:
            self.stdout.write(self.style.WARNING("Flushing…"))
            self._flush()

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== NeverQ Selected Legacy Import ===\n"))
        self.stdout.write(f"SQL: {Path(sql_file).resolve()}")
        if self.uploads_dir:
            self.stdout.write(f"Uploads: {self.uploads_dir}")
        else:
            self.stdout.write("Uploads: skipped")
        self.stdout.write("")

        steps = [
            ("companies", self._import_companies),
            ("customers", self._import_customers_deduped),
        ]
        if not skip_media_copy:
            steps.append(("gallery_images", self._copy_selected_gallery_media))

        for step_name, fn in steps:
            self._run_step(step_name, fn)

        self.stdout.write(self.style.SUCCESS("\n✅ Selected legacy import complete!\n"))
        self._summary_selected()

    def _resolve_single_company_id(self, raw_company_value):
        from apps.core.models import Company

        valid_ids = set(Company.objects.values_list("id", flat=True))
        company_ids = [company_id for company_id in self._int_list(raw_company_value) if company_id in valid_ids]
        if len(company_ids) == 1:
            return company_ids[0]
        return None

    def _product_gallery_rel_path(self, product_id: int, source: Path) -> str:
        return f"product_gallery/legacy_product_{product_id}_{source.name}".replace("\\", "/")

    def _category_gallery_rel_path(self, category_id: int, source: Path) -> str:
        return f"category_gallery/legacy_category_{category_id}_{source.name}".replace("\\", "/")

    @transaction.atomic
    def _copy_selected_gallery_media(self):
        from django.conf import settings
        from apps.core.models import Company
        from apps.menu.models import ProductGallery, CategoryGallery, MediaAsset

        valid_company_ids = set(Company.objects.values_list("id", flat=True))
        product_rows = {self._int(r.get("id")): r for r in self._parse("tbl_product")}
        category_rows = {self._int(r.get("id")): r for r in self._parse("tbl_category")}
        advert_rows = {self._int(r.get("id")): r for r in self._parse("tbl_advertise")}

        for legacy_id, row in product_rows.items():
            source = self._legacy_source((row or {}).get("img") or "")
            if not source:
                continue
            rel_path = self._product_gallery_rel_path(legacy_id, source)
            dest_path = Path(settings.MEDIA_ROOT) / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if not dest_path.exists():
                dest_path.write_bytes(source.read_bytes())

            company_id = self._int(row.get("company"))
            if company_id not in valid_company_ids:
                company_id = None

            ProductGallery.objects.update_or_create(
                image=rel_path,
                defaults={
                    "company_id": company_id,
                    "name": (row.get("pname") or source.stem or f"Legacy Product {legacy_id}")[:255],
                    "uploaded_by": None,
                },
            )
            self._copied_media["products"] += 1

        for legacy_id, row in category_rows.items():
            source = self._legacy_source((row or {}).get("img") or "")
            if not source:
                continue
            rel_path = self._category_gallery_rel_path(legacy_id, source)
            dest_path = Path(settings.MEDIA_ROOT) / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if not dest_path.exists():
                dest_path.write_bytes(source.read_bytes())

            company_id = self._resolve_single_company_id(row.get("cmid"))

            CategoryGallery.objects.update_or_create(
                image=rel_path,
                defaults={
                    "company_id": company_id,
                    "name": (row.get("name") or source.stem or f"Legacy Category {legacy_id}")[:255],
                    "is_active": self._int(row.get("status"), 1) == 1,
                },
            )
            self._copied_media["categories"] += 1

        for legacy_id, row in advert_rows.items():
            source = self._legacy_source((row or {}).get("img") or "")
            if not source:
                continue
            rel_path = self._create_banner_derivative(legacy_id, source)

            company_id = self._int(row.get("cmid"))
            if company_id not in valid_company_ids:
                company_id = self._valid_company_or_placeholder(company_id)

            MediaAsset.objects.update_or_create(
                image=rel_path,
                defaults={
                    "company_id": company_id,
                    "name": (row.get("name") or f"Legacy Banner {legacy_id}")[:255],
                    "uploaded_by": None,
                },
            )
            self._copied_media["adverts"] += 1
            self._copied_media["banner_assets"] += 1

        self._ok(
            "Gallery images imported: "
            f"product_gallery={self._copied_media['products']}, "
            f"category_gallery={self._copied_media['categories']}, "
            f"banner_media_library={self._copied_media['adverts']}, "
            f"missing={self._copied_media['missing']}"
        )

    def _summary_selected(self):
        from apps.core.models import Company
        from apps.accounts.models import Customer
        from apps.menu.models import ProductGallery, CategoryGallery, MediaAsset

        self.stdout.write(self.style.MIGRATE_HEADING("Summary"))
        self.stdout.write(f"  Companies:          {Company.objects.count()}")
        self.stdout.write(f"  Customers:          {Customer.objects.count()}")
        self.stdout.write(f"  Product Gallery:    {ProductGallery.objects.count()}")
        self.stdout.write(f"  Category Gallery:   {CategoryGallery.objects.count()}")
        self.stdout.write(f"  Banner Gallery:     {MediaAsset.objects.count()}  (shown in UI as Media Library)")
        self.stdout.write(
            "  Missing images:     "
            f"{self._copied_media['missing']}"
        )
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Done. Only companies, customers, and the selected gallery image sets were imported."
            )
        )
