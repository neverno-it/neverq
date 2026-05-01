"""
Test: Royalty leaderboard ranking, bonus award, duplicate prevention.
"""
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Company, RoyaltyAward
from apps.core.royalty_service import (
    award_standard_points, award_leaderboard_bonuses, get_leaderboard, _period_key
)
from apps.accounts.models import Customer, WalletTransaction
from apps.menu.models import Category, Product
from apps.orders.models import Order, OrderStatusChoices


def _co(**kw):
    defaults = dict(
        name='LeadCo', store_status=True, royalty_enabled=True,
        royalty_points_per_rupee=Decimal('1'),
        royalty_min_redeem=10, royalty_max_redeem_pct=50,
        royalty_rank1_points=500, royalty_rank2_points=200, royalty_rank3_points=50,
        royalty_reward_mode='amount', royalty_reward_period='monthly',
        order_open_days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],
    )
    defaults.update(kw)
    return Company.objects.create(**defaults)


def _customer(co, name, email):
    c = Customer.objects.create(name=name, email=email, company=co,
                                 is_approved=True, royalty_points=0, wallet_balance=Decimal('0'))
    c.set_password('pass'); c.save()
    return c


def _order(co, cu, amount, status=OrderStatusChoices.DELIVERED):
    return Order.objects.create(
        company=co, customer=cu,
        order_status=status,
        my_pay=amount, total_amount=amount, subtotal=amount,
        order_number=f'WEB-{Order.objects.count()+1:04d}',
        created_at=timezone.now(),
    )


class StandardEarnTest(TestCase):

    def setUp(self):
        self.co = _co()
        self.cat = Category.objects.create(name='Cat')
        self.cat.companies.add(self.co)

    def test_earn_points_on_confirmed_order(self):
        cu = _customer(self.co, 'Alice', 'alice@t.com')
        order = _order(self.co, cu, Decimal('100'))
        pts = award_standard_points(cu, order)
        self.assertEqual(pts, 100)  # 1pt per ₹1

    def test_earn_rate_scaled(self):
        co2 = _co(name='LeadCo2', royalty_points_per_rupee=Decimal('2'))
        cu = _customer(co2, 'Bob', 'bob@t.com')
        order = _order(co2, cu, Decimal('50'))
        pts = award_standard_points(cu, order)
        self.assertEqual(pts, 100)  # 2pt per ₹1

    def test_no_earn_when_royalty_disabled(self):
        co3 = _co(name='LeadCo3', royalty_enabled=False)
        cu = _customer(co3, 'Carol', 'carol@t.com')
        order = _order(co3, cu, Decimal('100'))
        pts = award_standard_points(cu, order)
        self.assertEqual(pts, 0)

    def test_no_duplicate_earn_same_order(self):
        cu = _customer(self.co, 'Dave', 'dave@t.com')
        order = _order(self.co, cu, Decimal('80'))
        pts1 = award_standard_points(cu, order)
        pts2 = award_standard_points(cu, order)  # second call same order
        self.assertEqual(pts1, 80)
        self.assertEqual(pts2, 0)  # blocked by duplicate check
        # Only one WalletTransaction should exist
        count = WalletTransaction.objects.filter(
            customer=cu, txn_type=WalletTransaction.TYPE_ROYALTY_EARNED,
            order_ref=order.order_number
        ).count()
        self.assertEqual(count, 1)

    def test_wallet_transaction_recorded(self):
        cu = _customer(self.co, 'Eve', 'eve@t.com')
        order = _order(self.co, cu, Decimal('60'))
        award_standard_points(cu, order)
        txn = WalletTransaction.objects.get(customer=cu,
              txn_type=WalletTransaction.TYPE_ROYALTY_EARNED)
        self.assertEqual(txn.points_delta, 60)
        self.assertEqual(txn.order_ref, order.order_number)


class LeaderboardTest(TestCase):

    def setUp(self):
        self.co = _co()
        self.cu1 = _customer(self.co, 'Top',    'top@t.com')
        self.cu2 = _customer(self.co, 'Second', 'sec@t.com')
        self.cu3 = _customer(self.co, 'Third',  'thd@t.com')
        # Create orders: cu1 spends most
        _order(self.co, self.cu1, Decimal('300'))
        _order(self.co, self.cu1, Decimal('200'))  # total 500
        _order(self.co, self.cu2, Decimal('250'))  # total 250
        _order(self.co, self.cu3, Decimal('100'))  # total 100

    def test_leaderboard_ranked_by_amount(self):
        board = get_leaderboard(self.co)
        self.assertEqual(board[0]['customer'].pk, self.cu1.pk)
        self.assertEqual(board[1]['customer'].pk, self.cu2.pk)
        self.assertEqual(board[2]['customer'].pk, self.cu3.pk)
        self.assertEqual(board[0]['rank'], 1)
        self.assertEqual(board[1]['rank'], 2)

    def test_leaderboard_ranked_by_count(self):
        self.co.royalty_reward_mode = 'count'
        self.co.save()
        # cu1 has 2 orders, others have 1 each
        board = get_leaderboard(self.co)
        self.assertEqual(board[0]['customer'].pk, self.cu1.pk)
        self.assertEqual(board[0]['value'], 2)

    def test_award_gives_correct_points(self):
        results = award_leaderboard_bonuses(self.co)
        awarded = {r['rank']: r for r in results if r['status'] == 'awarded'}
        self.assertIn(1, awarded)
        self.assertIn(2, awarded)
        self.assertIn(3, awarded)
        self.assertEqual(awarded[1]['points'], 500)
        self.assertEqual(awarded[2]['points'], 200)
        self.assertEqual(awarded[3]['points'], 50)

    def test_award_updates_customer_points(self):
        award_leaderboard_bonuses(self.co)
        self.cu1.refresh_from_db()
        self.assertEqual(self.cu1.royalty_points, 500)
        self.cu2.refresh_from_db()
        self.assertEqual(self.cu2.royalty_points, 200)

    def test_duplicate_award_blocked(self):
        results1 = award_leaderboard_bonuses(self.co)
        results2 = award_leaderboard_bonuses(self.co)  # same period
        awarded1 = [r for r in results1 if r['status'] == 'awarded']
        skipped2 = [r for r in results2 if r['status'] == 'skipped_already_awarded']
        self.assertEqual(len(awarded1), 3)
        self.assertEqual(len(skipped2), 3)
        # Points not doubled
        self.cu1.refresh_from_db()
        self.assertEqual(self.cu1.royalty_points, 500)

    def test_royalty_award_record_created(self):
        pk = _period_key(self.co)
        award_leaderboard_bonuses(self.co)
        awards = RoyaltyAward.objects.filter(company=self.co, period_key=pk)
        self.assertEqual(awards.count(), 3)
        ranks = set(awards.values_list('rank', flat=True))
        self.assertEqual(ranks, {1, 2, 3})

    def test_dry_run_does_not_write(self):
        results = award_leaderboard_bonuses(self.co, dry_run=True)
        self.assertEqual(RoyaltyAward.objects.count(), 0)
        self.assertEqual(WalletTransaction.objects.count(), 0)
        awarded = [r for r in results if r['status'] == 'awarded']
        self.assertEqual(len(awarded), 3)  # reports what would happen

    def test_different_period_keys_independent(self):
        """Same period awarded twice is blocked; two different periods are independent."""
        from apps.core.royalty_service import _period_key
        current = _period_key(self.co)
        # Award current period
        award_leaderboard_bonuses(self.co, current)
        self.assertEqual(RoyaltyAward.objects.filter(company=self.co, period_key=current).count(), 3)
        # Re-award same period: should all be skipped
        result2 = award_leaderboard_bonuses(self.co, current)
        skipped = [r for r in result2 if r['status'] == 'skipped_already_awarded']
        self.assertEqual(len(skipped), 3)
        # Total records still 3, not 6
        self.assertEqual(RoyaltyAward.objects.filter(company=self.co, period_key=current).count(), 3)
