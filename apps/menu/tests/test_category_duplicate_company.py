from django.test import Client, TestCase
from django.urls import reverse
import datetime

from apps.accounts.models import StaffUser
from apps.core.models import Company
from apps.menu.models import Category, CategoryCompanyStatus, Product, Schedule


def _company(name):
    return Company.objects.create(
        name=name,
        store_status=True,
        cod_payment=True,
        online_payment=True,
    )


def _staff(company=None, role=StaffUser.ROLE_SUPERADMIN, email='super@example.com'):
    staff = StaffUser.objects.create(
        company=company,
        name='Category Tester',
        email=email,
        role=role,
        is_active=True,
        is_staff=True,
    )
    staff.set_password('pass')
    staff.save()
    return staff


class CategoryDuplicateCompanyTest(TestCase):
    def test_superadmin_adds_existing_category_to_another_company(self):
        first_company = _company('First Category Co')
        second_company = _company('Second Category Co')
        category = Category.objects.create(
            name='Combos',
            slug='combos',
            is_active=True,
            is_deleted=False,
        )
        category.companies.add(first_company)

        client = Client()
        client.force_login(_staff())
        response = client.post(reverse('dashboard:category_add'), {
            'name': 'Combos',
            'companies': [str(second_company.pk)],
            'position_order': '0',
            'preparation_time_minutes': '0',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Category.objects.filter(name__iexact='Combos', is_deleted=False).count(), 1)
        category.refresh_from_db()
        self.assertSetEqual(
            set(category.companies.values_list('pk', flat=True)),
            {first_company.pk, second_company.pk},
        )

    def test_shared_category_status_is_per_company(self):
        first_company = _company('Status First Co')
        second_company = _company('Status Second Co')
        category = Category.objects.create(
            name='Shared Meals',
            slug='shared-meals',
            is_active=True,
            is_deleted=False,
        )
        category.companies.add(first_company, second_company)
        CategoryCompanyStatus.objects.create(category=category, company=first_company, is_active=False)
        CategoryCompanyStatus.objects.create(category=category, company=second_company, is_active=True)

        first_product = Product.objects.create(
            company=first_company,
            category=category,
            name='First Meal',
            slug='first-meal',
            price='50.00',
            is_active=True,
            is_deleted=False,
        )
        second_product = Product.objects.create(
            company=second_company,
            category=category,
            name='Second Meal',
            slug='second-meal',
            price='50.00',
            is_active=True,
            is_deleted=False,
        )

        self.assertFalse(category.is_active_now(first_company))
        self.assertTrue(category.is_active_now(second_company))
        self.assertFalse(first_product.is_available_now())
        self.assertTrue(second_product.is_available_now())

    def test_shared_category_schedule_can_be_overridden_per_company(self):
        first_company = _company('Global Schedule Co')
        second_company = _company('Custom Schedule Co')
        category = Category.objects.create(
            name='Scheduled Shared Meals',
            slug='scheduled-shared-meals',
            is_active=True,
            is_deleted=False,
        )
        category.companies.add(first_company, second_company)
        CategoryCompanyStatus.objects.create(category=category, company=first_company, is_active=True)
        CategoryCompanyStatus.objects.create(
            category=category,
            company=second_company,
            is_active=True,
            use_custom_availability=True,
        )
        from django.utils import timezone
        today = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][timezone.localtime().weekday()]
        other_day = [day for day in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] if day != today][0]

        Schedule.objects.create(
            category=category,
            display_day=other_day,
            start_time=datetime.time(0, 0),
            end_time=datetime.time(23, 59, 59),
        )
        Schedule.objects.create(
            category=category,
            company=second_company,
            display_day='All',
            start_time=datetime.time(0, 0),
            end_time=datetime.time(23, 59, 59),
        )

        first_product = Product.objects.create(
            company=first_company,
            category=category,
            name='Global Schedule Meal',
            slug='global-schedule-meal',
            price='50.00',
            is_active=True,
            is_deleted=False,
        )
        second_product = Product.objects.create(
            company=second_company,
            category=category,
            name='Custom Schedule Meal',
            slug='custom-schedule-meal',
            price='50.00',
            is_active=True,
            is_deleted=False,
        )

        self.assertFalse(category.is_active_now(first_company))
        self.assertTrue(category.is_active_now(second_company))
        self.assertFalse(first_product.is_available_now())
        self.assertTrue(second_product.is_available_now())

    def test_category_edit_preserves_site_status_and_saves_custom_availability(self):
        first_company = _company('Edit First Co')
        second_company = _company('Edit Second Co')
        category = Category.objects.create(
            name='Editable Shared Meals',
            slug='editable-shared-meals',
            is_active=True,
            is_deleted=False,
        )
        category.companies.add(first_company, second_company)
        CategoryCompanyStatus.objects.create(category=category, company=first_company, is_active=False)
        CategoryCompanyStatus.objects.create(category=category, company=second_company, is_active=True)

        client = Client()
        client.force_login(_staff(email='edit-super@example.com'))
        response = client.post(reverse('dashboard:category_edit', kwargs={'pk': category.pk}), {
            'name': 'Editable Shared Meals',
            'companies': [str(first_company.pk), str(second_company.pk)],
            'position_order': '0',
            'preparation_time_minutes': '0',
            'is_active': 'on',
            'site_schedule_company_ids': [str(second_company.pk)],
            f'site_schedule_enabled_{second_company.pk}': 'on',
            f'site_open_days_{second_company.pk}': ['Tue', 'Wed'],
            f'site_window_day_{second_company.pk}_0': 'All',
            f'site_window_start_{second_company.pk}_0': '09:00',
            f'site_window_end_{second_company.pk}_0': '17:00',
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CategoryCompanyStatus.objects.get(category=category, company=first_company).is_active)
        second_status = CategoryCompanyStatus.objects.get(category=category, company=second_company)
        self.assertTrue(second_status.is_active)
        self.assertTrue(second_status.use_custom_availability)
        self.assertEqual(second_status.open_days, ['Tue', 'Wed'])
        self.assertTrue(Schedule.objects.filter(category=category, company=second_company, display_day='All').exists())

    def test_superadmin_toggles_one_company_for_shared_category(self):
        first_company = _company('Toggle First Co')
        second_company = _company('Toggle Second Co')
        category = Category.objects.create(
            name='Toggle Meals',
            slug='toggle-meals',
            is_active=True,
            is_deleted=False,
        )
        category.companies.add(first_company, second_company)
        CategoryCompanyStatus.objects.create(category=category, company=first_company, is_active=True)
        CategoryCompanyStatus.objects.create(category=category, company=second_company, is_active=True)

        client = Client()
        client.force_login(_staff(email='toggle-super@example.com'))
        response = client.post(
            reverse('dashboard:category_toggle', kwargs={'pk': category.pk}),
            {'company_id': str(first_company.pk)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CategoryCompanyStatus.objects.get(category=category, company=first_company).is_active)
        self.assertTrue(CategoryCompanyStatus.objects.get(category=category, company=second_company).is_active)

    def test_category_list_renders_per_site_statuses(self):
        first_company = _company('List First Co')
        second_company = _company('List Second Co')
        category = Category.objects.create(
            name='List Meals',
            slug='list-meals',
            is_active=True,
            is_deleted=False,
        )
        category.companies.add(first_company, second_company)
        CategoryCompanyStatus.objects.create(category=category, company=first_company, is_active=False)
        CategoryCompanyStatus.objects.create(category=category, company=second_company, is_active=True)

        client = Client()
        client.force_login(_staff(email='list-super@example.com'))
        response = client.get(reverse('dashboard:category_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'List First Co')
        self.assertContains(response, 'List Second Co')
        self.assertContains(response, f'cat-status-label-{category.pk}-{first_company.pk}')
        self.assertContains(response, f'cat-status-label-{category.pk}-{second_company.pk}')

    def test_admin_adds_existing_category_to_own_company(self):
        first_company = _company('Admin First Co')
        second_company = _company('Admin Second Co')
        category = Category.objects.create(
            name='Mains',
            slug='mains',
            is_active=True,
            is_deleted=False,
        )
        category.companies.add(first_company)

        client = Client()
        client.force_login(_staff(
            company=second_company,
            role=StaffUser.ROLE_ADMIN,
            email='admin-category@example.com',
        ))
        response = client.post(reverse('dashboard:category_add'), {
            'name': 'Mains',
            'position_order': '0',
            'preparation_time_minutes': '0',
            'is_active': 'on',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Category.objects.filter(name__iexact='Mains', is_deleted=False).count(), 1)
        category.refresh_from_db()
        self.assertSetEqual(
            set(category.companies.values_list('pk', flat=True)),
            {first_company.pk, second_company.pk},
        )
