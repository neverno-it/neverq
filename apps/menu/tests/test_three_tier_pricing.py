import json
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Customer, StaffModulePermission, StaffUser
from apps.core.models import Building, Company
from apps.menu.models import Cafe, Category, Product, ProductCompanyPrice
from apps.menu.pricing import (
    PRICING_MODE_ROOM_SERVICE,
    PRICING_MODE_STAFF,
    PRICING_MODE_VISITOR,
    get_effective_price,
)
from apps.menu.views import _build_cart_summary
from apps.pos.models import POSOrder


def _company(name='Pricing Co'):
    return Company.objects.create(
        name=name,
        store_status=True,
        cod_payment=True,
        online_payment=True,
    )


def _category(company, name='Meals'):
    category = Category.objects.create(
        name=name,
        slug=name.lower().replace(' ', '-'),
        is_active=True,
        is_deleted=False,
    )
    category.companies.add(company)
    return category


def _product(company, category):
    return Product.objects.create(
        company=company,
        category=category,
        name='Test Meal',
        slug='test-meal',
        price=Decimal('60.00'),
        company_price=Decimal('100.00'),
        room_service_extra_percent=Decimal('10.00'),
        web_qty=-1,
        max_qty=10,
        pos_qty=10,
        is_active=True,
        is_kiosk_active=True,
        is_deleted=False,
    )


def _customer(company):
    return Customer.objects.create(
        company=company,
        name='Registered Customer',
        phone='9000000000',
        email='customer@example.com',
        password_hash='!',
        is_active=True,
        is_approved=True,
    )


def _pos_staff(company):
    staff = StaffUser.objects.create(
        company=company,
        name='POS User',
        email='pos@example.com',
        role=StaffUser.ROLE_POS,
        is_active=True,
    )
    staff.set_password('pass')
    staff.save()
    staff.site_access.add(company)
    StaffModulePermission.objects.create(
        staff_user=staff,
        module_key='perm_pos_terminal',
        level=StaffModulePermission.LEVEL_VIEW,
    )
    return staff


class ThreeTierPricingTest(TestCase):
    def setUp(self):
        self.company = _company()
        self.category = _category(self.company)
        self.product = _product(self.company, self.category)
        self.customer = _customer(self.company)
        self.staff = _pos_staff(self.company)

    def test_web_cart_uses_staff_base_price(self):
        summary = _build_cart_summary(self.customer, {
            str(self.product.pk): {'qty': 1, 'price': str(self.product.price), 'name': self.product.name},
        })

        self.assertEqual(summary['items'][0]['site_price'], Decimal('60.00'))
        self.assertEqual(summary['subtotal'], Decimal('60.00'))

    def test_explicit_pos_price_modes(self):
        visitor_price = get_effective_price(
            self.product,
            self.company,
            pricing_mode=PRICING_MODE_VISITOR,
        )
        staff_price = get_effective_price(
            self.product,
            self.company,
            pricing_mode=PRICING_MODE_STAFF,
        )
        room_price = get_effective_price(
            self.product,
            self.company,
            pricing_mode=PRICING_MODE_ROOM_SERVICE,
        )

        self.assertEqual(visitor_price, Decimal('100.00'))
        self.assertEqual(staff_price, Decimal('60.00'))
        self.assertEqual(room_price, Decimal('110.00'))

    def test_cafe_override_still_applies_when_building_is_selected(self):
        building = Building.objects.create(company=self.company, name='Tower A')
        cafe = Cafe.objects.create(company=self.company, building=building, name='Main Cafe', is_active=True)
        ProductCompanyPrice.objects.create(
            product=self.product,
            company=self.company,
            cafe=cafe,
            building=None,
            price=Decimal('80.00'),
            is_active=True,
        )

        staff_price = get_effective_price(
            self.product,
            self.company,
            building=building,
            cafe=cafe,
            pricing_mode=PRICING_MODE_STAFF,
        )
        visitor_price = get_effective_price(
            self.product,
            self.company,
            building=building,
            cafe=cafe,
            pricing_mode=PRICING_MODE_VISITOR,
        )

        self.assertEqual(staff_price, Decimal('80.00'))
        self.assertEqual(visitor_price, Decimal('100.00'))

    def test_kiosk_room_service_flag_does_not_change_non_pos_price(self):
        client = Client()
        session = client.session
        session['kiosk_cart'] = {str(self.product.pk): {'qty': 1}}
        session.save()

        response = client.get(
            reverse('orders:kiosk_cart', kwargs={'company_id': self.company.pk}),
            {'room_service': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['items'][0]['site_price'], Decimal('60.00'))
        self.assertEqual(response.context['effective_subtotal'], Decimal('60.00'))
        self.assertEqual(response.context['pricing_mode'], PRICING_MODE_STAFF)

    def test_pos_terminal_exposes_three_prices_for_menu_products(self):
        client = Client()
        client.force_login(self.staff)

        response = client.get(reverse('pos:terminal'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pos_prices'][self.product.pk], {
            'available': [PRICING_MODE_STAFF, PRICING_MODE_VISITOR, PRICING_MODE_ROOM_SERVICE],
            'v': 100.0,
            's': 60.0,
            'r': 110.0,
        })
        self.assertEqual(
            [item['key'] for item in response.context['pos_customer_types']],
            [PRICING_MODE_STAFF, PRICING_MODE_VISITOR, PRICING_MODE_ROOM_SERVICE],
        )

    def test_pos_terminal_hides_unconfigured_customer_types(self):
        self.product.company_price = Decimal('0.00')
        self.product.room_service_extra_percent = Decimal('0.00')
        self.product.save(update_fields=['company_price', 'room_service_extra_percent'])
        client = Client()
        client.force_login(self.staff)

        response = client.get(reverse('pos:terminal'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pos_prices'][self.product.pk], {
            'available': [PRICING_MODE_STAFF],
            'v': 0,
            's': 60.0,
            'r': 0,
        })
        self.assertEqual(
            [item['key'] for item in response.context['pos_customer_types']],
            [PRICING_MODE_STAFF],
        )
        self.assertContains(response, 'Staff')
        self.assertNotContains(response, 'Visitor')
        self.assertNotContains(response, 'Room Svc')

    def test_pos_terminal_hides_staff_when_base_price_is_zero(self):
        self.product.price = Decimal('0.00')
        self.product.company_price = Decimal('100.00')
        self.product.room_service_extra_percent = Decimal('0.00')
        self.product.save(update_fields=['price', 'company_price', 'room_service_extra_percent'])
        client = Client()
        client.force_login(self.staff)

        response = client.get(reverse('pos:terminal'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pos_prices'][self.product.pk]['available'], [PRICING_MODE_VISITOR])
        self.assertEqual(
            [item['key'] for item in response.context['pos_customer_types']],
            [PRICING_MODE_VISITOR],
        )

    def test_pos_order_uses_selected_customer_type_price(self):
        client = Client()
        client.force_login(self.staff)

        cases = [
            (POSOrder.CUSTOMER_STAFF, Decimal('60.00')),
            (POSOrder.CUSTOMER_VISITOR, Decimal('100.00')),
            (POSOrder.CUSTOMER_ROOM_SERVICE, Decimal('110.00')),
        ]

        for customer_type, expected_total in cases:
            with self.subTest(customer_type=customer_type):
                response = client.post(
                    reverse('pos:place_order'),
                    data=json.dumps({
                        'customer_type': customer_type,
                        'payment_type': POSOrder.PAYMENT_CASH,
                        'items': [{'id': self.product.pk, 'src': 'menu', 'qty': 1}],
                    }),
                    content_type='application/json',
                    HTTP_ACCEPT='application/json',
                )

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload['success'])
                self.assertEqual(Decimal(payload['base_total']), expected_total)
                self.assertEqual(Decimal(payload['total']), expected_total)

                order = POSOrder.objects.get(pk=payload['order_id'])
                self.assertEqual(order.customer_type, customer_type)
                self.assertEqual(order.items.get().price, expected_total)

    def test_pos_order_rejects_unconfigured_customer_type(self):
        self.product.company_price = Decimal('0.00')
        self.product.room_service_extra_percent = Decimal('0.00')
        self.product.save(update_fields=['company_price', 'room_service_extra_percent'])
        client = Client()
        client.force_login(self.staff)

        response = client.post(
            reverse('pos:place_order'),
            data=json.dumps({
                'customer_type': POSOrder.CUSTOMER_VISITOR,
                'payment_type': POSOrder.PAYMENT_CASH,
                'items': [{'id': self.product.pk, 'src': 'menu', 'qty': 1}],
            }),
            content_type='application/json',
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn('not available for this customer type', payload['error'])

    def test_cross_company_copy_preserves_staff_and_room_service_settings(self):
        target_company = _company('Target Pricing Co')
        target_category = _category(target_company, 'Target Meals')
        superadmin = StaffUser.objects.create(
            name='Super Admin',
            email='super@example.com',
            role=StaffUser.ROLE_SUPERADMIN,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )
        superadmin.set_password('pass')
        superadmin.save()

        client = Client()
        client.force_login(superadmin)
        response = client.post(
            reverse('dashboard:product_bulk_copy'),
            data={
                'ids': [str(self.product.pk)],
                'target_company': str(target_company.pk),
                'target_category': str(target_category.pk),
                f'copy_price_{self.product.pk}': '95.00',
            },
        )

        self.assertEqual(response.status_code, 302)
        copied = Product.objects.get(company=target_company, name=self.product.name)
        self.assertEqual(copied.price, Decimal('95.00'))
        self.assertEqual(copied.company_price, Decimal('100.00'))
        self.assertEqual(copied.room_service_extra_percent, Decimal('10.00'))
