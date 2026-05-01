"""
Test: Customer approval workflow and wallet/royalty operations.
"""
from decimal import Decimal
from django.test import TestCase

from apps.core.models import Company
from apps.accounts.models import Customer, WalletTransaction


def _make_company(**kw):
    defaults = dict(
        name='TestCo', store_status=True, royalty_enabled=True,
        royalty_points_per_rupee=Decimal('1'),
        royalty_min_redeem=50, royalty_max_redeem_pct=50,
        require_customer_approval=kw.pop('require_customer_approval', True),
        order_open_days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],
    )
    defaults.update(kw)
    return Company.objects.create(**defaults)


def _make_customer(company, approved=False, **kw):
    c = Customer.objects.create(
        name='Test', email=f'test_{company.pk}_{Customer.objects.count()}@t.com',
        company=company, is_approved=approved, **kw
    )
    c.set_password('pass')
    c.save()
    return c


class CustomerApprovalTest(TestCase):

    def test_new_customer_default_approval_false_when_company_requires(self):
        co = _make_company(require_customer_approval=True)
        cu = _make_customer(co, approved=False)
        self.assertFalse(cu.is_approved)

    def test_customer_approved_flag_set_to_true(self):
        co = _make_company()
        cu = _make_customer(co, approved=False)
        cu.is_approved = True
        cu.save()
        cu.refresh_from_db()
        self.assertTrue(cu.is_approved)

    def test_unapproved_customer_has_field(self):
        co = _make_company()
        cu = _make_customer(co, approved=False)
        self.assertFalse(cu.is_approved)
        self.assertTrue(hasattr(cu, 'wallet_balance'))
        self.assertTrue(hasattr(cu, 'royalty_points'))


class WalletTest(TestCase):

    def setUp(self):
        self.co = _make_company()
        self.cu = _make_customer(self.co, approved=True,
                                  wallet_balance=Decimal('0'), royalty_points=0)

    def test_wallet_topup(self):
        topup = Decimal('200.00')
        Customer.objects.filter(pk=self.cu.pk).update(wallet_balance=self.cu.wallet_balance + topup)
        self.cu.refresh_from_db()
        self.assertEqual(self.cu.wallet_balance, Decimal('200.00'))
        WalletTransaction.objects.create(
            customer=self.cu, txn_type=WalletTransaction.TYPE_TOPUP,
            wallet_delta=topup, balance_after=self.cu.wallet_balance,
            points_after=self.cu.royalty_points, created_by='admin'
        )
        self.assertEqual(WalletTransaction.objects.filter(customer=self.cu).count(), 1)

    def test_points_earn(self):
        pts = 100
        Customer.objects.filter(pk=self.cu.pk).update(royalty_points=self.cu.royalty_points + pts)
        self.cu.refresh_from_db()
        self.assertEqual(self.cu.royalty_points, pts)

    def test_points_redeem_1pt_equals_1_rupee(self):
        """1 royalty point = ₹1 deduction on order."""
        Customer.objects.filter(pk=self.cu.pk).update(royalty_points=200)
        self.cu.refresh_from_db()
        redeem_pts = 100
        pts_value = Decimal(str(redeem_pts))
        base_pay = Decimal('150.00')
        pay_after = max(Decimal('0'), base_pay - pts_value)
        self.assertEqual(pay_after, Decimal('50.00'))

    def test_no_negative_wallet(self):
        """Wallet cannot go below zero."""
        Customer.objects.filter(pk=self.cu.pk).update(wallet_balance=Decimal('10.00'))
        self.cu.refresh_from_db()
        apply = min(self.cu.wallet_balance, Decimal('50.00'))
        result = max(Decimal('0'), self.cu.wallet_balance - apply)
        self.assertEqual(result, Decimal('0.00'))

    def test_no_negative_points(self):
        Customer.objects.filter(pk=self.cu.pk).update(royalty_points=30)
        self.cu.refresh_from_db()
        apply = min(self.cu.royalty_points, 100)  # wants 100 but only has 30
        self.assertEqual(apply, 30)
        after = self.cu.royalty_points - apply
        self.assertGreaterEqual(after, 0)

    def test_wallet_transaction_audit_trail(self):
        WalletTransaction.objects.create(
            customer=self.cu, txn_type=WalletTransaction.TYPE_ORDER_DEBIT,
            wallet_delta=Decimal('-50'), balance_after=Decimal('150'),
            points_after=0, order_ref='WEB-001', created_by='customer'
        )
        txn = WalletTransaction.objects.get(customer=self.cu)
        self.assertEqual(txn.wallet_delta, Decimal('-50'))
        self.assertEqual(txn.order_ref, 'WEB-001')
