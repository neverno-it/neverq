from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import Customer
from apps.core.models import Company
from apps.orders.models import Order, OrderStatusChoices, PaymentModeChoices


def _company():
    return Company.objects.create(
        name='SnapCo', store_status=True, online_payment=True
    )


def _customer(company):
    return Customer.objects.create(
        company=company, name='Real Name', email='snap@test.local',
        phone='9111111111', is_active=True, is_approved=True,
        is_email_verified=True, is_deleted=False,
    )


def _order(company, customer, name_snap='', phone_snap=''):
    return Order.objects.create(
        company=company, customer=customer,
        customer_name_snapshot=name_snap,
        customer_phone_snapshot=phone_snap,
        subtotal=Decimal('100'), total_amount=Decimal('100'),
        my_pay=Decimal('100'), order_number='TEST001',
        payment_mode=PaymentModeChoices.CASH,
        order_status=OrderStatusChoices.CONFIRMED,
    )


class DisplayCustomerNameTest(TestCase):
    def setUp(self):
        self.co = _company()
        self.cu = _customer(self.co)

    def test_snapshot_takes_priority_over_fk(self):
        order = _order(self.co, self.cu, name_snap='Walk-in Priya')
        self.assertEqual(order.display_customer_name, 'Walk-in Priya')

    def test_fk_used_when_snapshot_empty(self):
        order = _order(self.co, self.cu, name_snap='')
        self.assertEqual(order.display_customer_name, 'Real Name')

    def test_fallback_when_both_empty(self):
        self.cu.name = ''
        self.cu.save()
        order = _order(self.co, self.cu, name_snap='')
        self.assertEqual(order.display_customer_name, 'Customer')

    def test_phone_snapshot_takes_priority(self):
        order = _order(self.co, self.cu, phone_snap='9000000001')
        self.assertEqual(order.display_customer_phone, '9000000001')

    def test_phone_fk_used_when_snapshot_empty(self):
        order = _order(self.co, self.cu, phone_snap='')
        self.assertEqual(order.display_customer_phone, '9111111111')

    def test_phone_empty_string_when_both_absent(self):
        self.cu.phone = ''
        self.cu.save()
        order = _order(self.co, self.cu, phone_snap='')
        self.assertEqual(order.display_customer_phone, '')
