from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Customer
from apps.core.models import Company
from apps.menu.models import Category, Product


def _company(name='FeaturedCo'):
    return Company.objects.create(
        name=name,
        store_status=True,
        online_payment=True,
        cod_payment=True,
        order_open_days=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
    )


def _category(company, name='Meals'):
    category = Category.objects.create(
        name=name,
        slug=name.lower(),
        open_days=[],
        is_active=True,
        is_deleted=False,
    )
    category.companies.add(company)
    return category


def _customer(company, email='featured@test.local'):
    return Customer.objects.create(
        company=company,
        name='Featured Tester',
        email=email,
        phone='9000000009',
        is_active=True,
        is_deleted=False,
        is_approved=True,
        is_email_verified=True,
    )


def _login_customer(client, customer):
    session = client.session
    session['customer_id'] = customer.pk
    session.save()


def _product(company, category, name, rating='0.00'):
    return Product.objects.create(
        company=company,
        category=category,
        name=name,
        slug=name.lower().replace(' ', '-'),
        price=Decimal('99.00'),
        rating=Decimal(str(rating)),
        is_active=True,
        is_deleted=False,
        web_qty=-1,
        max_qty=10,
        pos_qty=10,
        min_qty=1,
    )


class WebFeaturedProductsViewTest(TestCase):
    def setUp(self):
        self.company = _company()
        self.category = _category(self.company)
        self.customer = _customer(self.company)
        self.client = Client()
        _login_customer(self.client, self.customer)

    def test_home_featured_section_uses_explicit_web_featured_products(self):
        pinned = _product(self.company, self.category, 'Pinned Product', rating='1.00')
        pinned.featured_in_web = True
        pinned.save(update_fields=['featured_in_web'])

        _product(self.company, self.category, 'Popular Product', rating='5.00')
        _product(self.company, self.category, 'Regular Product', rating='3.00')

        response = self.client.get(reverse('menu:menu'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [product.name for product in response.context['featured_products']],
            ['Pinned Product'],
        )

    def test_home_featured_section_falls_back_to_top_rated_when_none_pinned(self):
        high = _product(self.company, self.category, 'Top Rated', rating='5.00')
        _product(self.company, self.category, 'Low Rated', rating='1.00')

        response = self.client.get(reverse('menu:menu'))

        self.assertEqual(response.status_code, 200)
        names = [p.name for p in response.context['featured_products']]
        self.assertIn('Top Rated', names)
        self.assertIn('Low Rated', names)

    def test_featured_section_capped_at_8(self):
        for i in range(12):
            p = _product(self.company, self.category, f'Pinned {i}')
            p.featured_in_web = True
            p.save(update_fields=['featured_in_web'])

        response = self.client.get(reverse('menu:menu'))
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.context['featured_products']), 8)
