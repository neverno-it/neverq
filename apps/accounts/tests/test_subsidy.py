"""
Tests for subsidy / meal benefit logic.
Three configuration points:
  1. Company:  bill_company=2, company_meal_amount
  2. Product:  company.free_meal_products (M2M)
  3. Customer: meal_benefit, subsidy_amount_override

Rules:
  - Subsidy only applies to web orders (registered customers).
  - Kiosk customer always has meal_benefit='none'.
  - free_meal_products empty = ALL products eligible.
  - free_meal_products populated = ONLY those products eligible.
  - One use per day (benefit_used_on check).
  - company.bill_company must be 2 for any subsidy to fire.
"""
from decimal import Decimal
from django.test import TestCase
from apps.core.models import Company, Building
from apps.menu.models import Category, Product, Cafe
from apps.accounts.models import Customer
from apps.orders.models import Order, OrderStatusChoices


def _make_company(**kwargs):
    defaults = dict(name='SubCo', is_active=True, bill_company=2,
                    company_meal_amount=Decimal('30'), store_status=True)
    defaults.update(kwargs)
    return Company.objects.create(**defaults)


def _make_product(company, name, price, slug=None):
    cat, _ = Category.objects.get_or_create(
        slug='subcat', defaults={'name': 'SubCat', 'is_active': True})
    cat.companies.add(company)
    return Product.objects.create(
        name=name, slug=slug or name.lower().replace(' ', '-'),
        company=company, category=cat,
        price=Decimal(str(price)), is_active=True, max_qty=10, min_qty=1)


def _make_customer(company, meal_benefit='subsidy', override=None):
    return Customer.objects.create(
        company=company, name='Emp', email=f'emp{company.pk}@test.com',
        phone='1', password_hash='x', is_active=True, is_approved=True,
        meal_benefit=meal_benefit, subsidy_amount_override=override)


def _cart(products, qty=1):
    return {str(p.pk): {'qty': qty, 'price': str(p.price), 'name': p.name} for p in products}


class SubsidyNoProductRestrictionTests(TestCase):
    """When free_meal_products is EMPTY, all products qualify."""

    def setUp(self):
        self.company = _make_company(company_meal_amount=Decimal('30'))
        self.p1 = _make_product(self.company, 'Chicken', 50, 'chk')
        self.p2 = _make_product(self.company, 'Fish', 35, 'fsh')
        self.customer = _make_customer(self.company, meal_benefit='subsidy')

    def test_subsidy_applies_when_no_product_restriction(self):
        """Empty free_meal_products → entire cart qualifies → ₹30 subsidy."""
        from apps.menu.views import _build_cart_summary
        summary = _build_cart_summary(self.customer, _cart([self.p1, self.p2]))
        self.assertEqual(summary['subsidy'], Decimal('30'))
        self.assertEqual(summary['my_pay'], Decimal('55'))   # 85 - 30

    def test_company_pay_covers_full_cart(self):
        """MEAL_BENEFIT_COMPANY_PAY → subsidy = entire cart amount."""
        self.customer.meal_benefit = 'company_pay'
        self.customer.save()
        from apps.menu.views import _build_cart_summary
        summary = _build_cart_summary(self.customer, _cart([self.p1, self.p2]))
        self.assertEqual(summary['subsidy'], Decimal('85'))
        self.assertEqual(summary['my_pay'], Decimal('0'))

    def test_no_benefit_no_subsidy(self):
        """meal_benefit=none → zero subsidy."""
        self.customer.meal_benefit = 'none'
        self.customer.save()
        from apps.menu.views import _build_cart_summary
        summary = _build_cart_summary(self.customer, _cart([self.p1]))
        self.assertEqual(summary['subsidy'], Decimal('0'))

    def test_subsidy_capped_at_cart_total(self):
        """Subsidy cannot exceed cart total."""
        self.company.company_meal_amount = Decimal('200')
        self.company.save()
        from apps.menu.views import _build_cart_summary
        summary = _build_cart_summary(self.customer, _cart([self.p1]))
        # cart = ₹50, subsidy cap = ₹50 (not ₹200)
        self.assertEqual(summary['subsidy'], Decimal('50'))
        self.assertEqual(summary['my_pay'], Decimal('0'))

    def test_per_customer_override_used(self):
        """subsidy_amount_override takes precedence over company default."""
        self.customer.subsidy_amount_override = Decimal('15')
        self.customer.save()
        from apps.menu.views import _build_cart_summary
        summary = _build_cart_summary(self.customer, _cart([self.p1]))
        self.assertEqual(summary['subsidy'], Decimal('15'))
        self.assertEqual(summary['my_pay'], Decimal('35'))   # 50 - 15


class SubsidyProductRestrictionTests(TestCase):
    """When free_meal_products is populated, only those products qualify."""

    def setUp(self):
        self.company = _make_company(company_meal_amount=Decimal('30'))
        self.eligible_p = _make_product(self.company, 'Veg Thali', 80, 'veg-thali')
        self.ineligible_p = _make_product(self.company, 'Juice', 30, 'juice')
        # Only veg_thali is eligible
        self.company.free_meal_products.add(self.eligible_p)
        self.customer = _make_customer(self.company, meal_benefit='subsidy')

    def test_subsidy_applies_for_eligible_product(self):
        """Cart with eligible product → subsidy fires."""
        from apps.menu.views import _build_cart_summary
        summary = _build_cart_summary(self.customer, _cart([self.eligible_p]))
        self.assertEqual(summary['subsidy'], Decimal('30'))

    def test_no_subsidy_for_ineligible_product_only(self):
        """Cart with only ineligible product → no subsidy."""
        from apps.menu.views import _build_cart_summary
        summary = _build_cart_summary(self.customer, _cart([self.ineligible_p]))
        self.assertEqual(summary['subsidy'], Decimal('0'))

    def test_mixed_cart_subsidy_only_on_eligible(self):
        """Mixed cart → subsidy applied only to eligible product's line total."""
        from apps.menu.views import _build_cart_summary
        summary = _build_cart_summary(self.customer, _cart([self.eligible_p, self.ineligible_p]))
        # eligible_subtotal = 80 (only veg_thali), subsidy capped at 30
        self.assertEqual(summary['subsidy'], Decimal('30'))


class SubsidyCompanyBillBlockTests(TestCase):
    """bill_company=1 (Employee Pays) disables ALL subsidy."""

    def test_no_subsidy_when_employee_pays(self):
        company = _make_company(bill_company=1, company_meal_amount=Decimal('50'))
        p = _make_product(company, 'Meal', 100, 'meal-ep')
        cust = _make_customer(company, meal_benefit='subsidy')
        from apps.menu.views import _build_cart_summary
        summary = _build_cart_summary(cust, _cart([p]))
        self.assertEqual(summary['subsidy'], Decimal('0'))
        self.assertEqual(summary['my_pay'], Decimal('100'))


class SubsidyOncePerDayTests(TestCase):
    """Subsidy fires only once per day per customer."""

    def test_benefit_blocked_after_first_use(self):
        company = _make_company(company_meal_amount=Decimal('30'))
        p = _make_product(company, 'Lunch', 70, 'lunch-opd')
        cust = _make_customer(company, meal_benefit='subsidy')

        # Place first order that consumed the benefit
        Order.objects.create(
            company=company, customer=cust,
            subtotal=70, total_amount=40, my_pay=40,
            bill_to_company=Decimal('30'),   # > 0 → marks benefit as used
            order_number='TEST-SUB-001',
            order_status=OrderStatusChoices.CONFIRMED,
        )
        from apps.menu.views import _build_cart_summary
        summary = _build_cart_summary(cust, _cart([p]))
        self.assertEqual(summary['subsidy'], Decimal('0'),
            'Benefit must not apply twice on the same day')
        self.assertTrue(summary['benefit_used_today'])


class KioskSubsidyBlockTests(TestCase):
    """Kiosk orders must never receive subsidy."""

    def test_kiosk_customer_never_gets_subsidy(self):
        """Even if someone manually sets meal_benefit on the kiosk customer,
        kiosk_place_order resets it to none before creating the order."""
        company = _make_company(company_meal_amount=Decimal('50'))
        p = _make_product(company, 'Snack', 40, 'snack-kiosk')

        # Create kiosk customer with wrongly-set benefit
        kiosk_cust = Customer.objects.create(
            company=company,
            email=f'kiosk@{company.name[:20].replace(" ","").lower()}.kiosk',
            name='Kiosk Orders', phone='', password_hash='x',
            is_active=True, meal_benefit='company_pay',  # wrong — someone set it
        )

        # Simulate what kiosk_place_order does:
        from apps.accounts.models import Customer as C
        if kiosk_cust.meal_benefit != 'none':
            C.objects.filter(pk=kiosk_cust.pk).update(meal_benefit='none', subsidy_eligible=False)
            kiosk_cust.meal_benefit = 'none'

        from apps.menu.views import _build_cart_summary
        summary = _build_cart_summary(kiosk_cust, _cart([p]))
        self.assertEqual(summary['subsidy'], Decimal('0'),
            'Kiosk customer must never receive subsidy')
        self.assertEqual(summary['my_pay'], summary['total'])
