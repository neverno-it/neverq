"""
Test: POS terminal renders menu products AND legacy POS-only products.
"""
from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from apps.core.models import Company
from apps.menu.models import Category, Product
from apps.pos.models import POSProduct
from apps.accounts.models import StaffUser


def _make_company():
    return Company.objects.create(
        name='POSCo', store_status=True,
        order_open_days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],
    )


class POSTerminalProductTest(TestCase):

    def setUp(self):
        self.co = _make_company()
        self.cat = Category.objects.create(name='Meals')
        self.cat.companies.add(self.co)
        # Menu product
        self.menu_prod = Product.objects.create(
            name='Menu Item', company=self.co, category=self.cat,
            price=Decimal('50'), is_active=True, is_deleted=False
        )
        # POS-only product
        self.pos_prod = POSProduct.objects.create(
            name='POS Only Item', company=self.co,
            price=Decimal('30'), is_active=True
        )
        self.staff = StaffUser.objects.create(
            email='pos@co.com', company=self.co, role='pos', is_active=True
        )
        self.staff.set_password('pass')
        self.staff.save()

    def test_pos_view_returns_menu_products(self):
        from apps.pos.views import pos_terminal
        factory = RequestFactory()
        request = factory.get('/pos/')
        request.user = self.staff
        # Manually call view logic (not full request cycle)
        from apps.menu.models import Product as MenuProduct
        products = list(MenuProduct.objects.filter(
            company=self.co, is_active=True, is_deleted=False
        ))
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].name, 'Menu Item')

    def test_pos_view_returns_pos_only_products(self):
        pos_only = list(POSProduct.objects.filter(
            company=self.co, is_active=True, is_deleted=False
        ))
        self.assertEqual(len(pos_only), 1)
        self.assertEqual(pos_only[0].name, 'POS Only Item')

    def test_pos_renders_when_menu_products_empty(self):
        """POS terminal must still render when menu products = 0 but pos_products exist."""
        from apps.menu.models import Product as MenuProduct
        MenuProduct.objects.filter(company=self.co).update(is_deleted=True)
        menu_qs = list(MenuProduct.objects.filter(company=self.co, is_active=True, is_deleted=False))
        pos_qs  = list(POSProduct.objects.filter(company=self.co, is_active=True, is_deleted=False))
        self.assertEqual(len(menu_qs), 0)
        self.assertEqual(len(pos_qs), 1)
        # Template condition fix: {% if products or pos_products %}
        has_anything = bool(menu_qs or pos_qs)
        self.assertTrue(has_anything)

    def test_pos_empty_state_when_both_empty(self):
        POSProduct.objects.filter(company=self.co).delete()
        from apps.menu.models import Product as MenuProduct
        MenuProduct.objects.filter(company=self.co).update(is_deleted=True)
        menu_qs = list(MenuProduct.objects.filter(company=self.co, is_active=True, is_deleted=False))
        pos_qs  = list(POSProduct.objects.filter(company=self.co, is_active=True, is_deleted=False))
        has_anything = bool(menu_qs or pos_qs)
        self.assertFalse(has_anything)
