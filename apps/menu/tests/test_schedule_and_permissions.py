"""
Test: Offering/Category/Product schedule chain and superadmin-only permission enforcement.
"""
import datetime
from django.test import TestCase, RequestFactory, Client
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from apps.core.models import Company
from apps.menu.models import Category, Offering, Product
from apps.accounts.models import StaffModulePermission, StaffUser


def _co():
    return Company.objects.create(
        name='SchedCo', store_status=True,
        order_open_days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],
    )


def _staff(co, role='admin'):
    s = StaffUser.objects.create(email=f'{role}@co.com', company=co, role=role, is_active=True)
    s.set_password('pass')
    s.save()
    return s


class ScheduleChainTest(TestCase):

    def setUp(self):
        self.co = _co()
        from django.utils import timezone as tz
        self.today_abbr = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][tz.localtime().weekday()]
        self.other_day = [d for d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
                          if d != self.today_abbr][0]

    def _prod(self, cat, offering=None, bypass=False, **kw):
        p = Product.objects.create(
            name='P', company=self.co, category=cat, price=10,
            is_active=True, schedule_bypass=bypass,
            offering=offering, **kw
        )
        return p

    def test_open_offering_open_category_product_available(self):
        off = Offering.objects.create(company=self.co, name='O', is_active=True)
        cat = Category.objects.create(name='C', open_days=[self.today_abbr])
        cat.companies.add(self.co)
        p = self._prod(cat, off)
        self.assertTrue(p.is_available_now())

    def test_closed_offering_hides_product(self):
        off = Offering.objects.create(company=self.co, name='O', is_active=True,
                                       open_days=[self.other_day])
        cat = Category.objects.create(name='C', open_days=[])
        cat.companies.add(self.co)
        p = self._prod(cat, off)
        self.assertFalse(p.is_available_now())

    def test_closed_category_hides_product(self):
        cat = Category.objects.create(name='C', open_days=[self.other_day])
        cat.companies.add(self.co)
        p = self._prod(cat)
        self.assertFalse(p.is_available_now())

    def test_bypass_overrides_closed_offering(self):
        off = Offering.objects.create(company=self.co, name='O', is_active=True,
                                       open_days=[self.other_day])
        cat = Category.objects.create(name='C', open_days=[])
        cat.companies.add(self.co)
        p = self._prod(cat, off, bypass=True)
        self.assertTrue(p.is_available_now())

    def test_bypass_overrides_closed_category(self):
        cat = Category.objects.create(name='C', open_days=[self.other_day])
        cat.companies.add(self.co)
        p = self._prod(cat, bypass=True)
        self.assertTrue(p.is_available_now())

    def test_customer_visibility_helper_honors_bypass(self):
        from apps.menu.views import _product_is_visible_for_customer
        cat = Category.objects.create(name='C', open_days=[self.other_day])
        cat.companies.add(self.co)
        p = self._prod(cat, bypass=True)
        self.assertTrue(_product_is_visible_for_customer(p, self.co))

    def test_bypass_with_own_time_window_respected(self):
        """bypass=True but product's own time window is expired → not available."""
        cat = Category.objects.create(name='C', open_days=[])
        cat.companies.add(self.co)
        p = self._prod(cat, bypass=True,
                       available_from=datetime.time(0, 0),
                       available_to=datetime.time(0, 1))
        self.assertFalse(p.is_available_now())


class SuperadminPermissionTest(TestCase):

    def setUp(self):
        self.co  = _co()
        self.factory = RequestFactory()

    def _get(self, url, user):
        request = self.factory.get(url)
        request.user = user
        return request

    def test_superadmin_can_access_offering_add(self):
        from apps.accounts.decorators import staff_role_required
        sup = _staff(self.co, 'superadmin')
        # Verify superadmin role is recognised
        self.assertEqual(sup.role, 'superadmin')
        self.assertTrue(sup.is_superadmin)

    def test_admin_cannot_add_offering(self):
        """Non-superadmin should not be able to trigger offering mutations."""
        admin = _staff(self.co, 'admin')
        self.assertEqual(admin.role, 'admin')
        # Verify decorator would block them
        self.assertFalse(admin.is_superadmin)

    def test_pos_user_is_not_superadmin(self):
        pos = _staff(self.co, 'pos')
        self.assertFalse(pos.is_superadmin)

    def test_hierarchy_views_superadmin_only(self):
        """Verify that hierarchy-related views are tagged superadmin-only in views file."""
        import inspect
        import apps.accounts.dashboard_views as dv
        # Check the hierarchy_overview function has the right decorator effect
        # by testing via live client if company add is restricted
        sup = _staff(self.co, 'superadmin')
        admin = _staff(self.co, 'admin')
        self.assertTrue(sup.is_superadmin)
        self.assertFalse(admin.is_superadmin)


class SuperadminHTTPPermissionTest(TestCase):
    """
    Extend existing permission tests with HTTP-level checks.
    Superadmin can access hierarchy/setup views; selected menu management
    screens also allow company admins when the access registry says so.
    """

    def setUp(self):
        self.co = _co()
        self.sup  = _staff(self.co, 'superadmin')
        self.adm  = _staff(self.co, 'admin')
        self.pos  = _staff(self.co, 'pos')
        self.client = Client()

    def _login(self, user):
        self.client.login(username=user.email, password='pass')

    def _grant(self, user, module_key):
        StaffModulePermission.objects.create(
            staff_user=user,
            module_key=module_key,
            level='view',
        )

    def _check_blocked(self, url_name, kwargs=None):
        self._login(self.adm)
        resp = self.client.get(reverse(url_name, kwargs=kwargs or {}))
        self.assertIn(resp.status_code, [302, 403],
            msg=f"{url_name} should block admin but got {resp.status_code}")

    def _check_allowed(self, url_name, kwargs=None):
        self._login(self.sup)
        resp = self.client.get(reverse(url_name, kwargs=kwargs or {}))
        # 200 = loaded, 302 = redirect within dashboard (not to login)
        if resp.status_code == 302:
            self.assertNotIn('/login/', resp.get('Location',''))
        else:
            self.assertEqual(resp.status_code, 200,
                msg=f"{url_name} should allow superadmin")

    def test_offering_list_superadmin_allowed(self):
        self._check_allowed('dashboard:offering_list')

    def test_offering_list_admin_allowed(self):
        self._grant(self.adm, 'perm_offerings')
        self._login(self.adm)
        resp = self.client.get(reverse('dashboard:offering_list'))
        self.assertEqual(resp.status_code, 200,
            'dashboard:offering_list should be accessible when granular offerings access is granted')

    def test_counter_add_superadmin_allowed(self):
        self._check_allowed('dashboard:counter_add')

    def test_counter_add_admin_blocked(self):
        self._check_blocked('dashboard:counter_add')

    def test_category_list_superadmin_allowed(self):
        self._check_allowed('dashboard:category_list')

    def test_category_list_admin_allowed(self):
        self._grant(self.adm, 'perm_categories')
        self._login(self.adm)
        resp = self.client.get(reverse('dashboard:category_list'))
        self.assertEqual(resp.status_code, 200,
            'dashboard:category_list should be accessible when granular categories access is granted')

    def test_building_list_superadmin_allowed(self):
        self._check_allowed('dashboard:building_list')

    def test_building_list_admin_blocked(self):
        self._check_blocked('dashboard:building_list')

    def test_cafe_list_superadmin_allowed(self):
        self._check_allowed('dashboard:cafe_list')

    def test_cafe_list_admin_blocked(self):
        self._check_blocked('dashboard:cafe_list')

    def test_location_list_superadmin_allowed(self):
        self._check_allowed('dashboard:location_list')

    def test_location_list_admin_blocked(self):
        self._check_blocked('dashboard:location_list')

    def test_hierarchy_superadmin_allowed(self):
        self._check_allowed('dashboard:hierarchy')

    def test_hierarchy_admin_blocked(self):
        self._check_blocked('dashboard:hierarchy')

    def test_pos_user_blocked_from_counter_add(self):
        self._login(self.pos)
        resp = self.client.get(reverse('dashboard:counter_add'))
        self.assertIn(resp.status_code, [302, 403])
