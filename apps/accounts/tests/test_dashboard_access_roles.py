import re
from pathlib import Path

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import StaffAccess, StaffModulePermission, StaffUser
from apps.core.access import (
    ACTION_REGISTRY,
    FIELD_HTML_NAMES,
    get_allowed_keys,
    get_locked_html_names,
    get_route_to_key_map,
    get_safe_landing_url,
)
from apps.core.models import Company
from apps.menu.models import Category, Counter, Product, ProductCounter


class DashboardAccessRoleTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='AccessCo',
            store_status=True,
            online_payment=True,
        )
        self.admin = self._staff('admin@test.com', 'admin')
        self.pos = self._staff('pos@test.com', 'pos')
        self.cafeman = self._staff('cafeman@test.com', 'cafeman')
        self.reports = self._staff('reports@test.com', 'reports')

    def _staff(self, email, role):
        user = StaffUser.objects.create(
            email=email,
            name=role.title(),
            role=role,
            company=self.company,
            is_active=True,
            is_staff=True,
        )
        user.set_password('testpass123')
        user.save()
        user.site_access.add(self.company)
        return user

    def _get_as(self, user, url_name):
        client = Client()
        client.force_login(user)
        return client.get(reverse(url_name))

    def _grant(self, user, module_key, level='view', actions=None):
        return StaffModulePermission.objects.create(
            staff_user=user,
            module_key=module_key,
            level=level,
            allowed_actions=actions or [],
        )

    def _product(self, name='Access Product'):
        category = Category.objects.create(name=f'{name} Category')
        category.companies.add(self.company)
        return Product.objects.create(
            name=name,
            company=self.company,
            category=category,
            price=10,
            web_qty=5,
            pos_qty=5,
            is_active=True,
            is_deleted=False,
        )

    def test_user_without_matrix_has_no_dashboard_module_access(self):
        response = self._get_as(self.admin, 'dashboard:product_list')
        home_response = self._get_as(self.admin, 'dashboard:home')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:no_access'))
        self.assertEqual(home_response.status_code, 302)
        self.assertEqual(home_response.url, reverse('dashboard:no_access'))

    def test_legacy_access_row_does_not_grant_actual_route_access(self):
        StaffAccess.objects.create(
            user=self.admin,
            landing_page='dashboard:home',
            visible_keys=['dashboard', 'products', 'orders'],
        )

        response = self._get_as(self.admin, 'dashboard:product_list')

        self.assertEqual(get_allowed_keys(self.admin), set())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:no_access'))

    def test_admin_can_access_product_list(self):
        self._grant(self.admin, 'perm_products')
        response = self._get_as(self.admin, 'dashboard:product_list')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_safe_landing_url(self.admin), 'dashboard:product_list')

    def test_admin_role_label_is_operation_manager(self):
        self.assertEqual(self.admin.get_role_display(), 'Operation Manager')

    def test_product_view_only_hides_ungranted_sidebar_and_actions(self):
        self._grant(self.admin, 'perm_products')
        response = self._get_as(self.admin, 'dashboard:product_list')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['lp']['add'])
        self.assertFalse(response.context['can_manage_products'])
        self.assertContains(response, 'No products are available for your current scope.')
        self.assertNotContains(response, 'Add Product')
        self.assertNotContains(response, 'Delete Selected')
        self.assertNotContains(response, 'Media & Scheduling')
        self.assertNotContains(response, 'Add your first product')

    def test_product_view_only_blocks_mutating_product_endpoints(self):
        product = self._product()
        self._grant(self.admin, 'perm_products')
        client = Client()
        client.force_login(self.admin)

        edit_response = client.get(reverse('dashboard:product_edit', args=[product.pk]))
        delete_response = client.post(reverse('dashboard:product_delete', args=[product.pk]))
        bulk_delete_response = client.post(
            reverse('dashboard:product_bulk_delete'),
            {'ids': [product.pk]},
        )
        qty_response = client.post(
            reverse('dashboard:product_update_qty', args=[product.pk]),
            {'web_qty': '0'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        reorder_response = client.post(
            reverse('dashboard:product_reorder'),
            data=f'{{"ids":[{product.pk}]}}',
            content_type='application/json',
        )

        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(edit_response.url, reverse('dashboard:no_access'))
        self.assertEqual(delete_response.status_code, 302)
        self.assertEqual(delete_response.url, reverse('dashboard:no_access'))
        self.assertEqual(bulk_delete_response.status_code, 302)
        self.assertEqual(bulk_delete_response.url, reverse('dashboard:no_access'))
        self.assertEqual(qty_response.status_code, 403)
        self.assertEqual(reorder_response.status_code, 403)
        product.refresh_from_db()
        self.assertFalse(product.is_deleted)
        self.assertTrue(product.is_active)
        self.assertEqual(product.web_qty, 5)

    def test_product_limited_edit_preserves_locked_fields_on_save(self):
        blocker_category = Category.objects.create(name='Slug Owner Category')
        blocker_category.companies.add(self.company)
        Product.objects.create(
            name='Slug Owner',
            slug='locked-product',
            company=self.company,
            category=blocker_category,
            price=10,
            web_qty=5,
            pos_qty=5,
            is_active=True,
            is_deleted=False,
        )
        product = self._product('Locked Product')
        original_slug = product.slug
        product.description = 'Old description'
        product.is_active = False
        product.save(update_fields=['description', 'is_active'])
        counter = Counter.objects.create(company=self.company, name='Hot Counter')
        ProductCounter.objects.create(product=product, counter=counter)
        self._grant(
            self.admin,
            'perm_products',
            level='part_edit',
            actions=['field_description', 'toggle'],
        )
        locked_json, level = get_locked_html_names(self.admin, 'perm_products')
        client = Client()
        client.force_login(self.admin)

        response = client.post(reverse('dashboard:product_edit', args=[product.pk]), {
            'description': 'New description',
            'is_active': 'on',
        })

        self.assertEqual(level, 'part_edit')
        self.assertIn('name', locked_json)
        self.assertIn('category', locked_json)
        self.assertIn('company', locked_json)
        self.assertIn('counter_ids', locked_json)
        self.assertNotIn('description', locked_json)
        self.assertNotIn('is_active', locked_json)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:product_list'))
        product.refresh_from_db()
        self.assertEqual(product.name, 'Locked Product')
        self.assertEqual(product.slug, original_slug)
        self.assertEqual(product.company, self.company)
        self.assertEqual(product.description, 'New description')
        self.assertTrue(product.is_active)
        self.assertEqual(ProductCounter.objects.filter(product=product).count(), 1)

    def test_product_list_includes_assigned_sites_only(self):
        second_company = Company.objects.create(name='Second Site', store_status=True, online_payment=True)
        third_company = Company.objects.create(name='Third Site', store_status=True, online_payment=True)
        self.admin.site_access.add(second_company)

        cat1 = Category.objects.create(name='Cat One')
        cat1.companies.add(self.company)
        cat2 = Category.objects.create(name='Cat Two')
        cat2.companies.add(second_company)
        cat3 = Category.objects.create(name='Cat Three')
        cat3.companies.add(third_company)
        Product.objects.create(name='Assigned Product One', company=self.company, category=cat1, price=10, is_active=True, is_deleted=False)
        Product.objects.create(name='Assigned Product Two', company=second_company, category=cat2, price=10, is_active=True, is_deleted=False)
        Product.objects.create(name='Unassigned Product', company=third_company, category=cat3, price=10, is_active=True, is_deleted=False)
        self._grant(self.admin, 'perm_products')

        response = self._get_as(self.admin, 'dashboard:product_list')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assigned Product One')
        self.assertContains(response, 'Assigned Product Two')
        self.assertNotContains(response, 'Unassigned Product')

    def test_unassigned_site_product_edit_is_blocked(self):
        other_company = Company.objects.create(name='Blocked Site', store_status=True, online_payment=True)
        other_category = Category.objects.create(name='Blocked Category')
        other_category.companies.add(other_company)
        product = Product.objects.create(
            name='Blocked Product',
            company=other_company,
            category=other_category,
            price=10,
            web_qty=5,
            pos_qty=5,
            is_active=True,
            is_deleted=False,
        )
        self._grant(self.admin, 'perm_products', level='part_edit', actions=['field_description'])
        client = Client()
        client.force_login(self.admin)

        response = client.get(reverse('dashboard:product_edit', args=[product.pk]))

        self.assertEqual(response.status_code, 404)

    def test_product_view_permission_does_not_allow_add_screen(self):
        self._grant(self.admin, 'perm_products')
        response = self._get_as(self.admin, 'dashboard:product_add')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:no_access'))

    def test_product_add_action_allows_add_screen(self):
        self._grant(self.admin, 'perm_products', level='part_edit', actions=['add'])
        response = self._get_as(self.admin, 'dashboard:product_add')
        self.assertEqual(response.status_code, 200)

    def test_coupon_view_only_cannot_add_or_delete(self):
        from apps.core.models import Coupon

        coupon = Coupon.objects.create(company=self.company, code='VIEWONLY', discount_type='flat', discount_value=10)
        self._grant(self.admin, 'perm_coupons')
        client = Client()
        client.force_login(self.admin)

        add_response = client.get(reverse('dashboard:coupon_add'))
        delete_response = client.post(reverse('dashboard:coupon_delete', args=[coupon.pk]))

        self.assertEqual(add_response.status_code, 302)
        self.assertEqual(add_response.url, reverse('dashboard:no_access'))
        self.assertEqual(delete_response.status_code, 302)
        self.assertEqual(delete_response.url, reverse('dashboard:no_access'))
        self.assertTrue(Coupon.objects.filter(pk=coupon.pk).exists())

    def test_pos_can_access_limited_product_list(self):
        self._grant(self.pos, 'perm_products', level='part_edit', actions=['cashier_edit'])
        response = self._get_as(self.pos, 'dashboard:product_list')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_manage_products'])
        self.assertTrue(response.context['can_limited_product_edit'])

    def test_pos_can_access_pos_product_list(self):
        self._grant(self.pos, 'perm_pos_terminal')
        response = self._get_as(self.pos, 'pos:terminal')
        self.assertEqual(response.status_code, 200)

    def test_cafeman_is_redirected_away_from_product_list(self):
        self._grant(self.cafeman, 'perm_kitchen')
        response = self._get_as(self.cafeman, 'dashboard:product_list')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:no_access'))

    def test_reports_role_is_redirected_away_from_product_list(self):
        self._grant(self.reports, 'perm_reports')
        response = self._get_as(self.reports, 'dashboard:product_list')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:no_access'))

    def test_reports_role_is_redirected_away_from_order_list(self):
        self._grant(self.reports, 'perm_reports')
        response = self._get_as(self.reports, 'dashboard:order_list')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:no_access'))

    def test_granular_matrix_replaces_legacy_access_for_configured_user(self):
        StaffAccess.objects.create(
            user=self.admin,
            landing_page='dashboard:home',
            visible_keys=['dashboard', 'products', 'orders'],
        )
        StaffModulePermission.objects.create(
            staff_user=self.admin,
            module_key='perm_reports',
            level='view',
        )

        self.assertEqual(get_allowed_keys(self.admin), {'reports'})

        reports_response = self._get_as(self.admin, 'dashboard:reports')
        products_response = self._get_as(self.admin, 'dashboard:product_list')

        self.assertEqual(reports_response.status_code, 200)
        self.assertEqual(products_response.status_code, 302)
        self.assertEqual(products_response.url, reverse('dashboard:no_access'))

    def test_royalty_leaderboard_has_its_own_matrix_route_key(self):
        StaffModulePermission.objects.create(
            staff_user=self.admin,
            module_key='perm_royalty_lb',
            level='view',
        )

        self.assertEqual(
            get_route_to_key_map()['dashboard:royalty_leaderboard'],
            'royalty_leaderboard',
        )
        self.assertEqual(get_allowed_keys(self.admin), {'royalty_leaderboard'})

    def test_granular_role_bypass_is_limited_to_granted_routes(self):
        StaffModulePermission.objects.create(
            staff_user=self.reports,
            module_key='perm_reviews',
            level='view',
        )

        allowed_response = self._get_as(self.reports, 'dashboard:reviews_list')
        response = self._get_as(self.reports, 'dashboard:product_list')
        self.assertEqual(allowed_response.status_code, 200)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard:no_access'))

    def test_legacy_user_access_routes_are_retired(self):
        superadmin = self._staff('superadmin@test.com', 'superadmin')
        client = Client()
        client.force_login(superadmin)

        list_response = client.get(reverse('dashboard:user_access'))
        edit_response = client.get(reverse('dashboard:user_access_edit', args=[self.admin.pk]))

        self.assertEqual(list_response.status_code, 302)
        self.assertEqual(list_response.url, reverse('dashboard:staff_list'))
        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(edit_response.url, reverse('dashboard:permission_matrix', args=[self.admin.pk]))

    def test_permission_matrix_saves_assigned_sites(self):
        second_company = Company.objects.create(name='Matrix Site', store_status=True, online_payment=True)
        superadmin = self._staff('matrix-super@test.com', 'superadmin')
        client = Client()
        client.force_login(superadmin)

        response = client.post(reverse('dashboard:permission_matrix', args=[self.admin.pk]), {
            'site_access': [str(self.company.pk), str(second_company.pk)],
            'level__perm_products': 'view',
        })

        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertEqual(
            set(self.admin.site_access.values_list('pk', flat=True)),
            {self.company.pk, second_company.pk},
        )
        self.assertEqual(
            StaffModulePermission.objects.get(staff_user=self.admin, module_key='perm_products').level,
            'view',
        )

    def test_granular_registry_covers_protected_module_keys(self):
        root = Path(__file__).resolve().parents[3]
        used_keys = set()
        for path in (root / 'apps').rglob('*.py'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            used_keys.update(re.findall(r"check_module_permission\(request,\s*['\"]([^'\"]+)['\"]", text))

        self.assertFalse(used_keys - set(ACTION_REGISTRY.keys()))

    def test_field_lock_registry_matches_granular_actions(self):
        missing = {
            module_key: sorted(set(field_map) - set(ACTION_REGISTRY.get(module_key, {}).get('actions', {})))
            for module_key, field_map in FIELD_HTML_NAMES.items()
        }
        missing = {module_key: keys for module_key, keys in missing.items() if keys}

        self.assertEqual(missing, {})
