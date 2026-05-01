"""
Test: Kiosk UI configuration — hero_image, card_style, show/hide toggles.
"""
from django.test import TestCase, Client
from django.urls import reverse

from apps.core.models import Company, KioskConfig, Building
from apps.accounts.models import StaffUser
from apps.menu.models import Category, Offering, OfferingGallery, Product


def _co():
    return Company.objects.create(
        name='UICo', store_status=True,
        kiosk_theme_color='#c62828',
        kiosk_welcome_text='Test Kiosk',
        order_open_days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],
    )


def _staff(co, role='superadmin'):
    s = StaffUser.objects.create(
        email=f'{role}_{co.pk}@t.com', company=co, role=role, is_active=True
    )
    s.set_password('pass'); s.save()
    return s


class KioskConfigModelTest(TestCase):

    def setUp(self):
        self.co = _co()

    def test_effective_theme_color_from_company(self):
        cfg = KioskConfig(company=self.co, name='Test', theme_color='')
        self.assertEqual(cfg.effective_theme_color, self.co.kiosk_theme_color)

    def test_effective_theme_color_override(self):
        cfg = KioskConfig(company=self.co, name='Test', theme_color='#2e7d32')
        self.assertEqual(cfg.effective_theme_color, '#2e7d32')

    def test_effective_welcome_title_from_company(self):
        cfg = KioskConfig(company=self.co, name='Test', welcome_title='')
        self.assertEqual(cfg.effective_welcome_title, self.co.name)

    def test_effective_welcome_subtitle_from_company(self):
        cfg = KioskConfig(company=self.co, name='Test', welcome_subtitle='')
        self.assertEqual(cfg.effective_welcome_subtitle, self.co.kiosk_welcome_text)

    def test_show_offerings_default_true(self):
        cfg = KioskConfig.objects.create(company=self.co, name='TestConfig')
        self.assertTrue(cfg.show_offerings)
        self.assertTrue(cfg.show_categories)

    def test_card_style_choices(self):
        for style in ('standard', 'compact', 'large'):
            cfg = KioskConfig(company=self.co, name='T', card_style=style)
            self.assertEqual(cfg.card_style, style)

    def test_slug_auto_generated(self):
        cfg = KioskConfig.objects.create(company=self.co, name='My Kiosk')
        self.assertTrue(len(cfg.slug) > 0)
        self.assertIn('kiosk', cfg.slug.lower())


class KioskTemplateRenderTest(TestCase):

    def setUp(self):
        self.co = _co()
        self.client = Client()

    def test_kiosk_home_loads(self):
        resp = self.client.get(reverse('orders:kiosk_home', kwargs={'company_id': self.co.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_hero_image_section_absent_without_config(self):
        resp = self.client.get(reverse('orders:kiosk_home', kwargs={'company_id': self.co.pk}))
        content = resp.content.decode()
        # hero_image block only renders when kiosk_cfg has a hero_image
        self.assertNotIn('hero_image', content.lower().replace(' ', '_') + '_not_literally_in_page')

    def test_card_style_default_no_cs_class_on_grid(self):
        resp = self.client.get(reverse('orders:kiosk_home', kwargs={'company_id': self.co.pk}))
        content = resp.content.decode()
        # CSS class definitions exist in stylesheet, but grid div must NOT have cs-* applied
        # Template only applies cs-compact/cs-large inside the conditional: kiosk_cfg.card_style
        # Without a kiosk_cfg the class attr is empty — check the row div doesn't carry it
        import re
        # Find actual class= on row g-3 divs
        row_divs = re.findall(r'class="row g-3([^"]*)"', content)
        for cls in row_divs:
            self.assertNotIn('cs-compact', cls)
            self.assertNotIn('cs-large', cls)

    def test_kiosk_slug_param_loads(self):
        cfg = KioskConfig.objects.create(
            company=self.co, name='Entrance',
            theme_color='#2e7d32', show_offerings=False,
        )
        url = reverse('orders:kiosk_home', kwargs={'company_id': self.co.pk})
        resp = self.client.get(url + f'?kiosk={cfg.slug}')
        self.assertEqual(resp.status_code, 200)

    def test_featured_products_render_on_default_kiosk_home(self):
        category = Category.objects.create(
            name='Combos',
            slug='combos',
            open_days=[],
            is_active=True,
            is_deleted=False,
        )
        category.companies.add(self.co)
        featured = Product.objects.create(
            company=self.co,
            category=category,
            name='Featured Combo',
            slug='featured-combo',
            price='99.00',
            is_active=True,
            is_kiosk_active=True,
            featured_in_kiosk_extra=True,
            is_deleted=False,
        )

        resp = self.client.get(reverse('orders:kiosk_home', kwargs={'company_id': self.co.pk}))

        self.assertEqual(resp.status_code, 200)
        self.assertIn(featured.pk, [product.pk for product in resp.context['featured_products']])
        self.assertContains(resp, 'featured-grid-single')

    def test_calorie_filter_limits_visible_products(self):
        category = Category.objects.create(
            name='Meals',
            slug='meals',
            open_days=[],
            is_active=True,
            is_deleted=False,
        )
        category.companies.add(self.co)
        light = Product.objects.create(
            company=self.co,
            category=category,
            name='Light Meal',
            slug='light-meal',
            price='80.00',
            calories=320,
            is_active=True,
            is_kiosk_active=True,
            is_deleted=False,
        )
        Product.objects.create(
            company=self.co,
            category=category,
            name='Heavy Meal',
            slug='heavy-meal',
            price='120.00',
            calories=620,
            is_active=True,
            is_kiosk_active=True,
            is_deleted=False,
        )

        resp = self.client.get(
            reverse('orders:kiosk_home', kwargs={'company_id': self.co.pk}) + '?calorie_max=400'
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['kiosk_calorie_max'], 400)
        self.assertEqual([product.pk for product in resp.context['browse_products']], [light.pk])

    def test_show_offerings_false_hides_strip(self):
        from apps.menu.models import Offering
        Offering.objects.create(company=self.co, name='Lunch', is_active=True)
        cfg = KioskConfig.objects.create(
            company=self.co, name='NoOff', show_offerings=False,
        )
        url = reverse('orders:kiosk_home', kwargs={'company_id': self.co.pk})
        resp = self.client.get(url + f'?kiosk={cfg.slug}')
        content = resp.content.decode()
        # The <div id="offeringStrip"> HTML element must be absent.
        # Note: the tour widget JS always references '#offeringStrip' in its
        # selector string — we check for the HTML id attribute specifically.
        self.assertNotIn('id="offeringStrip"', content,
            'Offering strip <div> must not render when show_offerings=False')


class SuperadminPermissionHTTPTest(TestCase):
    """Verify superadmin-only hierarchy views block non-superadmin via HTTP."""

    def setUp(self):
        self.co = _co()
        self.superadmin = _staff(self.co, 'superadmin')
        self.admin = _staff(self.co, 'admin')
        self.client = Client()

    def _login(self, user):
        self.client.login(username=user.email, password='pass')

    def test_superadmin_reaches_offering_list(self):
        self._login(self.superadmin)
        resp = self.client.get(reverse('dashboard:offering_list'))
        self.assertIn(resp.status_code, [200, 302])
        # 302 is ok if it goes to dashboard home, not login
        if resp.status_code == 302:
            self.assertNotIn('/login/', resp['Location'])

    def test_admin_reaches_offering_list(self):
        self._login(self.admin)
        resp = self.client.get(reverse('dashboard:offering_list'))
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_create_offering_from_gallery_image(self):
        gallery = OfferingGallery.objects.create(
            company=self.co,
            name='Lunch Hero',
            image='offering_gallery/lunch-hero.png',
        )
        self._login(self.admin)
        resp = self.client.post(reverse('dashboard:offering_add'), {
            'name': 'Lunch',
            'position_order': '0',
            'is_active': 'on',
            'gallery_image_url': gallery.image.url,
        })
        self.assertRedirects(resp, reverse('dashboard:offering_list'))
        offering = Offering.objects.get(company=self.co, name='Lunch')
        self.assertEqual(offering.image.name, gallery.image.name)

    def test_admin_blocked_from_counter_add(self):
        self._login(self.admin)
        resp = self.client.get(reverse('dashboard:counter_add'))
        self.assertIn(resp.status_code, [302, 403])

    def test_admin_allowed_on_category_list(self):
        # category_list allows admin — @staff_role_required('superadmin','admin','pos')
        self._login(self.admin)
        resp = self.client.get(reverse('dashboard:category_list'))
        self.assertEqual(resp.status_code, 200,
            'Admin should reach category_list (not blocked — decorator allows admin+pos)')

    def test_admin_blocked_from_company_store_toggle(self):
        self._login(self.admin)
        resp = self.client.post(
            reverse('dashboard:company_store_toggle', kwargs={'pk': self.co.pk}),
        )
        self.assertIn(resp.status_code, [302, 403])

    def test_superadmin_can_access_hierarchy(self):
        self._login(self.superadmin)
        resp = self.client.get(reverse('dashboard:hierarchy'))
        self.assertIn(resp.status_code, [200, 302])
        if resp.status_code == 302:
            self.assertNotIn('/login/', resp['Location'])
