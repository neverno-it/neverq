from __future__ import annotations

import re
import shutil
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import transaction, IntegrityError
from django.utils import timezone
from PIL import Image, ImageOps

from .import_sql_data import Command as BaseImportCommand


class Command(BaseImportCommand):
    help = (
        "Import legacy NeverQ customers + catalog + banners + products + categories "
        "without importing old orders, POS history, reviews, or web cookies. "
        "Imported files are stored under MEDIA_ROOT/media_library/legacy_import/... , "
        "banner images are normalized to the portal banner ratio, and duplicate/spam "
        "customers are cleaned during import."
    )

    BANNER_WIDTH = 1240
    BANNER_HEIGHT = 660
    _SPAM_MARKERS = (
        "bit.ly",
        "http://",
        "https://",
        "tek t",
        "kazan",
        "rüyalar",
        "ruyalar",
        "85.000",
        "85000 tl",
    )

    def add_arguments(self, parser):
        parser.add_argument("sql_file", type=str, help="Path to the legacy NeverQ SQL dump")
        parser.add_argument(
            "--uploads-dir",
            required=True,
            help="Path to the old PHP assets/uploads folder containing legacy image files",
        )
        parser.add_argument("--flush", action="store_true", help="Flush database before import")
        parser.add_argument(
            "--with-staff",
            action="store_true",
            help="Also import old staff users (disabled by default)",
        )
        parser.add_argument(
            "--skip-media-copy",
            action="store_true",
            help="Import rows only and skip copying product/category/banner/customer images",
        )

    def handle(self, *args, **options):
        sql_file = options["sql_file"]
        uploads_dir = Path(options["uploads_dir"]).expanduser().resolve()

        try:
            with open(sql_file, "r", encoding="utf-8", errors="replace") as f:
                self.sql = f.read()
        except FileNotFoundError as exc:
            raise CommandError(f"SQL file not found: {sql_file}") from exc

        if not uploads_dir.exists() or not uploads_dir.is_dir():
            raise CommandError(f"Uploads directory not found or not a folder: {uploads_dir}")

        self.uploads_dir = uploads_dir
        self._table_cache = {}
        self._copied_media = {
            "products": 0,
            "categories": 0,
            "adverts": 0,
            "customers": 0,
            "banner_assets": 0,
            "missing": 0,
        }

        if options["flush"]:
            self.stdout.write(self.style.WARNING("Flushing…"))
            self._flush()

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== NeverQ Legacy Catalog Import (No Orders) ===\n"))
        self.stdout.write(f"SQL: {Path(sql_file).resolve()}")
        self.stdout.write(f"Uploads: {self.uploads_dir}\n")

        steps = [
            ("states", self._import_states),
            ("locations", self._import_locations),
            ("companies", self._import_companies),
            ("buildings", self._import_buildings),
            ("food_types", self._import_food_types),
        ]
        if options.get("with_staff"):
            steps.append(("staff", self._import_staff))
        steps.extend(
            [
                ("customers", self._import_customers_deduped),
                ("categories", self._import_categories),
                ("category_links", self._link_category_companies),
                ("schedules", self._import_schedules),
                ("cafes", self._import_cafes),
                ("adverts", self._import_adverts_approved),
                ("products", self._import_products),
            ]
        )

        for step_name, fn in steps:
            self._run_step(step_name, fn)

        if not options.get("skip_media_copy"):
            self._run_step("media_copy", self._copy_legacy_media)

        self.stdout.write(self.style.SUCCESS("\n✅ Catalog-only legacy import complete!\n"))
        self._summary()
        self.stdout.write(
            self.style.SUCCESS(
                "Orders were intentionally NOT imported. Customers, sites, buildings, banners, categories, products, and images are ready."
            )
        )

    # ------------------------------------------------------------------
    # Customer import: dedupe by (company, email) and skip legacy spam
    # ------------------------------------------------------------------

    def _delete_customer_ids_chunked(self, Customer, stale_ids, chunk_size: int = 400) -> int:
        """SQLite-safe delete for large pk__in lists."""
        deleted_total = 0
        for start in range(0, len(stale_ids), chunk_size):
            chunk = stale_ids[start:start + chunk_size]
            deleted, _ = Customer.objects.filter(pk__in=chunk).delete()
            deleted_total += deleted
        return deleted_total

    def _customer_rank(self, row):
        active = self._int(row.get("status"), 1) == 1
        not_deleted = self._int(row.get("flag"), 1) == 0
        has_password = bool((row.get("password") or "").strip())
        created = self._dt(row.get("create_date")) or timezone.now()
        return (
            1 if active else 0,
            1 if not_deleted else 0,
            1 if has_password else 0,
            created.timestamp(),
            self._int(row.get("id"), 0),
        )

    def _resolve_email(self, row, placeholder_counter: dict[str, int]) -> str:
        email = (row.get("email") or "").strip().lower()
        if email and "@" in email and " " not in email:
            return email
        placeholder_counter["count"] += 1
        return f"legacy-customer-{self._int(row.get('id'))}@neverq.local"

    def _normalize_phone(self, value: str | None) -> str:
        digits = re.sub(r"\D+", "", str(value or ""))
        return digits[-10:] if digits else ""

    def _build_phone_frequency(self, rows):
        frequency = {}
        for row in rows:
            company_id = self._int(row.get("company"))
            phone = self._normalize_phone(row.get("phone"))
            if not company_id or not phone:
                continue
            key = (company_id, phone)
            frequency[key] = frequency.get(key, 0) + 1
        return frequency

    def _looks_like_spam_customer(self, row, phone_frequency) -> bool:
        name = (row.get("name") or "").strip()
        email = (row.get("email") or "").strip().lower()
        phone = self._normalize_phone(row.get("phone"))
        company_id = self._int(row.get("company"))
        blob = f"{name} {email}".lower()

        if any(marker in blob for marker in self._SPAM_MARKERS):
            return True

        punctuation_noise = sum(1 for ch in name if ch in "?$%€£₺")
        if len(name) >= 50 and punctuation_noise >= 2:
            return True

        if phone and phone_frequency.get((company_id, phone), 0) >= 1000:
            if len(name) >= 30 or "?" in name or any(marker in blob for marker in ("gmail.com", "hotmail.com", "icloud.com", "outlook.com")):
                return True

        return False

    def _import_customers_deduped(self):
        from apps.accounts.models import Customer
        from apps.core.models import Company, Building

        rows = self._parse("tbl_login")
        company_ids = set(Company.objects.values_list("id", flat=True))
        building_ids = set(Building.objects.values_list("id", flat=True))
        phone_frequency = self._build_phone_frequency(rows)

        chosen = {}
        placeholder_counter = {"count": 0}
        spam_skipped = 0

        for row in rows:
            if self._looks_like_spam_customer(row, phone_frequency):
                spam_skipped += 1
                continue

            company_id = self._int(row.get("company"))
            if company_id not in company_ids:
                company_id = self._valid_company_or_placeholder(company_id)

            email = self._resolve_email(row, placeholder_counter)
            key = (company_id, email)
            current = chosen.get(key)
            candidate = dict(row)
            candidate["_resolved_company_id"] = company_id
            candidate["_resolved_email"] = email
            if current is None or self._customer_rank(candidate) > self._customer_rank(current):
                chosen[key] = candidate

        kept_ids = {self._int(row["id"]) for row in chosen.values()}
        all_legacy_ids = {self._int(row.get("id")) for row in rows if self._int(row.get("id"))}
        stale_ids = sorted(all_legacy_ids - kept_ids)
        cleaned_existing = 0
        if stale_ids:
            cleaned_existing = self._delete_customer_ids_chunked(Customer, stale_ids)

        imported = rescued = 0
        for row in chosen.values():
            legacy_id = self._int(row["id"])
            company_id = row["_resolved_company_id"]
            original_company_id = self._int(row.get("company"))
            if company_id != original_company_id:
                rescued += 1
            building_id = self._int(row.get("building"))
            _, created = Customer.objects.update_or_create(
                pk=legacy_id,
                defaults={
                    "company_id": company_id,
                    "building_id": building_id if building_id in building_ids else None,
                    "name": (row.get("name") or row["_resolved_email"].split("@")[0]).strip()[:250],
                    "phone": row.get("phone") or "",
                    "email": row["_resolved_email"],
                    "password_hash": row.get("password") or "",
                    "avatar": row.get("img") or "",
                    "verification_key": row.get("verification_key") or "",
                    "is_email_verified": self._normalize_bool(row.get("is_email_verified")),
                    "otp": self._int(row.get("otp")),
                    "token": row.get("token") or "",
                    "token_expires": self._normalize_bool(row.get("expires")),
                    "address": row.get("address") or "",
                    "cod_payment": self._int(row.get("cod_payment")) == 1,
                    "monthly_payment": self._int(row.get("monthly_payment")) == 1,
                    "is_active": self._int(row.get("status"), 1) == 1,
                    "is_deleted": self._int(row.get("flag"), 1) == 0,
                    "created_at": self._dt(row.get("create_date")) or timezone.now(),
                },
            )
            if created:
                imported += 1

        duplicates_skipped = max(0, len(rows) - spam_skipped - len(chosen))
        self._ok(
            f"Customers: {imported}/{len(chosen)} imported from {len(rows)} legacy rows "
            f"({duplicates_skipped} duplicate email+company rows skipped, "
            f"{spam_skipped} spam/junk rows skipped, {placeholder_counter['count']} placeholder emails, "
            f"{rescued} rescued, {cleaned_existing} old duplicate/junk rows removed)"
        )

    # ------------------------------------------------------------------
    # Adverts: mark approved so they actually show in the customer portal
    # ------------------------------------------------------------------

    def _import_adverts_approved(self):
        from apps.menu.models import Advertise
        from apps.core.models import Company

        rows = self._parse("tbl_advertise")
        company_ids = set(Company.objects.values_list("id", flat=True))
        n = rescued = 0
        for r in rows:
            company_id = self._int(r.get("cmid"))
            if company_id not in company_ids:
                company_id = self._valid_company_or_placeholder(company_id)
                rescued += 1
            _, created = Advertise.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={
                    "company_id": company_id,
                    "name": r.get("name") or "",
                    "position_order": self._int(r.get("position_order")),
                    "is_active": self._int(r.get("status"), 1) == 1,
                    "status": Advertise.STATUS_APPROVED,
                    "created_at": timezone.now(),
                },
            )
            if created:
                n += 1
        self._ok(f"Adverts: {n}/{len(rows)} ({rescued} rescued, imported as approved)")

    # ------------------------------------------------------------------
    # Media copy helpers
    # ------------------------------------------------------------------

    def _legacy_source(self, legacy_name: str) -> Path | None:
        if not legacy_name:
            return None
        legacy_name = Path(str(legacy_name)).name.strip()
        if not legacy_name:
            return None
        source = self.uploads_dir / legacy_name
        if source.exists() and source.is_file():
            return source
        self._copied_media["missing"] += 1
        self.stdout.write(self.style.WARNING(f"    Missing legacy media: {legacy_name}"))
        return None

    def _library_rel_path(self, source: Path, group: str) -> str:
        return f"media_library/legacy_import/{group}/{source.name}".replace("\\", "/")

    def _copy_into_media_library(self, source: Path, group: str) -> str:
        rel_path = self._library_rel_path(source, group)
        dest_path = Path(settings.MEDIA_ROOT) / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if not dest_path.exists():
            shutil.copy2(source, dest_path)
        return rel_path

    def _banner_rel_path(self, advert_id: int, source: Path, ext: str) -> str:
        safe_ext = ext if ext in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"
        return f"media_library/legacy_import/banner_assets/advert_{advert_id}{safe_ext}".replace("\\", "/")

    def _create_banner_derivative(self, advert_id: int, source: Path) -> str:
        target_size = (self.BANNER_WIDTH, self.BANNER_HEIGHT)
        lanczos = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)

        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img)
            has_alpha = "A" in img.getbands()
            work = img.convert("RGBA" if has_alpha else "RGB")
            fitted = ImageOps.fit(work, target_size, method=lanczos, centering=(0.5, 0.5))
            ext = ".png" if has_alpha else ".jpg"
            rel_path = self._banner_rel_path(advert_id, source, ext)
            dest_path = Path(settings.MEDIA_ROOT) / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if ext == ".jpg":
                fitted = fitted.convert("RGB")
                fitted.save(dest_path, quality=92, optimize=True)
            else:
                fitted.save(dest_path, optimize=True)
        return rel_path

    def _maybe_create_banner_asset(self, advert, rel_path: str):
        from apps.menu.models import MediaAsset

        asset_name = f"Legacy Banner #{advert.pk} - {advert.name or 'Imported Banner'}"
        try:
            MediaAsset.objects.update_or_create(
                company=advert.company,
                name=asset_name,
                defaults={
                    "image": rel_path,
                    "uploaded_by": None,
                },
            )
            self._copied_media["banner_assets"] += 1
        except (OSError, IOError, IntegrityError, ValidationError, AttributeError) as exc:
            self.stdout.write(
                self.style.WARNING(
                    f"    Banner image normalized for advert #{advert.pk}, but Media Library record was skipped: {exc}"
                )
            )

    @transaction.atomic
    def _copy_legacy_media(self):
        from apps.menu.models import Product, Category, Advertise
        from apps.accounts.models import Customer

        category_rows = {self._int(r["id"]): r for r in self._parse("tbl_category")}
        advert_rows = {self._int(r["id"]): r for r in self._parse("tbl_advertise")}
        product_rows = {self._int(r["id"]): r for r in self._parse("tbl_product")}
        customer_rows = {self._int(r["id"]): r for r in self._parse("tbl_login")}

        for category in Category.objects.all().only("id"):
            row = category_rows.get(category.id)
            source = self._legacy_source(row.get("img") if row else "")
            if not source:
                continue
            rel = self._copy_into_media_library(source, "categories")
            Category.objects.filter(pk=category.pk).update(image=rel)
            self._copied_media["categories"] += 1

        for product in Product.objects.all().only("id"):
            row = product_rows.get(product.id)
            source = self._legacy_source(row.get("img") if row else "")
            if not source:
                continue
            rel = self._copy_into_media_library(source, "products")
            Product.objects.filter(pk=product.pk).update(image=rel)
            self._copied_media["products"] += 1

        for advert in Advertise.objects.select_related("company").only("id", "company", "name"):
            row = advert_rows.get(advert.id)
            source = self._legacy_source(row.get("img") if row else "")
            if not source:
                continue
            rel = self._create_banner_derivative(advert.id, source)
            Advertise.objects.filter(pk=advert.pk).update(image=rel)
            self._maybe_create_banner_asset(advert, rel)
            self._copied_media["adverts"] += 1

        for customer in Customer.objects.all().only("id"):
            row = customer_rows.get(customer.id)
            legacy_name = (row or {}).get("img") or ""
            source = self._legacy_source(legacy_name)
            if not source:
                continue
            rel = self._copy_into_media_library(source, "customers")
            Customer.objects.filter(pk=customer.pk).update(avatar=rel)
            self._copied_media["customers"] += 1

        self._ok(
            "Media copied to media_library/legacy_import: "
            f"products={self._copied_media['products']}, "
            f"categories={self._copied_media['categories']}, "
            f"adverts={self._copied_media['adverts']}, "
            f"customers={self._copied_media['customers']}, "
            f"banner_assets={self._copied_media['banner_assets']}, "
            f"missing={self._copied_media['missing']}"
        )
