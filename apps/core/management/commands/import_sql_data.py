"""
Import data from the legacy NeverQ PHP/MySQL SQL dump into this Django project.

Notes:
- Optimized to avoid heavy per-row ORM lookups during large imports.
- Supports resume with --start-at.
- Preserves legacy primary keys where possible.
- Handles duplicate legacy web order numbers by suffixing the legacy row id.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = "Import all data from the original PHP SQL dump"

    def add_arguments(self, parser):
        parser.add_argument("sql_file", type=str)
        parser.add_argument("--flush", action="store_true")
        parser.add_argument("--start-at", default="", help="Resume from a step such as orders or pos_orders")

    def handle(self, *args, **options):
        sql_file = options["sql_file"]
        try:
            with open(sql_file, "r", encoding="utf-8", errors="replace") as f:
                self.sql = f.read()
        except FileNotFoundError as exc:
            raise CommandError(f"File not found: {sql_file}") from exc

        self._table_cache = {}

        if options["flush"]:
            self.stdout.write(self.style.WARNING("Flushing…"))
            self._flush()

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== NeverQ SQL Import ===\n"))

        steps = [
            ("states", self._import_states),
            ("locations", self._import_locations),
            ("companies", self._import_companies),
            ("buildings", self._import_buildings),
            ("food_types", self._import_food_types),
            ("staff", self._import_staff),
            ("customers", self._import_customers),
            ("categories", self._import_categories),
            ("category_links", self._link_category_companies),
            ("schedules", self._import_schedules),
            ("cafes", self._import_cafes),
            ("adverts", self._import_adverts),
            ("products", self._import_products),
            ("orders", self._import_orders),
            ("orphan_orders", self._backfill_orphan_orders),
            ("order_items", self._import_order_items),
            ("order_statuses", self._import_order_statuses),
            ("pos_products", self._import_pos_products),
            ("pos_orders", self._import_pos_orders),
            ("pos_items", self._import_pos_items),
            ("reviews", self._import_reviews),
            ("webcookies", self._import_webcookies),
        ]

        start_at = (options.get("start_at") or "").strip().lower()
        started = not start_at
        matched = False

        for step_name, fn in steps:
            if not started and step_name != start_at:
                continue
            started = True
            matched = True
            self._run_step(step_name, fn)

        if start_at and not matched:
            raise CommandError(f"Unknown step: {start_at}")

        self.stdout.write(self.style.SUCCESS("\n✅  Import complete!\n"))
        self._summary()

    # ── SQL PARSER ────────────────────────────────────────────────

    def _parse(self, table):
        if table in self._table_cache:
            return self._table_cache[table]

        pattern = rf"INSERT INTO `{re.escape(table)}`\s*\(([^)]+)\)\s*VALUES\s*([\s\S]+?);"
        rows = []
        for cols_str, vals_str in re.findall(pattern, self.sql):
            cols = [c.strip().strip("`") for c in cols_str.split(",")]
            for row in self._parse_values(vals_str):
                if len(row) == len(cols):
                    rows.append(dict(zip(cols, row)))
        self._table_cache[table] = rows
        return rows

    def _parse_values(self, s):
        rows, i = [], 0
        s = s.strip()
        while i < len(s):
            if s[i] == "(":
                row, i = self._parse_row(s, i + 1)
                rows.append(row)
            else:
                i += 1
        return rows

    def _parse_row(self, s, i):
        vals = []
        while i < len(s):
            while i < len(s) and s[i] in " \t\n\r":
                i += 1
            if i >= len(s):
                break
            if s[i] == ")":
                return vals, i + 1
            if s[i] == ",":
                i += 1
                continue
            if s[i] == "'":
                v, i = self._parse_str(s, i + 1)
                vals.append(v)
            elif s[i : i + 4].upper() == "NULL":
                vals.append(None)
                i += 4
            else:
                e = i
                while e < len(s) and s[e] not in ",)":
                    e += 1
                vals.append(s[i:e].strip() or None)
                i = e
        return vals, i

    def _parse_str(self, s, i):
        r = []
        while i < len(s):
            c = s[i]
            if c == "\\":
                i += 1
                if i < len(s):
                    r.append({"n": "\n", "r": "\r", "t": "\t", "'": "'", '"': '"', "\\": "\\"}.get(s[i], s[i]))
                    i += 1
            elif c == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    r.append("'")
                    i += 2
                else:
                    return "".join(r), i + 1
            else:
                r.append(c)
                i += 1
        return "".join(r), i

    # ── HELPERS ───────────────────────────────────────────────────

    def _run_step(self, step_name, fn):
        self.stdout.write(self.style.MIGRATE_LABEL(f"\n→ {step_name}"))
        started = timezone.now()
        with transaction.atomic():
            fn()
        secs = (timezone.now() - started).total_seconds()
        self.stdout.write(f"  · done in {secs:.1f}s")

    def _ok(self, msg):
        self.stdout.write(self.style.SUCCESS(f"  ✓ {msg}"))

    def _dec(self, v, d="0"):
        try:
            return Decimal(str(v or d).strip() or d)
        except InvalidOperation:
            return Decimal(d)

    def _int(self, v, d=0):
        try:
            return int(v or d)
        except (ValueError, TypeError):
            return d

    def _dt(self, v):
        if not v:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(str(v), fmt)
                return timezone.make_aware(dt, timezone.get_current_timezone()) if timezone.is_naive(dt) else dt
            except (ValueError, OverflowError, OSError):
                pass
        return None

    def _t(self, v):
        if not v:
            return None
        try:
            p = str(v).split(":")
            return time(int(p[0]), int(p[1]), int(p[2]) if len(p) > 2 else 0)
        except (ValueError, IndexError, TypeError):
            return None

    def _int_list(self, v):
        return [int(x.strip()) for x in str(v or "").split(",") if x.strip().isdigit()]

    def _normalize_bool(self, v, true_values=None):
        if true_values is None:
            true_values = {"1", "yes", "true", "y"}
        return str(v or "").strip().lower() in true_values

    def _unique_token(self, desired, used, fallback_prefix, legacy_id):
        token = (desired or "").strip() or f"{fallback_prefix}-{legacy_id}"
        if token not in used:
            used.add(token)
            return token
        token2 = f"{token}-{legacy_id}"
        if token2 not in used:
            used.add(token2)
            return token2
        i = 2
        while True:
            token3 = f"{token}-{legacy_id}-{i}"
            if token3 not in used:
                used.add(token3)
                return token3
            i += 1

    def _ensure_legacy_company(self):
        from apps.core.models import Company

        company, _ = Company.objects.update_or_create(
            pk=1,
            defaults={
                'name': 'Legacy Unassigned Company',
                'company_address': 'Recovered placeholder for orphaned legacy records',
                'phone': '',
                'bill_company': 2,
                'company_meal_amount': 0,
                'cod_payment': False,
                'store_status': False,
                'store_order_enabled': False,
                'video_link': '',
                'is_active': False,
                'is_deleted': False,
            },
        )
        return company

    def _ensure_legacy_customer(self, company_id=1):
        from apps.accounts.models import Customer

        self._ensure_legacy_company()
        customer, _ = Customer.objects.update_or_create(
            pk=1,
            defaults={
                'company_id': company_id or 1,
                'building_id': None,
                'name': 'Legacy Unknown Customer',
                'phone': '',
                'email': 'legacy-orphan@neverq.local',
                'password_hash': '',
                'avatar': '',
                'verification_key': '',
                'is_email_verified': False,
                'otp': 0,
                'token': '',
                'token_expires': False,
                'address': '',
                'cod_payment': False,
                'monthly_payment': False,
                'is_active': False,
                'is_deleted': False,
                'created_at': timezone.now(),
            },
        )
        return customer

    def _valid_company_or_placeholder(self, company_id):
        from apps.core.models import Company

        company_id = self._int(company_id)
        if company_id and Company.objects.filter(pk=company_id).exists():
            return company_id
        self._ensure_legacy_company()
        return 1

    def _backfill_orphan_orders(self):
        from apps.orders.models import Order, OrderStatusChoices, PaymentModeChoices

        existing_ids = set(Order.objects.values_list('id', flat=True))
        item_rows = self._parse('tbl_orderitems')
        status_rows = self._parse('tbl_order_status')

        orphan_info = {}
        for r in item_rows:
            oid = self._int(r.get('oid'))
            if not oid or oid in existing_ids:
                continue
            info = orphan_info.setdefault(oid, {'company_id': 1, 'created_at': None, 'status': OrderStatusChoices.CANCELLED})
            info['company_id'] = self._valid_company_or_placeholder(r.get('cmid'))
            dt = self._dt(r.get('create_date'))
            if dt and (info['created_at'] is None or dt < info['created_at']):
                info['created_at'] = dt

        status_map = {0: 6, 1: 1, 2: 2, 3: 3, 4: 5}
        for r in status_rows:
            oid = self._int(r.get('oid'))
            if not oid or oid in existing_ids:
                continue
            info = orphan_info.setdefault(oid, {'company_id': 1, 'created_at': None, 'status': OrderStatusChoices.CANCELLED})
            dt = self._dt(r.get('create_date'))
            if dt and (info['created_at'] is None or dt < info['created_at']):
                info['created_at'] = dt
            mapped = status_map.get(self._int(r.get('status'), 0), OrderStatusChoices.CANCELLED)
            if mapped and mapped > info['status']:
                info['status'] = mapped

        if not orphan_info:
            self._ok('Orphan orders backfilled: 0')
            return

        customer = self._ensure_legacy_customer(1)
        used_numbers = set(Order.objects.values_list('order_number', flat=True))
        batch = []
        for oid, info in sorted(orphan_info.items()):
            batch.append(Order(
                id=oid,
                company_id=info['company_id'],
                customer_id=customer.id,
                cafe_id=None,
                coupon_id=0,
                coupon_discount=Decimal('0'),
                subtotal=Decimal('0'),
                shipping_cost=Decimal('0'),
                bill_to_company=Decimal('0'),
                my_pay=Decimal('0'),
                total_amount=Decimal('0'),
                order_number=self._unique_token(f'ORPH-{oid}', used_numbers, 'ORPH', oid),
                payment_mode=PaymentModeChoices.COMPANY,
                payment_status='legacy-orphan',
                transaction_id='',
                order_type=0,
                order_status=info['status'],
                review_given=False,
                session_foodtype='legacy-orphan',
                session_item_date='',
                created_at=info['created_at'] or timezone.now(),
                scheduled_date=info['created_at'],
                is_deleted=False,
            ))
        Order.objects.bulk_create(batch, ignore_conflicts=True, batch_size=500)
        self._ok(f'Orphan orders backfilled: {len(batch)}')

    # ── FLUSH ─────────────────────────────────────────────────────

    def _flush(self):
        from apps.reviews.models import Review
        from apps.orders.models import Order, OrderItem, OrderStatus
        from apps.pos.models import POSOrder, POSOrderItem, POSProduct
        from apps.menu.models import Category, Product, Advertise, Cafe, Schedule, FoodType
        from apps.accounts.models import Customer, StaffUser, WebCookie
        from apps.core.models import Company, Building, Location, State

        for M in [Review, OrderStatus, OrderItem, Order, POSOrderItem, POSOrder, POSProduct, Schedule, Product]:
            M.objects.all().delete()
        Category.objects.filter(parent__isnull=False).delete()
        Category.objects.all().delete()
        for M in [Advertise, Cafe, FoodType, Customer, WebCookie]:
            M.objects.all().delete()
        StaffUser.objects.filter(is_superuser=False).delete()
        for M in [Building, Company, Location, State]:
            M.objects.all().delete()
        self._ok("Data cleared")

    # ── STATES / LOCATIONS / ORG ─────────────────────────────────

    def _import_states(self):
        from apps.core.models import State
        rows = self._parse("state_list")
        n = 0
        for r in rows:
            _, created = State.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={"name": r.get("state") or ""},
            )
            if created:
                n += 1
        self._ok(f"States: {n}/{len(rows)}")

    def _import_locations(self):
        from apps.core.models import Location
        rows = self._parse("tbl_location")
        n = 0
        for r in rows:
            _, created = Location.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={
                    "name": r.get("name") or "",
                    "is_active": self._int(r.get("status"), 1) == 1,
                    "is_deleted": self._int(r.get("flag"), 1) == 0,
                },
            )
            if created:
                n += 1
        self._ok(f"Locations: {n}/{len(rows)}")

    def _import_companies(self):
        from apps.core.models import Company
        self._ensure_legacy_company()
        rows = self._parse("tbl_company")
        n = 0
        for r in rows:
            _, created = Company.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={
                    "name": r.get("name") or "",
                    "company_address": r.get("company_address") or "",
                    "company_gst": r.get("company_gst") or "",
                    "phone": r.get("phone") or "",
                    "order_from_time": self._t(r.get("frm_time")),
                    "order_to_time": self._t(r.get("to_time")),
                    "address": r.get("address") or "",
                    "bill_company": self._int(r.get("bill_company"), 2),
                    "company_meal_amount": self._dec(r.get("cmamt"), "0"),
                    "cod_payment": self._int(r.get("cod_payment")) == 1,
                    "store_status": self._int(r.get("store_status"), 1) == 1,
                    "store_order_enabled": self._int(r.get("store_ord")) == 1,
                    "video_link": r.get("video") or "",
                    "is_active": self._int(r.get("status"), 1) == 1,
                    "is_deleted": self._int(r.get("flag"), 1) == 0,
                },
            )
            if created:
                n += 1
        self._ok(f"Companies: {n}/{len(rows)}")

    def _import_buildings(self):
        from apps.core.models import Building, Company, Location
        rows = self._parse("tbl_building")
        companies = Company.objects.in_bulk()
        locations_by_name = {loc.name.strip().lower(): loc.pk for loc in Location.objects.all()}
        n = rescued = 0
        for r in rows:
            company_id = self._int(r.get("cid"))
            if company_id not in companies:
                company_id = self._valid_company_or_placeholder(company_id)
                rescued += 1
            location_name = (r.get("lid") or "").strip().lower()
            location_id = locations_by_name.get(location_name)
            _, created = Building.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={
                    "company_id": company_id,
                    "location_id": location_id,
                    "name": r.get("bname") or "",
                    "is_active": self._int(r.get("status"), 1) == 1,
                    "is_deleted": self._int(r.get("flag"), 1) == 0,
                },
            )
            if created:
                n += 1
        self._ok(f"Buildings: {n}/{len(rows)} ({rescued} rescued)")

    # ── FOOD TYPES ────────────────────────────────────────────────

    def _import_food_types(self):
        from apps.menu.models import FoodType
        rows = self._parse("tbl_foodtype")
        n = 0
        for r in rows:
            _, created = FoodType.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={"name": r.get("name") or "", "is_active": self._int(r.get("status"), 1) == 1},
            )
            if created:
                n += 1
        self._ok(f"Food types: {n}/{len(rows)}")

    # ── STAFF USERS ───────────────────────────────────────────────

    def _import_staff(self):
        from apps.accounts.models import StaffUser
        from apps.core.models import Company

        role_map = {
            "1": StaffUser.ROLE_SUPERADMIN,
            "2": StaffUser.ROLE_ADMIN,
            "3": StaffUser.ROLE_CAFEMAN,
            "4": StaffUser.ROLE_POS,
            "5": StaffUser.ROLE_REPORTS,
        }
        rows = self._parse("tbl_users")
        company_ids = set(Company.objects.values_list("id", flat=True))
        existing_emails = set(StaffUser.objects.values_list("email", flat=True))
        to_create = []
        for r in rows:
            email = (r.get("user_email") or "").strip().lower()
            if not email or email in existing_emails:
                continue
            existing_emails.add(email)
            level = str(r.get("user_level") or "2").strip()
            role = role_map.get(level, StaffUser.ROLE_POS)
            is_super = role == StaffUser.ROLE_SUPERADMIN
            company_id = self._int(r.get("cid"))
            to_create.append(
                StaffUser(
                    id=self._int(r["user_id"]),
                    email=email,
                    name=r.get("user_name") or email.split("@")[0],
                    phone=r.get("user_phone") or "",
                    role=role,
                    company_id=company_id if company_id in company_ids else None,
                    is_staff=role in (StaffUser.ROLE_SUPERADMIN, StaffUser.ROLE_ADMIN, StaffUser.ROLE_CAFEMAN),
                    is_superuser=is_super,
                    is_active=self._int(r.get("status"), 1) == 1,
                    password="md5$" + (r.get("user_password") or ""),
                )
            )
        StaffUser.objects.bulk_create(to_create, ignore_conflicts=True, batch_size=500)
        self._ok(f"Staff: {len(to_create)}/{len(rows)} (run reset_admin to set passwords)")

    # ── CUSTOMERS ─────────────────────────────────────────────────

    def _import_customers(self):
        from apps.accounts.models import Customer
        from apps.core.models import Company, Building

        rows = self._parse("tbl_login")
        company_ids = set(Company.objects.values_list("id", flat=True))
        building_ids = set(Building.objects.values_list("id", flat=True))
        n = skipped = rescued = 0
        for r in rows:
            company_id = self._int(r.get("company"))
            if company_id not in company_ids:
                company_id = self._valid_company_or_placeholder(company_id)
                rescued += 1
            building_id = self._int(r.get("building"))
            _, created = Customer.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={
                    "company_id": company_id,
                    "building_id": building_id if building_id in building_ids else None,
                    "name": r.get("name") or "",
                    "phone": r.get("phone") or "",
                    "email": r.get("email") or "",
                    "password_hash": r.get("password") or "",
                    "avatar": r.get("img") or "",
                    "verification_key": r.get("verification_key") or "",
                    "is_email_verified": self._normalize_bool(r.get("is_email_verified")),
                    "otp": self._int(r.get("otp")),
                    "token": r.get("token") or "",
                    "token_expires": self._normalize_bool(r.get("expires")),
                    "address": r.get("address") or "",
                    "cod_payment": self._int(r.get("cod_payment")) == 1,
                    "monthly_payment": self._int(r.get("monthly_payment")) == 1,
                    "is_active": self._int(r.get("status"), 1) == 1,
                    "is_deleted": self._int(r.get("flag"), 1) == 0,
                    "created_at": self._dt(r.get("create_date")) or timezone.now(),
                },
            )
            if created:
                n += 1
        self._ok(f"Customers: {n}/{len(rows)} ({skipped} skipped, {rescued} rescued)")

    # ── CATEGORIES / SCHEDULES / CAFE / ADS / PRODUCTS ───────────

    def _import_categories(self):
        from apps.menu.models import Category
        rows = self._parse("tbl_category")
        n = 0
        for r in rows:
            _, created = Category.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={
                    "slug": r.get("slug") or str(r["id"]),
                    "name": r.get("name") or "",
                    "icon_type": self._int(r.get("icon")),
                    "tagline": r.get("tagline") or "",
                    "cat_type": self._int(r.get("type"), 1),
                    "position_order": self._int(r.get("position_order")),
                    "is_active": self._int(r.get("status"), 1) == 1,
                    "is_deleted": self._int(r.get("flag"), 1) == 0,
                },
            )
            if created:
                n += 1

        cats = Category.objects.in_bulk()
        for r in rows:
            cat = cats.get(self._int(r["id"]))
            if not cat:
                continue
            parent_id = self._int(r.get("parent_id"))
            sub_parent_id = None  # sub_parent deprecated — hierarchy is Offering→Category→Product
            changed = False
            if parent_id and cat.parent_id != parent_id and parent_id in cats:
                cat.parent_id = parent_id
                changed = True
            if False:  # sub_parent_id logic disabled — field kept dormant
                pass
                changed = True
            if changed:
                cat.save(update_fields=["parent"])
        self._ok(f"Categories: {n}/{len(rows)}")

    def _link_category_companies(self):
        from apps.menu.models import Category
        from apps.core.models import Company

        rows = self._parse("tbl_category")
        categories = Category.objects.in_bulk()
        company_ids = set(Company.objects.values_list("id", flat=True))
        through = Category.companies.through
        existing_pairs = set(through.objects.values_list("category_id", "company_id"))
        inserts = []
        n = 0
        for r in rows:
            category_id = self._int(r["id"])
            if category_id not in categories:
                continue
            for company_id in self._int_list(r.get("cmid")):
                if company_id not in company_ids:
                    continue
                pair = (category_id, company_id)
                if pair in existing_pairs:
                    continue
                existing_pairs.add(pair)
                inserts.append(through(category_id=category_id, company_id=company_id))
                n += 1
        through.objects.bulk_create(inserts, ignore_conflicts=True, batch_size=1000)
        self._ok(f"Category-company links: {n}")

    def _import_schedules(self):
        from apps.menu.models import Schedule, Category
        rows = self._parse("tbl_schedule")
        category_ids = set(Category.objects.values_list("id", flat=True))
        n = 0
        for r in rows:
            start_time = self._t(r.get("start_time"))
            end_time = self._t(r.get("end_time"))
            if not start_time or not end_time:
                continue
            category_id = self._int(r.get("sub_id"))
            _, created = Schedule.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={
                    "category_id": category_id if category_id in category_ids else None,
                    "display_day": r.get("display_day") or "All",
                    "start_time": start_time,
                    "end_time": end_time,
                },
            )
            if created:
                n += 1
        self._ok(f"Schedules: {n}/{len(rows)}")

    def _import_cafes(self):
        from apps.menu.models import Cafe
        from apps.core.models import Company
        rows = self._parse("tbl_cafes")
        company_ids = set(Company.objects.values_list("id", flat=True))
        n = rescued = 0
        for r in rows:
            company_id = self._int(r.get("cmid"))
            if company_id not in company_ids:
                company_id = self._valid_company_or_placeholder(company_id)
                rescued += 1
            _, created = Cafe.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={
                    "company_id": company_id,
                    "name": r.get("name") or "",
                    "is_active": self._int(r.get("status"), 1) == 1,
                    "is_deleted": self._int(r.get("flag"), 1) == 0,
                },
            )
            if created:
                n += 1
        self._ok(f"Cafes: {n}/{len(rows)} ({rescued} rescued)")

    def _import_adverts(self):
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
                },
            )
            if created:
                n += 1
        self._ok(f"Adverts: {n}/{len(rows)}")

    def _import_products(self):
        from apps.menu.models import Product, Category, FoodType
        from apps.core.models import Company

        rows = self._parse("tbl_product")
        category_ids = set(Category.objects.values_list("id", flat=True))
        company_ids = set(Company.objects.values_list("id", flat=True))
        food_type_ids = set(FoodType.objects.values_list("id", flat=True))
        n = skipped = 0
        product_food_links = []
        through = Product.food_type.through
        seen_links = set(through.objects.values_list("product_id", "foodtype_id"))

        for r in rows:
            category_id = self._int(r.get("cid"))
            if category_id not in category_ids:
                skipped += 1
                continue
            product, created = Product.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={
                    "category_id": category_id,
                    "sub_category_id": None,   # deprecated — field kept dormant
                    "sub_list_id":     None,   # deprecated — field kept dormant
                    "company_id": self._int(r.get("company")) if self._int(r.get("company")) in company_ids else None,
                    "slug": r.get("slug") or str(r["id"]),
                    "name": r.get("pname") or "",
                    "code": r.get("code") or "",
                    "price": self._dec(r.get("price")),
                    "company_price": self._dec(r.get("cmprice")),
                    "packing_price": self._dec(r.get("packing_price")),
                    "min_qty": self._int(r.get("min_qty") or "1", 1),
                    "max_qty": self._int(r.get("max_qty") or "10", 10) or 10,
                    "pos_qty": self._int(r.get("pos_qty")),
                    "description": r.get("details") or "",
                    "rating": self._dec(r.get("rating") or "0"),
                    "position_order": self._int(r.get("position_order")),
                    "is_active": self._int(r.get("status"), 1) == 1,
                    "is_deleted": self._int(r.get("flag"), 1) == 0,
                    "menu_date": (self._dt(r.get("mdate")) or timezone.now()).date() if r.get("mdate") else None,
                    "available_from": self._t(r.get("frm_time")),
                    "available_to": self._t(r.get("to_time")),
                    "start_datetime": self._dt(r.get("start_date")),
                    "end_datetime": self._dt(r.get("end_date")),
                },
            )
            if created:
                n += 1
            for ft_id in self._int_list(r.get("type_id")):
                if ft_id in food_type_ids and (product.pk, ft_id) not in seen_links:
                    seen_links.add((product.pk, ft_id))
                    product_food_links.append(through(product_id=product.pk, foodtype_id=ft_id))
        through.objects.bulk_create(product_food_links, ignore_conflicts=True, batch_size=1000)
        self._ok(f"Products: {n}/{len(rows)} ({skipped} skipped — no category)")

    # ── ORDERS ────────────────────────────────────────────────────

    def _import_orders(self):
        from apps.orders.models import Order
        from apps.accounts.models import Customer
        from apps.core.models import Company
        from apps.menu.models import Cafe

        status_map = {0: 6, 1: 1, 2: 2, 3: 3, 4: 5}
        pay_map = {"Online": "online", "Cash": "cash", "Monthly": "monthly", "Company": "company", "COD": "cash", "PAID": "online"}

        rows = self._parse("tbl_orders")
        company_ids = set(Company.objects.values_list("id", flat=True))
        customer_ids = set(Customer.objects.values_list("id", flat=True))
        cafe_ids = set(Cafe.objects.values_list("id", flat=True))
        used_numbers = set(Order.objects.values_list("order_number", flat=True))

        batch = []
        n = skipped = 0
        for r in rows:
            company_id = self._int(r.get("cmid"))
            customer_id = self._int(r.get("uid"))
            if company_id not in company_ids or customer_id not in customer_ids:
                skipped += 1
                continue

            raw_order_number = r.get("orderno") or ""
            order_number = self._unique_token(raw_order_number, used_numbers, "NQ", self._int(r["id"]))
            orig_status = self._int(r.get("orderstatus"), 1)
            payment_mode = pay_map.get((r.get("paymentmode") or "Online").strip(), "online")
            created_at = self._dt(r.get("entry_date")) or self._dt(r.get("create_date")) or timezone.now()

            batch.append(
                Order(
                    id=self._int(r["id"]),
                    company_id=company_id,
                    customer_id=customer_id,
                    cafe_id=self._int(r.get("rid")) if self._int(r.get("rid")) in cafe_ids else None,
                    coupon_id=self._int(r.get("cupid")),
                    coupon_discount=self._dec(r.get("cupdis")),
                    subtotal=self._dec(r.get("subtotal")),
                    shipping_cost=self._dec(r.get("shpcost")),
                    bill_to_company=self._dec(r.get("bill_to_company")),
                    my_pay=self._dec(r.get("my_pay")),
                    total_amount=self._dec(r.get("totalamt")),
                    order_number=order_number,
                    payment_mode=payment_mode,
                    payment_status=r.get("payment") or "paid",
                    transaction_id=r.get("transaction_id") or "",
                    order_type=self._int(r.get("order_type")),
                    order_status=status_map.get(orig_status, 1),
                    review_given=self._int(r.get("review")) == 1,
                    session_foodtype=r.get("session_foodtype") or "",
                    session_item_date=r.get("session_item_date") or "",
                    created_at=created_at,
                    scheduled_date=self._dt(r.get("create_date")),
                    is_deleted=self._int(r.get("is_deleted"), 1) != 1,
                )
            )
            n += 1
            if len(batch) >= 500:
                Order.objects.bulk_create(batch, ignore_conflicts=True, batch_size=500)
                batch = []
                self.stdout.write(f"    {n} orders…", ending="\r")
                sys.stdout.flush()
        if batch:
            Order.objects.bulk_create(batch, ignore_conflicts=True, batch_size=500)
        self._ok(f"Orders: {n}/{len(rows)} ({skipped} skipped)")

    def _import_order_items(self):
        from apps.orders.models import Order, OrderItem
        from apps.menu.models import Product
        from apps.core.models import Company

        rows = self._parse("tbl_orderitems")
        order_company_map = dict(Order.objects.values_list("id", "company_id"))
        product_ids = set(Product.objects.values_list("id", flat=True))
        company_ids = set(Company.objects.values_list("id", flat=True))
        batch = []
        n = skipped = 0
        for r in rows:
            order_id = self._int(r.get("oid"))
            if order_id not in order_company_map:
                skipped += 1
                continue
            company_id = self._int(r.get("cmid"))
            if company_id not in company_ids:
                company_id = order_company_map[order_id]
            product_id = self._int(r.get("pid"))
            batch.append(
                OrderItem(
                    id=self._int(r["id"]),
                    company_id=company_id,
                    order_id=order_id,
                    product_id=product_id if product_id in product_ids else None,
                    row_id=r.get("row_id") or "",
                    price=self._dec(r.get("price")),
                    qty=self._int(r.get("qty"), 1),
                    image_snapshot=r.get("img") or "",
                    is_deleted=self._int(r.get("flag"), 0) == 0,
                    created_at=self._dt(r.get("create_date")) or timezone.now(),
                )
            )
            n += 1
            if len(batch) >= 1000:
                OrderItem.objects.bulk_create(batch, ignore_conflicts=True, batch_size=1000)
                batch = []
                self.stdout.write(f"    {n} items…", ending="\r")
                sys.stdout.flush()
        if batch:
            OrderItem.objects.bulk_create(batch, ignore_conflicts=True, batch_size=1000)
        self._ok(f"Order items: {n}/{len(rows)} ({skipped} skipped)")

    def _import_order_statuses(self):
        from apps.orders.models import Order, OrderStatus

        status_map = {0: 6, 1: 1, 2: 2, 3: 3, 4: 5}
        rows = self._parse("tbl_order_status")
        order_ids = set(Order.objects.values_list("id", flat=True))
        batch = []
        n = skipped = 0
        for r in rows:
            order_id = self._int(r.get("oid"))
            if order_id not in order_ids:
                skipped += 1
                continue
            batch.append(
                OrderStatus(
                    id=self._int(r["id"]),
                    order_id=order_id,
                    status=status_map.get(self._int(r.get("status"), 1), 1),
                    details=r.get("details") or "",
                    created_at=self._dt(r.get("create_date")) or timezone.now(),
                )
            )
            n += 1
            if len(batch) >= 2000:
                OrderStatus.objects.bulk_create(batch, ignore_conflicts=True, batch_size=2000)
                batch = []
                self.stdout.write(f"    {n} order status rows…", ending="\r")
                sys.stdout.flush()
        if batch:
            OrderStatus.objects.bulk_create(batch, ignore_conflicts=True, batch_size=2000)
        self._ok(f"Order status history: {n}/{len(rows)} ({skipped} skipped)")

    # ── POS ───────────────────────────────────────────────────────

    def _import_pos_products(self):
        from apps.pos.models import POSProduct
        from apps.core.models import Company
        rows = self._parse("tbl_pos_product")
        company_ids = set(Company.objects.values_list("id", flat=True))
        n = 0
        for r in rows:
            company_id = self._int(r.get("cmpid"))
            if company_id not in company_ids:
                continue
            _, created = POSProduct.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={
                    "company_id": company_id,
                    "name": r.get("pname") or "",
                    "price": self._dec(r.get("price")),
                    "is_active": self._int(r.get("status"), 1) == 1,
                    "is_deleted": self._int(r.get("flag"), 1) == 0,
                },
            )
            if created:
                n += 1
        self._ok(f"POS products: {n}/{len(rows)}")

    def _import_pos_orders(self):
        from apps.pos.models import POSOrder
        from apps.core.models import Company

        rows = self._parse("tbl_pos_orders")
        company_ids = set(Company.objects.values_list("id", flat=True))
        used_numbers = set(POSOrder.objects.values_list("order_number", flat=True))
        batch = []
        n = skipped = 0
        for r in rows:
            company_id = self._int(r.get("compid"))
            if company_id not in company_ids:
                skipped += 1
                continue
            payment_type = self._int(r.get("payment_type"), 1)
            if payment_type not in (1, 2, 3):
                payment_type = 1
            batch.append(
                POSOrder(
                    id=self._int(r["id"]),
                    company_id=company_id,
                    customer_name=r.get("uname") or "Walk-in Customer",
                    customer_email=r.get("uemail") or "",
                    customer_phone=r.get("uphone") or "",
                    order_number=self._unique_token(r.get("ordnumber"), used_numbers, "POS", self._int(r["id"])),
                    total_amount=self._dec(r.get("totamount")),
                    payment_type=payment_type,
                    is_deleted=self._int(r.get("flag"), 1) == 0,
                    created_at=self._dt(r.get("create_date")) or timezone.now(),
                )
            )
            n += 1
            if len(batch) >= 500:
                POSOrder.objects.bulk_create(batch, ignore_conflicts=True, batch_size=500)
                batch = []
                self.stdout.write(f"    {n} pos orders…", ending="\r")
                sys.stdout.flush()
        if batch:
            POSOrder.objects.bulk_create(batch, ignore_conflicts=True, batch_size=500)
        self._ok(f"POS orders: {n}/{len(rows)} ({skipped} skipped)")

    def _import_pos_items(self):
        from apps.pos.models import POSOrder, POSOrderItem
        from apps.core.models import Company

        rows = self._parse("tbl_pos_orderitems")
        pos_order_ids = set(POSOrder.objects.values_list("id", flat=True))
        company_ids = set(Company.objects.values_list("id", flat=True))
        batch = []
        n = skipped = 0
        for r in rows:
            order_id = self._int(r.get("oid"))
            company_id = self._int(r.get("compid"))
            if order_id not in pos_order_ids or company_id not in company_ids:
                skipped += 1
                continue
            batch.append(
                POSOrderItem(
                    id=self._int(r["id"]),
                    company_id=company_id,
                    order_id=order_id,
                    product_name=r.get("items") or "",
                    price=self._dec(r.get("price")),
                    qty=self._int(r.get("qty"), 1),
                    amount=self._dec(r.get("amount")),
                    is_deleted=self._int(r.get("flag"), 1) == 0,
                    created_at=self._dt(r.get("create_date")) or timezone.now(),
                )
            )
            n += 1
            if len(batch) >= 1000:
                POSOrderItem.objects.bulk_create(batch, ignore_conflicts=True, batch_size=1000)
                batch = []
                self.stdout.write(f"    {n} pos items…", ending="\r")
                sys.stdout.flush()
        if batch:
            POSOrderItem.objects.bulk_create(batch, ignore_conflicts=True, batch_size=1000)
        self._ok(f"POS order items: {n}/{len(rows)} ({skipped} skipped)")

    # ── REVIEWS / WEB COOKIES ─────────────────────────────────────

    def _import_reviews(self):
        from apps.reviews.models import Review
        from apps.accounts.models import Customer
        rows = self._parse("tbl_review")
        customer_ids = set(Customer.objects.values_list("id", flat=True))
        n = skipped = 0
        for r in rows:
            customer_id = self._int(r.get("uid"))
            if customer_id not in customer_ids:
                skipped += 1
                continue
            _, created = Review.objects.update_or_create(
                pk=self._int(r["id"]),
                defaults={
                    "customer_id": customer_id,
                    "rating": self._dec(r.get("rating") or "5"),
                    "details": r.get("details") or "",
                    "is_active": self._int(r.get("status"), 1) == 1,
                    "is_deleted": self._int(r.get("flag"), 1) == 0,
                    "created_at": self._dt(r.get("create_date")) or timezone.now(),
                },
            )
            if created:
                n += 1
        self._ok(f"Reviews: {n}/{len(rows)} ({skipped} skipped)")

    def _import_webcookies(self):
        from apps.accounts.models import Customer, WebCookie
        rows = self._parse("tbl_web_cookie")
        customer_ids = set(Customer.objects.values_list("id", flat=True))
        batch = []
        n = 0
        for r in rows:
            customer_id = self._int(r.get("user_id"))
            batch.append(
                WebCookie(
                    id=self._int(r["id"]),
                    cookie_id=r.get("cookie_id") or "",
                    customer_id=customer_id if customer_id in customer_ids else None,
                    delivery_type=r.get("delivery_type") or "",
                    delivery_date=r.get("delivery_date") or "",
                    created_at=self._dt(r.get("create_date")) or timezone.now(),
                )
            )
            n += 1
            if len(batch) >= 1000:
                WebCookie.objects.bulk_create(batch, ignore_conflicts=True, batch_size=1000)
                batch = []
        if batch:
            WebCookie.objects.bulk_create(batch, ignore_conflicts=True, batch_size=1000)
        self._ok(f"Web cookies: {n}/{len(rows)}")

    # ── SUMMARY ───────────────────────────────────────────────────

    def _summary(self):
        from apps.core.models import Company, Building, Location, State
        from apps.accounts.models import Customer, StaffUser, WebCookie
        from apps.menu.models import Category, Product, Cafe, Schedule, Advertise
        from apps.orders.models import Order, OrderItem, OrderStatus
        from apps.pos.models import POSOrder, POSOrderItem, POSProduct
        from apps.reviews.models import Review

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Import Summary ==="))
        for lbl, val in [
            ("States", State.objects.count()),
            ("Companies", Company.objects.count()),
            ("Locations", Location.objects.count()),
            ("Buildings", Building.objects.count()),
            ("Staff Users", StaffUser.objects.count()),
            ("Customers", Customer.objects.count()),
            ("Categories", Category.objects.count()),
            ("Schedules", Schedule.objects.count()),
            ("Cafes", Cafe.objects.count()),
            ("Adverts", Advertise.objects.count()),
            ("Products", Product.objects.count()),
            ("Orders", Order.objects.count()),
            ("Order Items", OrderItem.objects.count()),
            ("Order Statuses", OrderStatus.objects.count()),
            ("POS Products", POSProduct.objects.count()),
            ("POS Orders", POSOrder.objects.count()),
            ("POS Items", POSOrderItem.objects.count()),
            ("Reviews", Review.objects.count()),
            ("Web Cookies", WebCookie.objects.count()),
        ]:
            self.stdout.write(f"  {lbl:<20} {val:>6,}")
        self.stdout.write("\nRun: python manage.py reset_admin\n")
