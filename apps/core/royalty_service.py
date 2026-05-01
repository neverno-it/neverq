"""
Royalty points service.

Two earn mechanisms:
  1. Standard earn: every order awards points at company.royalty_points_per_rupee
  2. Leaderboard bonus: top N customers per period get bonus points

Both are recorded as WalletTransaction entries and tracked via RoyaltyAward
to prevent double-awarding.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Tuple

from django.db import transaction
from django.db.models import Sum, Count
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _period_key(company, dt=None) -> str:
    """Return a string key representing the current reward period for this company."""
    dt = dt or timezone.localtime()
    period = getattr(company, 'royalty_reward_period', 'monthly')
    if period == 'daily':
        return dt.strftime('%Y-%m-%d')
    elif period == 'weekly':
        return dt.strftime('%Y-W%W')
    else:  # monthly
        return dt.strftime('%Y-%m')


def _add_points(customer, delta: int, txn_type: str, order_ref: str = '', note: str = '',
                created_by: str = 'system') -> None:
    """Atomically increment customer royalty_points and write a WalletTransaction."""
    from apps.accounts.models import Customer, WalletTransaction
    if delta == 0:
        return
    # Atomic update with select_for_update to prevent race conditions
    with transaction.atomic():
        locked = customer.__class__._default_manager.select_for_update().get(pk=customer.pk)
        customer.__class__.objects.filter(pk=customer.pk).update(
            royalty_points=locked.royalty_points + delta
        )
    customer.refresh_from_db(fields=['royalty_points', 'wallet_balance'])
    WalletTransaction.objects.create(
        customer=customer,
        txn_type=txn_type,
        points_delta=delta,
        balance_after=customer.wallet_balance,
        points_after=customer.royalty_points,
        order_ref=order_ref,
        note=note,
        created_by=created_by,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Standard earn (called after each confirmed order)
# ─────────────────────────────────────────────────────────────────────────────

def award_standard_points(customer, order) -> int:
    """
    Award standard royalty points for a single order.
    Returns points awarded (0 if royalty disabled or already awarded).
    """
    from apps.accounts.models import WalletTransaction
    company = order.company
    if not getattr(company, 'royalty_enabled', False):
        return 0

    # Prevent duplicate award for the same order
    already = WalletTransaction.objects.filter(
        customer=customer,
        txn_type=WalletTransaction.TYPE_ROYALTY_EARNED,
        order_ref=order.order_number,
    ).exists()
    if already:
        return 0

    rate = Decimal(str(getattr(company, 'royalty_points_per_rupee', 1) or 1))

    # Use total_amount (full order value) as the earn basis — not my_pay.
    # Reason: company_pay customers have my_pay=₹0 (company covers the full
    # bill), but they should still earn loyalty points for the meal.
    # total_amount = after_offer_subtotal + packing (before wallet/subsidy).
    paid = Decimal(str(getattr(order, 'total_amount', 0) or 0))
    if paid <= 0:
        return 0

    pts = int(paid * rate)
    if pts <= 0:
        return 0

    _add_points(
        customer, pts,
        txn_type=WalletTransaction.TYPE_ROYALTY_EARNED,
        order_ref=order.order_number,
        note=f'Earned {pts} pts on order {order.order_number} (₹{paid} × {rate}/₹)',
        created_by='system',
    )
    return pts


# ─────────────────────────────────────────────────────────────────────────────
#  Leaderboard ranking
# ─────────────────────────────────────────────────────────────────────────────

def get_leaderboard(company, period_key: str | None = None, top_n: int = 10) -> list:
    """
    Returns list of dicts:
      [{'customer': <Customer>, 'value': <Decimal|int>, 'rank': int}, ...]
    ranked by the company's configured reward_mode within the given period.
    """
    from apps.orders.models import Order, OrderStatusChoices

    pk = period_key or _period_key(company)
    period = getattr(company, 'royalty_reward_period', 'monthly')
    mode   = getattr(company, 'royalty_reward_mode', 'amount')

    # Build date range from period_key
    import datetime
    if period == 'daily':
        date = datetime.date.fromisoformat(pk)
        start = timezone.make_aware(datetime.datetime.combine(date, datetime.time.min))
        end   = timezone.make_aware(datetime.datetime.combine(date, datetime.time.max))
    elif period == 'weekly':
        year, week = pk.split('-W')
        # Monday of that ISO week
        year_int, week_int = int(year), int(week)
        max_week = datetime.date(year_int, 12, 28).isocalendar()[1]
        week_int = max(1, min(week_int, max_week))
        start_date = datetime.date.fromisocalendar(year_int, week_int, 1)
        start = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
        end   = start + datetime.timedelta(days=7)
    else:  # monthly
        year, month = pk.split('-')
        start = timezone.make_aware(datetime.datetime(int(year), int(month), 1))
        import calendar
        last_day = calendar.monthrange(int(year), int(month))[1]
        end = timezone.make_aware(datetime.datetime(int(year), int(month), last_day, 23, 59, 59))

    confirmed_statuses = [
        OrderStatusChoices.CONFIRMED, OrderStatusChoices.PREPARING,
        OrderStatusChoices.READY, OrderStatusChoices.DELIVERED,
    ]
    qs = Order.objects.filter(
        company=company,
        order_status__in=confirmed_statuses,
        created_at__gte=start,
        created_at__lte=end,
        is_deleted=False,
    ).exclude(customer__email__contains='.kiosk')

    if mode == 'amount':
        # Use total_amount so company_pay customers (my_pay=0) are ranked fairly.
        qs = qs.values('customer').annotate(value=Sum('total_amount')).order_by('-value')
    else:
        qs = qs.values('customer').annotate(value=Count('id')).order_by('-value')

    from apps.accounts.models import Customer
    result = []
    for rank, row in enumerate(qs[:top_n], start=1):
        try:
            cust = Customer.objects.get(pk=row['customer'])
            result.append({'customer': cust, 'value': row['value'], 'rank': rank})
        except Customer.DoesNotExist:
            pass
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Leaderboard bonus award
# ─────────────────────────────────────────────────────────────────────────────

def award_leaderboard_bonuses(company, period_key: str | None = None, dry_run: bool = False) -> List[dict]:
    """
    Award bonus points to top 1/2/3 customers for the given period.
    Returns list of award dicts. Already-awarded ranks are skipped.
    If dry_run=True, returns what WOULD be awarded without writing.
    """
    from apps.core.models import RoyaltyAward
    from apps.accounts.models import WalletTransaction

    if not getattr(company, 'royalty_enabled', False):
        return []

    pk = period_key or _period_key(company)
    rank_points = {
        1: getattr(company, 'royalty_rank1_points', 500),
        2: getattr(company, 'royalty_rank2_points', 250),
        3: getattr(company, 'royalty_rank3_points', 100),
    }

    leaderboard = get_leaderboard(company, pk, top_n=3)
    results = []

    for entry in leaderboard:
        rank   = entry['rank']
        cust   = entry['customer']
        pts    = rank_points.get(rank, 0)
        if pts <= 0:
            continue

        # Check if already awarded
        already = RoyaltyAward.objects.filter(
            company=company, period_key=pk, rank=rank
        ).exists()
        if already:
            results.append({'rank': rank, 'customer': cust, 'points': pts, 'status': 'skipped_already_awarded'})
            continue

        if not dry_run:
            with transaction.atomic():
                RoyaltyAward.objects.create(
                    company=company, customer=cust,
                    period_key=pk, rank=rank, points=pts,
                )
                _add_points(
                    cust, pts,
                    txn_type=WalletTransaction.TYPE_ROYALTY_EARNED,
                    order_ref='',
                    note=f'Leaderboard bonus: Rank #{rank} for period {pk} ({pts} pts)',
                    created_by='system',
                )
        results.append({'rank': rank, 'customer': cust, 'points': pts, 'status': 'awarded'})

    return results
