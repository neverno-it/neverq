"""
NeverQ — Audit Regression Tests
=================================
Covers the 5 confirmed regressions found in the ZIP audit:

  A. company_cafes missing from home page context
  B. web_qty not readable/saveable via dashboard product form
  C. dashboard_offer_add NameError on image upload (structural test)
  D. reorder_order respects web_qty cap
  E. _get_web_max_qty uniqueness (no duplicate definition)

These tests are additive — they do not touch existing test logic.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from apps.core.models import Company
from apps.accounts.models import Customer, StaffUser
from apps.menu.models import (
    Product, Category, Offering, Offer, Cafe,
)
from apps.orders.models import Order, OrderItem


# ── Shared factories ─────────────────────────────────────────────────────────

def _company(name='AuditCo'):
    return Company.objects.create(
        name=name,
        order_open_days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],
        online_payment=True,
        cod_payment=True,
        store_status=True,
    )


def _category(company, name='Meals'):
    cat = Category.objects.create(
        name=name,
        slug=name.lower(),
        is_active=True,
        is_deleted=False,
    )
    cat.companies.add(company)
    return cat


def _product(company, category, name='Thali', price=100, web_qty=-1, max_qty=10, pos_qty=5):
    return Product.objects.create(
        company=company,
        category=category,
        name=name,
        slug=name.lower().replace(' ', '-'),
        price=Decimal(str(price)),
        is_active=True,
        is_deleted=False,
        web_qty=web_qty,
        max_qty=max_qty,
        pos_qty=pos_qty,
        min_qty=1,
    )


def _customer(company, email='cust@audit.test'):
    return Customer.objects.create(
        company=company,
        name='Audit Customer',
        email=email,
        phone='9000000001',
        is_active=True,
        is_deleted=False,
        is_approved=True,
        is_email_verified=True,
    )


def _staff(company, role='admin', username='auditstaff'):
    email = f'{username}@audit.test'
    s = StaffUser.objects.create(email=email, company=company, role=role, is_active=True)
    s.set_password('auditpass')
    s.save()
    return s


def _login_customer(client, customer):
    session = client.session
    session['customer_id'] = customer.pk
    session.save()


# ── A. company_cafes in home page context ────────────────────────────────────

class HomeCafesContextTest(TestCase):
    """Regression: customer_menu must pass company_cafes to home template."""

    def setUp(self):
        self.co = _company('CafeCo')
        self.cat = _category(self.co)
        self.customer = _customer(self.co)
        self.client = Client()
        _login_customer(self.client, self.customer)

    def test_company_cafes_in_context_single(self):
        """Single cafe: company_cafes present, picker hidden (length <= 1)."""
        Cafe.objects.create(company=self.co, name='Main Cafe', is_active=True, is_deleted=False)
        resp = self.client.get(reverse('menu:menu'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('company_cafes', resp.context,
            'company_cafes must be in home template context')
        self.assertIsInstance(resp.context['company_cafes'], list)

    def test_company_cafes_in_context_multi(self):
        """Multi-cafe: company_cafes has both cafes — picker can render."""
        Cafe.objects.create(company=self.co, name='Cafe A', is_active=True, is_deleted=False)
        Cafe.objects.create(company=self.co, name='Cafe B', is_active=True, is_deleted=False)
        resp = self.client.get(reverse('menu:menu'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('company_cafes', resp.context)
        self.assertEqual(len(resp.context['company_cafes']), 2,
            'Both cafes must appear in home context so the picker can render')

    def test_selected_cafe_id_in_context(self):
        """selected_cafe_id key must always be present (None if nothing selected)."""
        resp = self.client.get(reverse('menu:menu'))
        self.assertIn('selected_cafe_id', resp.context,
            'selected_cafe_id must be in home context')


# ── B. web_qty saveable via dashboard product form ────────────────────────────

class WebQtyProductFormTest(TestCase):
    """Regression: _save_product must read + persist web_qty from POST."""

    def setUp(self):
        self.co = _company('FormCo')
        self.cat = _category(self.co)
        self.superadmin = _staff(self.co, role='superadmin', username='sadmin_wq')
        self.client = Client()
        self.client.force_login(self.superadmin)

    def _post_product(self, extra=None):
        data = {
            'name': 'Test Product',
            'price': '80',
            'company_price': '0',
            'packing_price': '0',
            'min_qty': '1',
            'max_qty': '10',
            'web_qty': '3',
            'pos_qty': '5',
            'position_order': '0',
            'preparation_time_minutes': '10',
            'category': self.cat.pk,
            'company': self.co.pk,
            'is_active': 'on',
        }
        if extra:
            data.update(extra)
        return self.client.post(reverse('dashboard:product_add'), data)

    def test_web_qty_field_exists_in_form_response(self):
        """GET product form must render a web_qty input field."""
        resp = self.client.get(reverse('dashboard:product_add'))
        self.assertContains(resp, 'name="web_qty"',
            msg_prefix='Product form must have a web_qty input')

    def test_edit_form_displays_zero_web_qty_without_converting_to_unlimited(self):
        """A saved web_qty=0 must render as 0, not the -1 default."""
        product = _product(self.co, self.cat, name='Sold Out Edit Product', web_qty=0, pos_qty=100)
        resp = self.client.get(reverse('dashboard:product_edit', kwargs={'pk': product.pk}))

        self.assertContains(resp, 'name="web_qty" class="form-control" min="-1" value="0"', html=False)
        self.assertNotContains(resp, 'name="web_qty" class="form-control" min="-1" value="-1"', html=False)

    def test_edit_form_displays_saved_calories(self):
        """Saved calorie values must appear in the edit form."""
        product = _product(self.co, self.cat, name='Dal Fry Edit Product', web_qty=0, pos_qty=100)
        product.calories = 240
        product.save(update_fields=['calories'])
        resp = self.client.get(reverse('dashboard:product_edit', kwargs={'pk': product.pk}))

        self.assertContains(resp, 'name="calories" id="caloriesInput" class="form-control" min="0" value="240"', html=False)

    def test_web_qty_saved_on_add(self):
        """POST with web_qty=3 must persist web_qty=3 on the created product."""
        resp = self._post_product({'web_qty': '3'})
        self.assertRedirects(resp, reverse('dashboard:product_list'))
        product = Product.objects.filter(company=self.co, name='Test Product').first()
        self.assertIsNotNone(product, 'Product should have been created')
        self.assertEqual(product.web_qty, 3,
            'web_qty must be saved from POST, not left at default -1')

    def test_web_qty_unlimited_saved(self):
        """web_qty=-1 (unlimited) round-trips correctly."""
        self._post_product({'web_qty': '-1', 'name': 'Unlimited Product'})
        product = Product.objects.filter(company=self.co, name='Unlimited Product').first()
        self.assertIsNotNone(product)
        self.assertEqual(product.web_qty, -1)

    def test_web_qty_zero_sold_out(self):
        """web_qty=0 (sold-out) round-trips correctly."""
        self._post_product({'web_qty': '0', 'name': 'Sold Out Product'})
        product = Product.objects.filter(company=self.co, name='Sold Out Product').first()
        self.assertIsNotNone(product)
        self.assertEqual(product.web_qty, 0)

    def test_web_qty_saved_on_edit(self):
        """Editing an existing product must update web_qty."""
        product = _product(self.co, self.cat, name='Edit Me', web_qty=-1)
        data = {
            'name': 'Edit Me',
            'price': '80',
            'company_price': '0',
            'packing_price': '0',
            'min_qty': '1',
            'max_qty': '10',
            'web_qty': '7',
            'pos_qty': '0',
            'position_order': '0',
            'preparation_time_minutes': '10',
            'category': self.cat.pk,
            'company': self.co.pk,
            'is_active': 'on',
        }
        resp = self.client.post(reverse('dashboard:product_edit', kwargs={'pk': product.pk}), data)
        self.assertRedirects(resp, reverse('dashboard:product_list'))
        product.refresh_from_db()
        self.assertEqual(product.web_qty, 7,
            'web_qty must be updated when editing a product via the dashboard')


# ── C. dashboard_offer_add — structural test for NameError guard ─────────────

class OfferAddNoImageTest(TestCase):
    """
    The NameError crash in dashboard_offer_add only fires when an image file
    is uploaded. We verify the no-image POST path (the common case) works
    cleanly. A full image-upload test would need live file handling.
    """

    def setUp(self):
        self.co = _company('OfferCo')
        self.cat = _category(self.co)
        self.superadmin = _staff(self.co, role='superadmin', username='sadmin_oa')
        self.client = Client()
        self.client.force_login(self.superadmin)

    def test_offer_add_without_image_succeeds(self):
        """Creating an offer without an image must not raise NameError."""
        data = {
            'company': self.co.pk,
            'title': 'Audit Offer',
            'offer_type': 'percent',
            'value': '10',
            'is_active': 'on',
            'product_scope': 'none',
        }
        resp = self.client.post(reverse('dashboard:offer_add'), data)
        self.assertRedirects(resp, reverse('dashboard:offer_list'),
            msg_prefix='Offer add (no image) must succeed without NameError')

    def test_offer_add_get_loads(self):
        """GET offer add form must load without error."""
        resp = self.client.get(reverse('dashboard:offer_add'))
        self.assertEqual(resp.status_code, 200)


# ── D. reorder_order respects web_qty cap ────────────────────────────────────

class ReorderWebQtyCapTest(TestCase):
    """Regression: reorder_order must use _get_web_max_qty, not max_qty."""

    def setUp(self):
        self.co = _company('ReorderCo')
        self.co.store_status = True
        self.co.save(update_fields=['store_status'])
        self.cat = _category(self.co)
        self.customer = _customer(self.co, email='reorder@audit.test')
        self.client = Client()
        _login_customer(self.client, self.customer)

    def _make_order(self, product, qty):
        from apps.orders.models import OrderStatusChoices
        order = Order.objects.create(
            company=self.co,
            customer=self.customer,
            order_number='WEB-9999',
            order_status=OrderStatusChoices.DELIVERED,
            payment_mode='cash',
            payment_status='paid',
            subtotal=product.price * qty,
            total_amount=product.price * qty,
            my_pay=product.price * qty,
        )
        OrderItem.objects.create(
            order=order,
            company=self.co,
            product=product,
            qty=qty,
            unit_price=product.price,
            price=product.price * qty,
        )
        return order

    def test_reorder_honours_web_qty_cap(self):
        """
        Product: web_qty=2, max_qty=10.
        Reorder of qty=5 must be capped to 2 (web_qty), not 10 (max_qty).
        """
        product = _product(self.co, self.cat, name='Capped Thali',
                           web_qty=2, max_qty=10, pos_qty=0)
        order = self._make_order(product, qty=5)

        resp = self.client.post(
            reverse('orders:reorder_order', kwargs={'pk': order.pk})
        )
        # Either redirects to cart or shows warning — either way no 500
        self.assertIn(resp.status_code, [200, 302],
            'reorder must not 500 when web_qty < requested qty')

        cart = self.client.session.get('cart', {})
        key = str(product.pk)
        if key in cart:
            qty_in_cart = int(cart[key].get('qty', 0))
            self.assertLessEqual(qty_in_cart, 2,
                f'Cart qty ({qty_in_cart}) must not exceed web_qty cap (2)')

    def test_reorder_zero_web_qty_skips_product(self):
        """web_qty=0 means sold out — product must be skipped on reorder."""
        product = _product(self.co, self.cat, name='Sold Out Item',
                           web_qty=0, max_qty=10, pos_qty=0)
        order = self._make_order(product, qty=1)

        self.client.post(reverse('orders:reorder_order', kwargs={'pk': order.pk}))
        cart = self.client.session.get('cart', {})
        self.assertNotIn(str(product.pk), cart,
            'Sold-out product (web_qty=0) must not appear in cart on reorder')


# ── E. _get_web_max_qty defined exactly once ──────────────────────────────────

class WebQtyFunctionUniquenessTest(TestCase):
    """Regression: duplicate function definition must not exist in menu/views.py."""

    def test_get_web_max_qty_defined_once(self):
        import ast, inspect
        import apps.menu.views as mv
        src = inspect.getsource(mv)
        tree = ast.parse(src)
        fn_defs = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == '_get_web_max_qty'
        ]
        self.assertEqual(len(fn_defs), 1,
            f'_get_web_max_qty must be defined exactly once, found {len(fn_defs)} definitions')

    def test_get_web_max_qty_logic_web_qty_takes_priority(self):
        """web_qty >= 0 must be used as cap; max_qty is only fallback."""
        from apps.menu.views import _get_web_max_qty
        from unittest.mock import MagicMock
        p = MagicMock()
        p.web_qty = 3
        p.max_qty = 999
        self.assertEqual(_get_web_max_qty(p), 3,
            'web_qty=3 must take priority over max_qty=999')

    def test_get_web_max_qty_fallback_to_max_qty(self):
        """web_qty=-1 (unlimited) falls back to max_qty when set."""
        from apps.menu.views import _get_web_max_qty
        from unittest.mock import MagicMock
        p = MagicMock()
        p.web_qty = -1
        p.max_qty = 15
        self.assertEqual(_get_web_max_qty(p), 15,
            'web_qty=-1 must fall back to max_qty=15')

    def test_get_web_max_qty_zero_means_sold_out(self):
        """web_qty=0 must return 0, treated as sold out (not fall through to max_qty)."""
        from apps.menu.views import _get_web_max_qty
        from unittest.mock import MagicMock
        p = MagicMock()
        p.web_qty = 0
        p.max_qty = 20
        self.assertEqual(_get_web_max_qty(p), 0,
            'web_qty=0 must return 0 (sold out), not fall back to max_qty')
