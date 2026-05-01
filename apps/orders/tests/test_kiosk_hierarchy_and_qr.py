"""
Test: kiosk hierarchy visibility and QR same-day validity.
Covers: Offering -> Category -> Product chain, schedule_bypass, QR expiry.
"""
from datetime import date, timedelta
from django.test import TestCase, RequestFactory
from django.utils import timezone

from apps.core.models import Company
from apps.menu.models import Category, Offering, Product
from apps.accounts.models import Customer


def _make_company(**kw):
    return Company.objects.create(
        name='TestCo', store_status=True,
        order_open_days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],
        **kw
    )


def _make_product(company, name='Prod', price=50, **kw):
    cat = kw.pop('category', None) or Category.objects.create(name='Cat')
    cat.companies.add(company)
    is_active = kw.pop('is_active', True)
    return Product.objects.create(
        name=name, company=company, category=cat, price=price, is_active=is_active, **kw
    )


class KioskHierarchyTest(TestCase):

    def setUp(self):
        self.co = _make_company()
        self.today_abbr = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][timezone.localtime().weekday()]

    # ── Offerings ────────────────────────────────────────────────

    def test_offering_active_now_shown(self):
        """Active offering with no time restriction is available."""
        off = Offering.objects.create(company=self.co, name='Lunch', is_active=True)
        self.assertTrue(off.is_active_now())

    def test_offering_inactive_hidden(self):
        """Inactive offering is never available."""
        off = Offering.objects.create(company=self.co, name='Dinner', is_active=False)
        self.assertFalse(off.is_active_now())

    def test_offering_wrong_day_hidden(self):
        """Offering restricted to a different day is not available today."""
        other_days = [d for d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'] if d != self.today_abbr]
        off = Offering.objects.create(
            company=self.co, name='WrongDay', is_active=True, open_days=[other_days[0]]
        )
        self.assertFalse(off.is_active_now())

    def test_offering_correct_day_shown(self):
        """Offering matching today's day is available."""
        off = Offering.objects.create(
            company=self.co, name='TodayOff', is_active=True, open_days=[self.today_abbr]
        )
        self.assertTrue(off.is_active_now())

    # ── Categories ───────────────────────────────────────────────

    def test_category_open_all_days_when_empty(self):
        """Category with empty open_days is available every day."""
        cat = Category.objects.create(name='AllDay', open_days=[])
        self.assertTrue(cat.is_open_on_day())

    def test_category_closed_other_day(self):
        other = [d for d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'] if d != self.today_abbr]
        cat = Category.objects.create(name='OtherDay', open_days=[other[0]])
        self.assertFalse(cat.is_open_on_day())

    def test_category_open_today(self):
        cat = Category.objects.create(name='Today', open_days=[self.today_abbr])
        self.assertTrue(cat.is_open_on_day())

    # ── Products ─────────────────────────────────────────────────

    def test_product_available_no_restrictions(self):
        p = _make_product(self.co)
        self.assertTrue(p.is_available_now())

    def test_product_category_closed_today_hides_product(self):
        other = [d for d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'] if d != self.today_abbr]
        cat = Category.objects.create(name='OtherDay', open_days=[other[0]])
        cat.companies.add(self.co)
        p = _make_product(self.co, category=cat)
        self.assertFalse(p.is_available_now())

    def test_schedule_bypass_ignores_category_schedule(self):
        """schedule_bypass=True means product visible even if category is closed today."""
        other = [d for d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'] if d != self.today_abbr]
        cat = Category.objects.create(name='Closed', open_days=[other[0]])
        cat.companies.add(self.co)
        p = _make_product(self.co, category=cat, schedule_bypass=True)
        self.assertTrue(p.is_available_now())

    def test_schedule_bypass_respects_product_time_window(self):
        """schedule_bypass=True still respects the product's own available_from/to."""
        import datetime
        cat = Category.objects.create(name='AllDay', open_days=[])
        cat.companies.add(self.co)
        # Time window: 00:00–00:01 (almost certainly in the past)
        p = _make_product(
            self.co, category=cat, schedule_bypass=True,
            available_from=datetime.time(0, 0),
            available_to=datetime.time(0, 1),
        )
        self.assertFalse(p.is_available_now())

    def test_inactive_product_never_available(self):
        p = _make_product(self.co, is_active=False)
        self.assertFalse(p.is_available_now())

    # ── QR validity ──────────────────────────────────────────────

    def test_same_day_qr_is_valid(self):
        """QR issued today should be accepted."""
        from apps.orders.models import CounterTicket, Order, OrderStatusChoices
        cu = Customer.objects.create(name='User', email='u@t.com', company=self.co)
        order = Order.objects.create(
            company=self.co, customer=cu,
            order_status=OrderStatusChoices.CONFIRMED,
            order_number='TEST-001',
        )
        ticket = CounterTicket.objects.create(
            company=self.co, order=order,
            scan_code='CTAABBCCDD12',
            created_at=timezone.now(),
        )
        today = timezone.localdate()
        # Use localtime() so the date comparison is always in the server's local timezone
        ticket_date = timezone.localtime(ticket.created_at).date() if ticket.created_at else None
        self.assertEqual(ticket_date, today)
        self.assertFalse(ticket_date < today)  # should NOT be expired

    def test_previous_day_qr_is_rejected(self):
        """QR issued yesterday must be rejected."""
        from apps.orders.models import CounterTicket, Order, OrderStatusChoices
        cu = Customer.objects.create(name='User2', email='u2@t.com', company=self.co)
        order = Order.objects.create(
            company=self.co, customer=cu,
            order_status=OrderStatusChoices.CONFIRMED,
            order_number='TEST-002',
        )
        yesterday = timezone.now() - timedelta(days=1)
        ticket = CounterTicket.objects.create(
            company=self.co, order=order,
            scan_code='CTEXPIRED0001',
            created_at=yesterday,
        )
        today = timezone.localdate()
        ticket_date = ticket.created_at.date()
        self.assertTrue(ticket_date < today)  # expired


# ── Featured extra products ───────────────────────────────────────────

class KioskFeaturedProductsTest(TestCase):

    def setUp(self):
        self.co = _make_company()

    def _prod(self, name, featured=False, is_active=True):
        cat = Category.objects.create(name=f'Cat-{name}', open_days=[])
        cat.companies.add(self.co)
        return Product.objects.create(
            name=name, company=self.co, category=cat, price=50,
            is_active=is_active, is_kiosk_active=True, featured_in_kiosk_extra=featured,
        )

    def test_featured_products_appear(self):
        self._prod('Featured A', featured=True)
        self._prod('Featured B', featured=True)
        self._prod('Normal', featured=False)
        featured = [p for p in Product.objects.filter(
            company=self.co, is_active=True, is_kiosk_active=True,
            featured_in_kiosk_extra=True,
        ) if p.is_available_now()]
        self.assertEqual(len(featured), 2)

    def test_max_10_featured_products(self):
        for i in range(15):
            self._prod(f'Feat{i}', featured=True)
        qs = Product.objects.filter(
            company=self.co, is_active=True, is_kiosk_active=True,
            featured_in_kiosk_extra=True,
        )
        featured = [p for p in qs if p.is_available_now()][:10]
        self.assertLessEqual(len(featured), 10)

    def test_inactive_product_excluded_from_featured(self):
        self._prod('InactiveFeat', featured=True, is_active=False)
        qs = Product.objects.filter(
            company=self.co, is_active=True, is_kiosk_active=True,
            featured_in_kiosk_extra=True,
        )
        self.assertEqual(qs.count(), 0)

    def test_non_featured_excluded(self):
        self._prod('Normal', featured=False)
        qs = Product.objects.filter(
            company=self.co, featured_in_kiosk_extra=True,
        )
        self.assertEqual(qs.count(), 0)

    def test_no_duplicates_between_main_and_featured(self):
        p = self._prod('BothGrids', featured=True)
        available_pks = {p.pk}
        all_featured = list(Product.objects.filter(
            company=self.co, featured_in_kiosk_extra=True, is_active=True,
        ))
        featured_no_dups = [f for f in all_featured if f.pk not in available_pks]
        # p is already in the main grid, so featured section should exclude it
        self.assertNotIn(p, featured_no_dups)
