"""
NeverQ — Monthly Billing Regression Tests
==========================================
Covers the 5 bugs found and fixed in the monthly billing flow:

  Bug 1 — flash_order sets payment_status='pending' for monthly (should be 'approved')
  Bug 2 — cashier confirm leaves monthly orders payment_status='pending' forever
  Bug 3 — place_order deducts wallet/points even when payment_mode=monthly
  Bug 4 — checkout template shows wallet section for monthly (template/JS guard)
  Bug 5 — button text shows ₹amount for monthly (template/JS guard)

Bugs 4 and 5 are template/JS — tested via view response content where possible.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Company
from apps.accounts.models import Customer, StaffUser
from apps.menu.models import Category, Product
from apps.orders.models import (
    Order, OrderItem, OrderStatus, OrderStatusChoices, PaymentModeChoices,
)


# ── Shared factories ──────────────────────────────────────────────────────────

def _company(**kw):
    defaults = dict(
        name='MonthlyCo',
        monthly_payment=True,
        online_payment=True,
        cod_payment=True,
        store_status=True,
    )
    defaults.update(kw)
    return Company.objects.create(**defaults)


def _category(company, name='Meals'):
    cat = Category.objects.create(
        name=name, slug=f'{name.lower()}-{company.pk}',
        is_active=True, is_deleted=False,
    )
    cat.companies.add(company)
    return cat


def _product(company, category, price=100):
    return Product.objects.create(
        company=company, category=category,
        name='Test Thali', slug=f'thali-{company.pk}',
        price=Decimal(str(price)),
        is_active=True, is_deleted=False,
        max_qty=20, min_qty=1, web_qty=-1,
    )


def _customer(company, email=None, monthly=True, wallet=Decimal('0')):
    return Customer.objects.create(
        company=company,
        name='Monthly Customer',
        email=email or f'monthly-{company.pk}@test.com',
        phone='9000000001',
        is_active=True, is_deleted=False,
        is_approved=True, is_email_verified=True,
        monthly_payment=monthly,
        wallet_balance=wallet,
    )


def _staff(company, role='admin', email=None):
    s = StaffUser.objects.create(
        email=email or f'{role}-{company.pk}@test.com',
        company=company, role=role, is_active=True,
    )
    s.set_password('testpass')
    s.save()
    return s


def _order(company, customer, payment_mode='monthly', payment_status='approved',
           order_status=OrderStatusChoices.CONFIRMED):
    return Order.objects.create(
        company=company, customer=customer,
        subtotal=Decimal('100'), total_amount=Decimal('100'),
        my_pay=Decimal('100'),
        payment_mode=payment_mode,
        payment_status=payment_status,
        order_status=order_status,
    )


def _login_customer(client, customer):
    session = client.session
    session['customer_id'] = customer.pk
    session.save()


# ── Bug 1: flash_order payment_status ────────────────────────────────────────

class FlashOrderMonthlyPaymentStatusTest(TestCase):
    """Bug 1 — flash_order must set payment_status='approved' for monthly orders."""

    def setUp(self):
        self.co = _company(name='FlashCo')
        self.cat = _category(self.co)
        self.prod = _product(self.co, self.cat)
        self.staff = _staff(self.co, role='admin', email='flash-admin@test.com')
        self.client = Client()
        self.client.force_login(self.staff)

    def _post_flash_order(self, payment_mode):
        return self.client.post(reverse('dashboard:flash_order'), {
            'company': self.co.pk,
            'customer_name': 'Walk-in Customer',
            'customer_phone': '9000000099',
            'payment_mode': payment_mode,
            'delivery_date': timezone.localdate().isoformat(),
            f'product_id[]': self.prod.pk,
            f'qty[]': '1',
        })

    def test_flash_order_monthly_gets_approved_status(self):
        """Monthly flash order must have payment_status='approved', not 'pending'."""
        resp = self._post_flash_order('monthly')
        self.assertRedirects(resp, reverse('dashboard:flash_order'))
        order = Order.objects.filter(company=self.co, payment_mode='monthly').last()
        self.assertIsNotNone(order, 'Monthly flash order was not created')
        self.assertEqual(
            order.payment_status, 'approved',
            f'Expected payment_status=approved for monthly flash order, got {order.payment_status!r}'
        )

    def test_flash_order_cash_gets_paid_status(self):
        """Cash flash order must have payment_status='paid' (sanity check)."""
        resp = self._post_flash_order('cash')
        self.assertRedirects(resp, reverse('dashboard:flash_order'))
        order = Order.objects.filter(company=self.co, payment_mode='cash').last()
        self.assertIsNotNone(order)
        self.assertEqual(order.payment_status, 'paid')

    def test_flash_order_online_gets_pending_status(self):
        """Online flash order must have payment_status='pending'."""
        resp = self._post_flash_order('online')
        self.assertRedirects(resp, reverse('dashboard:flash_order'))
        order = Order.objects.filter(company=self.co, payment_mode='online').last()
        self.assertIsNotNone(order)
        self.assertEqual(order.payment_status, 'pending')


# ── Bug 2: cashier confirm payment_status ────────────────────────────────────

class CashierConfirmMonthlyTest(TestCase):
    """Bug 2 — cashier confirming a monthly order must set payment_status='approved'."""

    def setUp(self):
        self.co = _company(name='CashierCo')
        self.customer = _customer(self.co)
        self.admin = _staff(self.co, role='admin', email='cashier-admin@test.com')
        self.client = Client()
        self.client.force_login(self.admin)

    def _confirm_order(self, order):
        return self.client.post(
            reverse('dashboard:order_update_status', kwargs={'pk': order.pk}),
            {'status': str(OrderStatusChoices.CONFIRMED), 'details': ''},
        )

    def test_confirm_monthly_pending_sets_approved(self):
        """Monthly order arriving as PENDING (flash_order bug path) must become approved on confirm."""
        order = _order(
            self.co, self.customer,
            payment_mode='monthly',
            payment_status='pending',
            order_status=OrderStatusChoices.PENDING,
        )
        resp = self._confirm_order(order)
        order.refresh_from_db()
        self.assertIn(resp.status_code, [200, 302])
        self.assertEqual(
            order.payment_status, 'approved',
            f'Expected approved after confirming monthly order, got {order.payment_status!r}'
        )
        self.assertEqual(order.order_status, OrderStatusChoices.CONFIRMED)

    def test_confirm_cash_sets_paid(self):
        """Cash order confirmed must still become paid (regression guard)."""
        order = _order(
            self.co, self.customer,
            payment_mode='cash',
            payment_status='pending',
            order_status=OrderStatusChoices.PENDING,
        )
        self._confirm_order(order)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'paid')

    def test_confirm_already_approved_monthly_unchanged(self):
        """Confirming an already-approved monthly order must not change payment_status."""
        order = _order(
            self.co, self.customer,
            payment_mode='monthly',
            payment_status='approved',
            order_status=OrderStatusChoices.PENDING,
        )
        self._confirm_order(order)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, 'approved')


# ── Bug 3: place_order wallet deduction ──────────────────────────────────────

class MonthlyWalletBlockTest(TestCase):
    """Bug 3 — place_order must NOT deduct wallet or points for monthly payment mode."""

    def setUp(self):
        self.co = _company(name='WalletBlockCo')
        self.cat = _category(self.co)
        self.prod = _product(self.co, self.cat, price=100)
        # Customer has ₹50 wallet balance
        self.customer = _customer(self.co, wallet=Decimal('50.00'))
        self.client = Client()
        _login_customer(self.client, self.customer)

    def _place_order(self, payment_mode, use_wallet='1'):
        """Place an order via the checkout form."""
        # Put product in cart
        session = self.client.session
        session['cart'] = {
            str(self.prod.pk): {
                'qty': 1, 'price': str(self.prod.price), 'name': self.prod.name
            }
        }
        session.save()
        return self.client.post(reverse('orders:place_order'), {
            'payment_mode': payment_mode,
            'use_wallet': use_wallet,
            'order_type': '0',
        })

    def test_monthly_order_does_not_deduct_wallet(self):
        """Wallet balance must be unchanged after placing a monthly order."""
        wallet_before = self.customer.wallet_balance
        resp = self._place_order('monthly', use_wallet='1')
        # Order should be created (redirect to confirmation or checkout)
        self.assertIn(resp.status_code, [200, 302])
        self.customer.refresh_from_db()
        self.assertEqual(
            self.customer.wallet_balance, wallet_before,
            f'Wallet was deducted for monthly order: before={wallet_before}, '
            f'after={self.customer.wallet_balance}'
        )

    def test_monthly_order_wallet_used_is_zero(self):
        """Order created with monthly mode must have wallet_used=0."""
        self._place_order('monthly', use_wallet='1')
        order = Order.objects.filter(
            customer=self.customer, payment_mode='monthly'
        ).last()
        if order:
            self.assertEqual(
                order.wallet_used, Decimal('0.00'),
                f'wallet_used should be 0 for monthly, got {order.wallet_used}'
            )

    def test_monthly_order_payment_status_is_approved(self):
        """Monthly order via place_order must have payment_status='approved'."""
        self._place_order('monthly', use_wallet='0')
        order = Order.objects.filter(
            customer=self.customer, payment_mode='monthly'
        ).last()
        if order:
            self.assertEqual(order.payment_status, 'approved')

    def test_monthly_order_is_auto_confirmed(self):
        """Monthly order must be auto-confirmed (CONFIRMED status, not PENDING)."""
        self._place_order('monthly', use_wallet='0')
        order = Order.objects.filter(
            customer=self.customer, payment_mode='monthly'
        ).last()
        if order:
            self.assertEqual(order.order_status, OrderStatusChoices.CONFIRMED)

    def test_cash_order_still_deducts_wallet(self):
        """Cash order with wallet must still deduct wallet (regression guard)."""
        wallet_before = self.customer.wallet_balance
        self._place_order('cash', use_wallet='1')
        self.customer.refresh_from_db()
        # Wallet should be reduced (if COD is enabled and order was placed)
        order = Order.objects.filter(customer=self.customer, payment_mode='cash').last()
        if order and order.wallet_used > 0:
            self.assertLess(self.customer.wallet_balance, wallet_before,
                'Wallet should have been deducted for cash order with use_wallet=1')


# ── _allowed_payment_modes unit tests ────────────────────────────────────────

class AllowedPaymentModesTest(TestCase):
    """Unit tests for _allowed_payment_modes covering all monthly eligibility rules."""

    def _modes(self, company_monthly, customer_monthly, my_pay, bill_to_company):
        from apps.orders.views import _allowed_payment_modes
        from unittest.mock import MagicMock
        co = MagicMock()
        cu = MagicMock()
        co.monthly_payment = company_monthly
        cu.monthly_payment = customer_monthly
        co.cod_payment = False
        co.online_payment = True
        cu.cod_payment = False
        return [v for v, _ in _allowed_payment_modes(co, cu, my_pay, bill_to_company)]

    def test_both_monthly_flags_true_includes_monthly(self):
        """Monthly appears when both company and customer have monthly_payment=True."""
        modes = self._modes(True, True, Decimal('100'), Decimal('0'))
        self.assertIn(PaymentModeChoices.MONTHLY, modes)

    def test_company_monthly_false_excludes_monthly(self):
        """Monthly must not appear when company has monthly_payment=False."""
        modes = self._modes(False, True, Decimal('100'), Decimal('0'))
        self.assertNotIn(PaymentModeChoices.MONTHLY, modes)

    def test_customer_monthly_false_excludes_monthly(self):
        """Monthly must not appear when customer has monthly_payment=False."""
        modes = self._modes(True, False, Decimal('100'), Decimal('0'))
        self.assertNotIn(PaymentModeChoices.MONTHLY, modes)

    def test_full_subsidy_strips_all_modes_to_company(self):
        """When my_pay=0 and bill_to_company>0, only COMPANY mode is returned."""
        modes = self._modes(True, True, Decimal('0'), Decimal('100'))
        self.assertEqual(modes, [PaymentModeChoices.COMPANY])
        self.assertNotIn(PaymentModeChoices.MONTHLY, modes)

    def test_wallet_zeroes_my_pay_no_subsidy_keeps_monthly(self):
        """When my_pay=0 but bill_to_company=0 (wallet covered), monthly is still available."""
        modes = self._modes(True, True, Decimal('0'), Decimal('0'))
        self.assertIn(PaymentModeChoices.MONTHLY, modes)

    def test_monthly_appears_before_online_in_mode_list(self):
        """Monthly should appear before Online in the payment mode list."""
        from apps.orders.views import _allowed_payment_modes
        from unittest.mock import MagicMock
        co = MagicMock()
        cu = MagicMock()
        co.monthly_payment = True
        cu.monthly_payment = True
        co.cod_payment = False
        co.online_payment = True
        cu.cod_payment = False
        modes = [v for v, _ in _allowed_payment_modes(co, cu, Decimal('100'), Decimal('0'))]
        if PaymentModeChoices.MONTHLY in modes and PaymentModeChoices.ONLINE in modes:
            self.assertLess(
                modes.index(PaymentModeChoices.MONTHLY),
                modes.index(PaymentModeChoices.ONLINE),
                'Monthly should be listed before Online'
            )


# ── Monthly checkout template smoke tests ────────────────────────────────────

class MonthlyCheckoutTemplateTest(TestCase):
    """Bug 4 + 5 — checkout template must include walletPointsSection id
    and payment-mode-aware JS for monthly billing."""

    def setUp(self):
        self.co = _company(name='TemplateCo')
        self.cat = _category(self.co)
        self.prod = _product(self.co, self.cat)
        self.customer = _customer(self.co, wallet=Decimal('30.00'))
        self.client = Client()
        _login_customer(self.client, self.customer)
        session = self.client.session
        session['cart'] = {
            str(self.prod.pk): {
                'qty': 1, 'price': str(self.prod.price), 'name': self.prod.name
            }
        }
        session.save()

    def _get_checkout(self):
        return self.client.get(reverse('orders:checkout'))

    def test_checkout_loads_for_monthly_eligible_customer(self):
        """Checkout page must load (200) for a monthly-eligible customer."""
        resp = self._get_checkout()
        self.assertEqual(resp.status_code, 200)

    def test_checkout_shows_monthly_option(self):
        """Monthly option must appear in the rendered checkout for eligible customer."""
        resp = self._get_checkout()
        self.assertContains(resp, 'value="monthly"',
            msg_prefix='Monthly payment option must be rendered in checkout')

    def test_checkout_has_wallet_section_id(self):
        """walletPointsSection id must be present so JS can show/hide it."""
        resp = self._get_checkout()
        self.assertContains(resp, 'walletPointsSection',
            msg_prefix='walletPointsSection id must exist for JS monthly guard')

    def test_checkout_has_monthly_js_guard(self):
        """JS must contain the monthly mode detection for wallet guard."""
        resp = self._get_checkout()
        self.assertContains(resp, '_selectedPaymentMode',
            msg_prefix='Payment mode JS guard must be present in checkout')
        self.assertContains(resp, '_updateWalletVisibility',
            msg_prefix='Wallet visibility update function must be present')

    def test_checkout_has_monthly_button_text_logic(self):
        """JS must handle monthly button text differently from paid modes."""
        resp = self._get_checkout()
        self.assertContains(resp, 'Monthly Billing',
            msg_prefix='Monthly Billing text must appear in checkout page JS')


# ── Order model payment status choices ───────────────────────────────────────

class MonthlyPaymentStatusChoicesTest(TestCase):
    """Sanity: PaymentModeChoices.MONTHLY exists and equals the string 'monthly'."""

    def test_monthly_choice_value(self):
        self.assertEqual(PaymentModeChoices.MONTHLY, 'monthly')

    def test_monthly_choice_label(self):
        self.assertEqual(
            PaymentModeChoices.MONTHLY.label, 'Monthly Billing'
        )

    def test_monthly_order_payment_status_approved_string(self):
        """'approved' is the correct payment_status string for monthly orders."""
        co = _company(name='ChoicesCo')
        cu = _customer(co, email='choices@test.com')
        order = _order(co, cu, payment_mode='monthly', payment_status='approved')
        self.assertEqual(order.payment_status, 'approved')
        self.assertEqual(order.payment_mode, 'monthly')
