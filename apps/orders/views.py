import logging
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
import json

logger = logging.getLogger(__name__)
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

from apps.accounts.decorators import customer_login_required, staff_role_required
from apps.core.models import Company
from apps.menu.models import Product
from apps.menu.pricing import (
    PRICING_MODE_ROOM_SERVICE,
    PRICING_MODE_STAFF,
    get_effective_price,
)
from .models import Order, OrderItem, OrderStatus, OrderStatusChoices, PaymentModeChoices
from .phonepe import (
    PhonePeError,
    create_phonepe_payment,
    fetch_phonepe_order_status,
    phonepe_callback_authorized,
    phonepe_decode_callback,
)
from .razorpay import (
    RazorpayError,
    create_razorpay_order,
    to_paise,
    verify_razorpay_signature,
    verify_razorpay_webhook_signature,
)

ORDER_NUMBER_SEQUENCE_CACHE_TTL = 7 * 24 * 60 * 60


def _money(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


class StockUnavailableError(Exception):
    """Raised when stock is unavailable during final order creation."""
    pass


def _web_stock_available(product, qty=1):
    try:
        qty = int(qty or 0)
    except (TypeError, ValueError):
        qty = 0
    if qty <= 0:
        return True
    return product.web_qty < 0 or product.web_qty >= qty



def _get_order_min_qty(product):
    try:
        return max(1, int(getattr(product, 'min_qty', 1) or 1))
    except (TypeError, ValueError):
        return 1


def _get_order_max_qty(product):
    try:
        return max(1, int(getattr(product, 'max_qty', 999999) or 999999))
    except (TypeError, ValueError):
        return 999999


def _get_web_max_qty(product):
    """
    Effective maximum units allowed on a web/kiosk order line.
    max_qty is per-order; web_qty is stock only.
    """
    min_qty = _get_order_min_qty(product)
    cap = _get_order_max_qty(product)
    try:
        _raw = getattr(product, 'web_qty', None)
        web_qty = int(_raw) if _raw is not None else -1
    except (TypeError, ValueError):
        web_qty = -1
    if web_qty >= 0:
        cap = min(cap, web_qty)
    return cap if cap >= min_qty else 0


def _pos_stock_available(product, qty=1):
    try:
        qty = int(qty or 0)
    except (TypeError, ValueError):
        qty = 0
    if qty <= 0:
        return True
    return int(product.pos_qty or 0) >= qty



# ─── Stock & Pricing helpers ─────────────────────────────────────────────────

def _deduct_stock(product, qty, source, ref_id, company, note=''):
    """
    Atomically deduct stock and write a ledger entry.
    source: 'web' or 'pos'
    Returns True if stock was available (or unlimited), False if out of stock.
    """
    from apps.menu.models import StockLedger
    from django.db import transaction
    with transaction.atomic():
        p = product.__class__.objects.select_for_update().get(pk=product.pk)
        if source == 'web':
            if p.web_qty >= 0:          # -1 = unlimited
                if p.web_qty < qty:
                    return False
                p.web_qty = max(0, p.web_qty - qty)
            p.save(update_fields=['web_qty'])
        elif source == 'pos':
            if p.pos_qty < qty:
                return False
            p.pos_qty = max(0, p.pos_qty - qty)
            p.save(update_fields=['pos_qty'])
        StockLedger.objects.create(
            product=p, company=company, source=source,
            ref_id=ref_id, qty=-qty, note=note,
        )
    return True


def _restock(product, qty, source, ref_id, company, note=''):
    """Restore stock on order cancel."""
    from apps.menu.models import StockLedger
    from django.db import transaction
    with transaction.atomic():
        p = product.__class__.objects.select_for_update().get(pk=product.pk)
        if source == 'web':
            if p.web_qty >= 0:
                p.web_qty += qty
            p.save(update_fields=['web_qty'])
        elif source == 'pos':
            p.pos_qty += qty
            p.save(update_fields=['pos_qty'])
        StockLedger.objects.create(
            product=p, company=company, source=source,
            ref_id=ref_id, qty=qty, note=note,
        )


def _get_site_price(product, company, building=None, cafe=None, pricing_mode=PRICING_MODE_STAFF):
    return get_effective_price(
        product,
        company,
        building=building,
        cafe=cafe,
        pricing_mode=pricing_mode,
    )



def _fresh_company(customer):
    company = Company.objects.get(pk=customer.company_id)
    customer.company = company
    return company


def _money_text(value):
    return f"{_money(value):.2f}"


def _next_order_number(default_prefix, company=None):
    """
    Generate a sequential, collision-safe order number.

    Format: PREFIX-YYMMDD-NNNN  e.g. WEB-260401-0001

    Prefix resolution:
      - Web orders:   company.web_order_prefix   or default_prefix ('WEB')
      - Kiosk orders: company.kiosk_order_prefix or default_prefix ('KIO')
    Prefix is uppercased and stripped; falls back to default if blank.
    """
    if company is not None:
        if default_prefix.upper() == 'WEB':
            raw = getattr(company, 'web_order_prefix', '') or ''
        else:
            raw = getattr(company, 'kiosk_order_prefix', '') or ''
        prefix = raw.strip().upper() or default_prefix.upper()
    else:
        prefix = default_prefix.upper()

    today = timezone.localdate().strftime('%y%m%d')
    base = f"{prefix}-{today}-"
    last = (
        Order.objects.filter(order_number__startswith=base)
        .order_by('-order_number')
        .values_list('order_number', flat=True)
        .first()
    )
    last_db_seq = 0
    if last:
        try:
            last_db_seq = int(str(last).rsplit('-', 1)[-1])
        except (ValueError, IndexError):
            last_db_seq = 0
    cache_key = f'neverq:order-seq:{base}'
    try:
        if cache.add(cache_key, last_db_seq, ORDER_NUMBER_SEQUENCE_CACHE_TTL):
            seq = int(cache.incr(cache_key))
        else:
            cached_seq = cache.get(cache_key)
            try:
                cached_seq = int(cached_seq)
            except (TypeError, ValueError):
                cached_seq = 0
            if cached_seq < last_db_seq:
                cache.set(cache_key, last_db_seq, ORDER_NUMBER_SEQUENCE_CACHE_TTL)
            seq = int(cache.incr(cache_key))
    except Exception:
        seq = last_db_seq + 1

    candidate = f"{base}{seq:04d}"
    while (
        Order.objects.filter(order_number=candidate).exists()
        or _get_pending_phonepe_snapshot('web', candidate)
        or _get_pending_phonepe_snapshot('kiosk', candidate)
    ):
        seq += 1
        candidate = f"{base}{seq:04d}"
    try:
        cache.set(cache_key, seq, ORDER_NUMBER_SEQUENCE_CACHE_TTL)
    except Exception:
        pass
    return candidate


def _clear_edit_order_session(request):
    request.session.pop('editing_order_id', None)
    request.session.modified = True


def _load_order_into_cart(request, order):
    cart = {}
    for item in order.items.filter(is_deleted=False).select_related('product'):
        product = item.product
        if not product or product.is_deleted or not product.is_active:
            continue
        key = str(product.pk)
        entry = cart.setdefault(key, {'qty': 0, 'price': str(product.price), 'name': product.name})
        entry['qty'] += int(item.qty or 0)
    request.session['cart'] = cart
    request.session['editing_order_id'] = order.pk
    request.session.modified = True
    return cart


def _restore_order_stock(order, note_prefix='Edit restore'):
    for oi in order.items.filter(is_deleted=False).select_related('product'):
        if oi.product:
            _restock(oi.product, oi.qty, 'web', order.pk, order.company, f'{note_prefix} {order.order_number}')


def _rewrite_order_from_summary(order, summary, payment_mode, payment_status, order_type, scheduled_dt, initial_status, status_note, coupon=None, coupon_discount=Decimal('0.00')):
    order.coupon_id = coupon.pk if coupon else 0
    order.coupon_discount = coupon_discount
    order.offer_discount = summary['offer_discount']
    order.subtotal = summary['subtotal']
    order.shipping_cost = summary['packing']
    order.bill_to_company = summary['bill_to_company']
    order.my_pay = summary['my_pay']
    order.total_amount = summary['total']
    order.payment_mode = payment_mode
    order.payment_status = payment_status
    order.order_type = order_type
    order.order_status = initial_status
    order.scheduled_date = scheduled_dt
    # Customer model has no cafe field; preserve the order's existing cafe if already set
    # (it gets assigned from the customer's building→cafe resolution at order creation time)
    if order.cafe_id is None:
        order.cafe = None
    order.auto_ready_at = order.calculate_auto_ready_at(start_from=timezone.now()) if initial_status == OrderStatusChoices.CONFIRMED else None
    order.save()

    # Remove old tickets/items then rebuild fresh
    order.counter_tickets.all().delete()
    order.items.all().delete()

    for item in summary['items']:
        product = item['product']
        qty = item['qty']
        gross_unit = item.get('site_price', product.price)
        line_saving = item.get('line_saving', Decimal('0.00'))
        effective_unit = (item['line_total'] / qty) if qty else gross_unit
        # FIX-5: use cafe-aware counter resolution (same as kiosk) for consistency
        _order_cafe = getattr(order, 'cafe', None)
        OrderItem.objects.create(
            company=order.company,
            order=order,
            product=product,
            counter=_resolve_product_counter(product, cafe=_order_cafe),
            price=effective_unit,
            unit_price=gross_unit,
            item_offer_discount=line_saving,
            qty=qty,
            image_snapshot=str(product.image) if product.image else '',
            created_at=timezone.now(),
        )
        _deduct_stock(product, qty, 'web', order.pk, order.company, f'Edit {order.order_number}')

    _create_counter_tickets(order)
    OrderStatus.objects.create(
        order=order,
        status=initial_status,
        details=status_note,
        created_at=timezone.now(),
    )
    return order


def _ordering_closed_message(company):
    return company.ordering_status_message or 'Ordering is currently closed for this store.'


def _unavailable_cart_item_names(summary):
    names = []
    for item in summary.get('items', []):
        product = item.get('product')
        qty = int(item.get('qty', 0) or 0)
        if not product:
            continue
        if not product.is_available_now():
            names.append(product.name)
            continue
        if not _web_stock_available(product, qty):
            names.append(product.name)
    return names



def _get_customer_product(company, product_id):
    try:
        return Product.objects.select_related('category').prefetch_related('food_type').get(
            pk=int(product_id),
            is_deleted=False,
            company=company,
        )
    except (Product.DoesNotExist, TypeError, ValueError):
        return None





def _create_counter_tickets(order):
    """
    Group confirmed order items by counter and create one CounterTicket per group.
    Items with no counter assigned get a single 'unassigned' ticket.
    Safe to call multiple times; duplicates are not created.
    """
    from apps.orders.models import CounterTicket
    from collections import defaultdict

    groups = defaultdict(list)
    for item in order.items.filter(is_deleted=False).select_related('counter'):
        groups[item.counter].append(item)

    tickets = []
    for counter, items in groups.items():
        ticket, _ = CounterTicket.objects.get_or_create(
            order=order,
            counter=counter,
            defaults={'company': order.company},
        )
        tickets.append(ticket)
    return tickets


def _ticket_queryset():
    from apps.orders.models import CounterTicket
    return CounterTicket.objects.select_related(
        'order', 'order__customer', 'counter', 'company'
    ).prefetch_related('order__items__product')


def _refresh_order_delivery_state(order, detail='Counter pickup updated.'):
    remaining = order.items.filter(is_deleted=False, picked_up_at__isnull=True).count()
    if remaining == 0:
        if order.order_status != OrderStatusChoices.DELIVERED:
            order.order_status = OrderStatusChoices.DELIVERED
            order.auto_ready_at = None
            order.save(update_fields=['order_status', 'auto_ready_at', 'updated_at'])
            OrderStatus.objects.create(
                order=order,
                status=OrderStatusChoices.DELIVERED,
                details='All counter items collected.',
                created_at=timezone.now(),
            )
    elif order.order_status < OrderStatusChoices.READY:
        order.order_status = OrderStatusChoices.READY
        order.save(update_fields=['order_status', 'updated_at'])
        OrderStatus.objects.create(
            order=order,
            status=OrderStatusChoices.READY,
            details=detail,
            created_at=timezone.now(),
        )


def _mark_ticket_collected(ticket):
    now = timezone.now()
    changed = False
    for item in ticket.order.items.filter(counter=ticket.counter, is_deleted=False, picked_up_at__isnull=True):
        item.picked_up_at = now
        item.save(update_fields=['picked_up_at'])
        changed = True
    if ticket.status != ticket.STATUS_COLLECTED or not ticket.collected_at:
        ticket.status = ticket.STATUS_COLLECTED
        ticket.collected_at = now
        ticket.save(update_fields=['status', 'collected_at', 'updated_at'])
        changed = True
    _refresh_order_delivery_state(ticket.order, detail=f'Counter ticket {ticket.ticket_number} collected.')
    return changed


def _sync_ticket_status_from_items(ticket):
    if ticket.remaining_items.count() == 0 and ticket.status != ticket.STATUS_COLLECTED:
        ticket.status = ticket.STATUS_COLLECTED
        ticket.collected_at = timezone.now()
        ticket.save(update_fields=['status', 'collected_at', 'updated_at'])


def _find_pickup_targets(code, company=None):
    code = (code or '').strip()
    if not code:
        return None, None
    item_qs = OrderItem.objects.select_related(
        'order', 'product', 'counter', 'order__customer', 'order__company'
    ).filter(is_deleted=False)
    ticket_qs = _ticket_queryset()
    if company is not None:
        item_qs = item_qs.filter(order__company=company)
        ticket_qs = ticket_qs.filter(company=company)
    ticket = ticket_qs.filter(scan_code__iexact=code).first() or ticket_qs.filter(ticket_number__iexact=code).first()
    item = None if ticket else item_qs.filter(pickup_code__iexact=code).first()
    return item, ticket



def _pickup_valid_date_for_target(target):
    order = getattr(target, 'order', None)
    scheduled_dt = getattr(order, 'scheduled_date', None) if order is not None else None
    base_dt = scheduled_dt or getattr(target, 'created_at', None) or getattr(order, 'created_at', None)
    if not base_dt:
        return timezone.localdate()
    if timezone.is_naive(base_dt):
        base_dt = timezone.make_aware(base_dt, timezone.get_current_timezone())
    return timezone.localtime(base_dt).date()


def _pickup_target_is_expired(target):
    return _pickup_valid_date_for_target(target) < timezone.localdate()


def _pickup_expired_message(target):
    valid_date = _pickup_valid_date_for_target(target)
    return f'This QR code was valid on {valid_date.strftime("%d-%m-%Y")} only and can no longer be used. T&C Applied.'


def _resolve_customer_cafe(customer, company, request=None):
    """
    Resolve the cafe for a web customer in this order of priority:
      1. An explicit customer.cafe attribute (rare, set programmatically).
      2. Session-stored web cafe chosen by the customer at cart/checkout time
         (stored by set_web_cafe via the cafe picker in cart.html).
      3. First cafe belonging to customer's building (original fallback).
      4. None — global / no cafe scope.
    """
    # 1. Explicit attribute
    cafe = getattr(customer, 'cafe', None)
    if cafe is not None:
        return cafe
    # 2. Session-stored choice — only available when request is passed
    if request is not None:
        _sess_cafe_id = request.session.get('web_cafe_id')
        if _sess_cafe_id:
            from apps.menu.models import Cafe as _CafeModel
            _c = _CafeModel.objects.filter(
                pk=_sess_cafe_id, company=company, is_active=True, is_deleted=False
            ).first()
            if _c:
                return _c
            # Invalid session value — clear it
            request.session.pop('web_cafe_id', None)
    # 3. Building fallback
    building = getattr(customer, 'building', None)
    if building is not None:
        from apps.menu.models import Cafe as _CafeModel
        return _CafeModel.objects.filter(
            building=building, company=company, is_active=True, is_deleted=False
        ).first()
    # 4. None
    return None


def _get_live_offer_for_product(company, product, cafe=None):
    """
    Return the best live Offer for a product.
    Priority: cafe-scoped single-product → cafe-scoped multi-product (M2M) →
              global single-product → global multi-product (M2M) →
              cafe-scoped site-wide (no products at all) → global site-wide (no products at all).

    Offers with M2M products set are product-specific and must ONLY match the
    products explicitly listed in them — they are never treated as site-wide.
    """
    from apps.menu.models import Offer

    # 1. cafe-scoped single-product offer
    if cafe:
        for offer in Offer.objects.filter(
            company=company, cafe=cafe, is_active=True, is_deleted=False, product=product
        ).order_by('-created_at'):
            if offer.is_live:
                return offer

    # 2. cafe-scoped multi-product (M2M) offer
    if cafe:
        for offer in Offer.objects.filter(
            company=company, cafe=cafe, is_active=True, is_deleted=False,
            product__isnull=True, products=product
        ).order_by('-created_at'):
            if offer.is_live:
                return offer

    # 3. global single-product offer
    for offer in Offer.objects.filter(
        company=company, is_active=True, is_deleted=False, product=product, cafe__isnull=True
    ).order_by('-created_at'):
        if offer.is_live:
            return offer

    # 4. global multi-product (M2M) offer
    for offer in Offer.objects.filter(
        company=company, is_active=True, is_deleted=False,
        product__isnull=True, products=product, cafe__isnull=True
    ).order_by('-created_at'):
        if offer.is_live:
            return offer

    # 5. cafe-scoped site-wide offer (no single-product FK, no M2M products at all)
    if cafe:
        for offer in Offer.objects.filter(
            company=company, cafe=cafe, is_active=True, is_deleted=False,
            product__isnull=True, products__isnull=True
        ).order_by('-created_at'):
            if offer.is_live:
                return offer

    # 6. global site-wide offer (no single-product FK, no M2M products at all)
    for offer in Offer.objects.filter(
        company=company, is_active=True, is_deleted=False,
        product__isnull=True, cafe__isnull=True, products__isnull=True
    ).order_by('-created_at'):
        if offer.is_live:
            return offer

    return None


def _preload_cart_products_and_offers(company, cart, cafe=None):
    from apps.menu.models import Offer

    product_ids = []
    for raw_product_id in (cart or {}).keys():
        try:
            product_ids.append(int(raw_product_id))
        except (TypeError, ValueError):
            continue

    if not product_ids:
        return {}, {}

    products = list(
        Product.objects.select_related('category')
        .prefetch_related('food_type')
        .filter(pk__in=product_ids, is_deleted=False, company=company)
    )
    product_map = {product.pk: product for product in products}
    if not product_map:
        return {}, {}

    offer_qs = Offer.objects.filter(
        company=company,
        is_active=True,
        is_deleted=False,
    )
    if cafe:
        offer_qs = offer_qs.filter(Q(cafe=cafe) | Q(cafe__isnull=True))
    else:
        offer_qs = offer_qs.filter(cafe__isnull=True)

    offers = list(
        offer_qs.select_related('product', 'cafe')
        .prefetch_related('products')
        .order_by('-created_at')
    )

    cafe_id = getattr(cafe, 'pk', None)
    all_product_ids = list(product_map.keys())
    best_offer_by_product = {}
    best_priority_by_product = {}

    for offer in offers:
        if not offer.is_live:
            continue

        m2m_product_ids = [p.pk for p in offer.products.all()]

        if cafe_id and offer.cafe_id == cafe_id:
            if offer.product_id is not None:
                priority = 1
                target_product_ids = [offer.product_id]
            elif m2m_product_ids:
                priority = 2
                target_product_ids = m2m_product_ids
            else:
                priority = 5
                target_product_ids = all_product_ids
        elif offer.cafe_id is None:
            if offer.product_id is not None:
                priority = 3
                target_product_ids = [offer.product_id]
            elif m2m_product_ids:
                priority = 4
                target_product_ids = m2m_product_ids
            else:
                priority = 6
                target_product_ids = all_product_ids
        else:
            continue

        for target_product_id in target_product_ids:
            if target_product_id not in product_map:
                continue
            current_priority = best_priority_by_product.get(target_product_id)
            if current_priority is None or priority < current_priority:
                best_priority_by_product[target_product_id] = priority
                best_offer_by_product[target_product_id] = offer

    return product_map, best_offer_by_product


def _get_kiosk_scope(request, company):
    from apps.core.models import Building
    from apps.menu.models import Cafe
    building = None
    cafe = None
    raw_building = (request.GET.get('building') or '').strip()
    raw_cafe = (request.GET.get('cafe') or '').strip()
    if raw_building:
        request.session['kiosk_building_id'] = raw_building
        if not raw_cafe:
            request.session.pop('kiosk_cafe_id', None)
    if raw_cafe:
        request.session['kiosk_cafe_id'] = raw_cafe
    building_id = request.session.get('kiosk_building_id')
    cafe_id = request.session.get('kiosk_cafe_id')
    if building_id:
        building = Building.objects.filter(pk=building_id, company=company, is_deleted=False, is_active=True).first()
        if not building:
            request.session.pop('kiosk_building_id', None)
    if cafe_id:
        cafe = Cafe.objects.select_related('building').filter(pk=cafe_id, company=company, is_deleted=False, is_active=True).first()
        if not cafe:
            request.session.pop('kiosk_cafe_id', None)
        elif building and cafe.building_id and cafe.building_id != building.pk:
            cafe = None
            request.session.pop('kiosk_cafe_id', None)
    if cafe and cafe.building_id and building is None:
        building = cafe.building
        request.session['kiosk_building_id'] = str(building.pk)
    return building, cafe


def _resolve_product_counter(product, cafe=None):
    mappings = product.counter_mappings.select_related('counter', 'counter__cafe').filter(is_active=True, counter__is_deleted=False, counter__is_active=True).order_by('position_order', 'id')
    if cafe is not None:
        scoped = mappings.filter(counter__cafe=cafe).first()
        if scoped:
            return scoped.counter
    first = mappings.first()
    return first.counter if first else None


def _apply_offer_to_line(offer, unit_price, qty, cart_subtotal=None):
    """
    Return (effective_line_total, offer_saving) for the given offer.
    PERCENT  → % off the line total (with optional max_discount cap).
    FREE     → entire line is free.
    BOGO     → every 2nd unit is free.
    FLAT/CART → handled at cart level, not per-line; returns gross unchanged.
    cart_subtotal is used to check min_order_value thresholds.
    """
    if offer is None:
        return unit_price * qty, Decimal('0.00')

    gross = unit_price * qty

    # Minimum order threshold check
    if offer.min_order_value and cart_subtotal is not None:
        if cart_subtotal < offer.min_order_value:
            return gross, Decimal('0.00')

    if offer.offer_type == offer.TYPE_FREE:
        return Decimal('0.00'), gross
    if offer.offer_type == offer.TYPE_BOGO:
        free_units = qty // 2
        saving = unit_price * free_units
        return max(Decimal('0.00'), gross - saving), saving
    if offer.offer_type == offer.TYPE_PERCENT:
        rate = min(Decimal('100'), max(Decimal('0'), offer.value))
        saving = (gross * rate / Decimal('100')).quantize(Decimal('0.01'))
        if offer.max_discount:
            saving = min(saving, offer.max_discount)
        return max(Decimal('0.00'), gross - saving), saving
    # FLAT/CART are cart-level — handled in _build_cart_summary
    return gross, Decimal('0.00')


def _free_meal_product_ids_for_company(company):
    if not company:
        return set()
    return set(company.free_meal_products.filter(is_deleted=False).values_list('pk', flat=True))


def _eligible_snapshot_subtotal_for_company(company, customer, snapshot):
    eligible_product_ids = _free_meal_product_ids_for_company(company)
    if not eligible_product_ids:
        snapshot_after_offer = _money(snapshot.get('after_offer_subtotal'))
        if snapshot_after_offer > Decimal('0.00'):
            return snapshot_after_offer
        eligible_subtotal = Decimal('0.00')
        for item_data in snapshot.get('items', []):
            eligible_subtotal += _money(item_data.get('line_total'))
        return eligible_subtotal

    eligible_subtotal = Decimal('0.00')
    for item_data in snapshot.get('items', []):
        try:
            product_id = int(item_data.get('product_id') or 0)
        except (TypeError, ValueError):
            product_id = 0
        if product_id in eligible_product_ids:
            eligible_subtotal += _money(item_data.get('line_total'))
    return eligible_subtotal


def _build_cart_summary(customer, cart, benefit_date=None, request=None):
    company = _fresh_company(customer)
    cart = cart or {}
    items = []
    subtotal = Decimal('0.00')
    offer_discount = Decimal('0.00')
    eligible_product_ids = _free_meal_product_ids_for_company(company)
    eligible_subtotal = Decimal('0.00')
    building = getattr(customer, 'building', None)
    cafe = _resolve_customer_cafe(customer, company, request=request)

    # FIX-1: Pre-load the set of offer PKs this customer has already used.
    # The billing engine itself must not apply used offers — not just the UI.
    from apps.menu.models import OfferUsage as _OfferUsage, Offer as _OfferConst
    _today = timezone.localdate()
    _used_offer_ids = set(
        _OfferUsage.objects.filter(customer=customer, used_on=_today)
        .values_list('offer_id', flat=True)
    )
    # Use model constants — avoids case-mismatch if DB has mixed-case offer_type values.
    # ALL offer types are once-per-day per customer.
    ONE_USE_TYPES = {_OfferConst.TYPE_BOGO, _OfferConst.TYPE_FREE, _OfferConst.TYPE_PERCENT, _OfferConst.TYPE_FLAT, _OfferConst.TYPE_CART}
    _applied_one_use_offer_ids = set()

    _cart_products, _live_offers = _preload_cart_products_and_offers(company, cart, cafe=cafe)

    for product_id, item in list(cart.items()):
        try:
            product_pk = int(product_id)
        except (TypeError, ValueError):
            cart.pop(product_id, None)
            continue

        product = _cart_products.get(product_pk)
        if not product:
            cart.pop(product_id, None)
            continue

        try:
            qty = max(0, int(item.get('qty', 0)))
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            cart.pop(product_id, None)
            continue

        min_qty = _get_order_min_qty(product)
        max_qty = _get_web_max_qty(product)
        if max_qty <= 0:
            cart.pop(product_id, None)
            continue
        qty = max(min_qty, min(qty, max_qty))
        item['qty'] = qty

        site_price = _get_site_price(product, company, building=building, cafe=cafe)
        live_offer = _live_offers.get(product.pk)
        if live_offer and live_offer.pk in _used_offer_ids:
            live_offer = None
        if live_offer and live_offer.offer_type in ONE_USE_TYPES and live_offer.pk in _applied_one_use_offer_ids:
            live_offer = None
        # Pass running subtotal so _apply_offer_to_line can evaluate min_order_value.
        # subtotal here is the gross accumulated so far (before this line), which is
        # a conservative estimate — a full pre-pass would be ideal but this prevents
        # the silent zero-discount that happened when cart_subtotal was None.
        effective_line_total, line_saving = _apply_offer_to_line(live_offer, site_price, qty, cart_subtotal=subtotal + site_price * qty)
        line_total = effective_line_total
        is_free_meal_eligible = not eligible_product_ids or product.pk in eligible_product_ids
        subtotal += site_price * qty             # gross before offer
        offer_discount += line_saving
        if is_free_meal_eligible:
            eligible_subtotal += line_total
        if live_offer and line_saving > 0 and live_offer.offer_type in ONE_USE_TYPES:
            _applied_one_use_offer_ids.add(live_offer.pk)
        items.append({
            'product': product,
            'qty': qty,
            'site_price': site_price,
            'line_total': line_total,
            'gross_line_total': site_price * qty,
            'line_saving': line_saving,
            'offer': live_offer,
            'is_free_meal_eligible': is_free_meal_eligible,
        })

    packing = sum((_money(item['product'].packing_price) * item['qty']) for item in items)

    # ── Cart-level FLAT / CART offer applied after per-line totals ──
    # FLAT and CART are once-per-day per customer — blocked if used today.
    from apps.menu.models import Offer as _Offer
    cart_level_offer = None
    cart_offer_saving = Decimal('0.00')
    _cafe = cafe
    for _offer_type in (_Offer.TYPE_FLAT, _Offer.TYPE_CART):
        _qs = _Offer.objects.filter(
            company=company, is_active=True, is_deleted=False, offer_type=_offer_type
        ).order_by('-created_at')
        if _cafe:
            for _o in _qs.filter(cafe=_cafe):
                if _o.is_live and _o.pk not in _used_offer_ids:
                    cart_level_offer = _o; break
        if not cart_level_offer:
            for _o in _qs.filter(cafe__isnull=True):
                if _o.is_live and _o.pk not in _used_offer_ids:
                    cart_level_offer = _o; break
        if cart_level_offer:
            break
    if cart_level_offer:
        _min = cart_level_offer.min_order_value or Decimal('0')
        if subtotal >= _min:
            if cart_level_offer.offer_type == _Offer.TYPE_FLAT:
                cart_offer_saving = min(cart_level_offer.value, subtotal)
            elif cart_level_offer.offer_type == _Offer.TYPE_CART:
                _rate = min(Decimal('100'), max(Decimal('0'), cart_level_offer.value))
                cart_offer_saving = (subtotal * _rate / Decimal('100')).quantize(Decimal('0.01'))
                if cart_level_offer.max_discount:
                    cart_offer_saving = min(cart_offer_saving, cart_level_offer.max_discount)
        else:
            cart_level_offer = None

    offer_discount += cart_offer_saving
    after_offer_subtotal = subtotal - offer_discount
    gross_total = after_offer_subtotal + packing
    if not eligible_product_ids:
        eligible_subtotal = after_offer_subtotal
    benefit_date = benefit_date or timezone.localdate()
    subsidy = customer.company_cover_for_amount(eligible_subtotal, benefit_date)
    my_pay = max(Decimal('0.00'), gross_total - subsidy)
    bill_to_company = subsidy
    company_cover_label = 'Company-paid meal' if customer.meal_benefit == customer.MEAL_BENEFIT_COMPANY_PAY and subsidy > 0 else 'Company subsidy'
    benefit_used_today = (
        customer.meal_benefit in (customer.MEAL_BENEFIT_COMPANY_PAY, customer.MEAL_BENEFIT_SUBSIDY) and
        customer.benefit_limit_for_date(benefit_date) > 0 and
        customer.benefit_used_on(benefit_date)
    )

    return {
        'cart': cart,
        'items': items,
        'subtotal': subtotal,
        'offer_discount': offer_discount,
        'after_offer_subtotal': after_offer_subtotal,
        'cart_level_offer': cart_level_offer,
        'cart_offer_saving': cart_offer_saving,
        'eligible_subtotal': eligible_subtotal,
        'packing': packing,
        'subsidy': subsidy,
        'my_pay': my_pay,
        'bill_to_company': bill_to_company,
        'company_cover_label': company_cover_label,
        'benefit_used_today': benefit_used_today,
        'total': gross_total,
        'cart_count': sum(item['qty'] for item in items),
    }




def _allowed_payment_modes(company, customer, my_pay=None, bill_to_company=None):
    payment_modes = []
    my_pay = _money(my_pay)
    bill_to_company = _money(bill_to_company)
    if my_pay <= Decimal('0.00') and bill_to_company > Decimal('0.00'):
        return [(PaymentModeChoices.COMPANY, 'Company Covered')]
    if my_pay <= Decimal('0.00') and bill_to_company <= Decimal('0.00'):
        payment_modes.append((PaymentModeChoices.WALLET, 'Wallet / Free Checkout'))
        if getattr(customer, 'monthly_payment', False) and getattr(company, 'monthly_payment', False):
            payment_modes.append((PaymentModeChoices.MONTHLY, 'Monthly Billing'))
        return payment_modes
    # Company-level payment mode controls
    if getattr(company, 'cod_payment', False) or getattr(customer, 'cod_payment', False):
        payment_modes.append((PaymentModeChoices.CASH, 'Cash on Delivery'))
    if getattr(customer, 'monthly_payment', False) and getattr(company, 'monthly_payment', False):
        payment_modes.append((PaymentModeChoices.MONTHLY, 'Monthly Billing'))
    if getattr(company, 'online_payment', True):
        payment_modes.append((PaymentModeChoices.ONLINE, 'Online Payment'))
    if not payment_modes:
        # fallback — always at least one mode
        payment_modes.append((PaymentModeChoices.ONLINE, 'Online Payment'))
    return payment_modes



def _parse_scheduled_datetime(value):
    value = (value or '').strip()
    if not value:
        return None

    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            naive = datetime.strptime(value, fmt)
            if fmt == '%Y-%m-%d':
                naive = naive.replace(hour=12, minute=0)
            return timezone.make_aware(naive, timezone.get_current_timezone())
        except (TypeError, ValueError):
            continue
    return None



def _progress_steps(order):
    steps = [
        (OrderStatusChoices.PENDING, 'Placed', 'We have received your order.'),
        (OrderStatusChoices.CONFIRMED, 'Confirmed', 'The cafeteria team has acknowledged it.'),
        (OrderStatusChoices.PREPARING, 'Preparing', 'Your food is being prepared.'),
        (OrderStatusChoices.READY, 'Ready', 'Ready for pickup or dispatch.'),
        (OrderStatusChoices.DELIVERED, 'Delivered', 'Order completed successfully.'),
    ]
    current = order.order_status
    progress = []
    for status_value, label, note in steps:
        progress.append({
            'label': label,
            'note': note,
            'complete': current >= status_value and current != OrderStatusChoices.CANCELLED,
            'current': current == status_value,
        })
    return progress




def _promote_due_ready_orders(customer=None, company=None):
    from apps.orders.models import CounterTicket

    now = timezone.now()
    qs = Order.objects.filter(
        order_status=OrderStatusChoices.CONFIRMED,
        is_deleted=False,
        auto_ready_at__isnull=False,
        auto_ready_at__lte=now,
    )
    if customer is not None:
        qs = qs.filter(customer=customer)
    elif company is not None:
        qs = qs.filter(company=company)

    for order in qs:
        order.order_status = OrderStatusChoices.READY
        order.auto_ready_at = None
        order.save(update_fields=['order_status', 'auto_ready_at', 'updated_at'])

        order.counter_tickets.filter(
            status__in=[CounterTicket.STATUS_PENDING, CounterTicket.STATUS_PREPARING]
        ).update(status=CounterTicket.STATUS_READY, updated_at=now)

        OrderStatus.objects.create(
            order=order,
            status=OrderStatusChoices.READY,
            details='Auto-marked ready after configured preparation time.',
            created_at=now,
        )

def _phonepe_config():
    return {
        'merchant_id': settings.PHONEPE_MERCHANT_ID,
        'salt_key':    settings.PHONEPE_SALT_KEY,
        'salt_index':  settings.PHONEPE_SALT_INDEX,
        'mode':        settings.PHONEPE_MODE,
    }


def _razorpay_config():
    return {
        'key_id': getattr(settings, 'RAZORPAY_KEY_ID', ''),
        'key_secret': getattr(settings, 'RAZORPAY_KEY_SECRET', ''),
    }


def _find_existing_order_with_retry(merchant_order_id, attempts=3, delay_seconds=1.0):
    """
    Briefly re-check the local DB for an order that may be created by the
    PhonePe webhook while the browser redirect is being processed.
    """
    for attempt in range(1, max(1, int(attempts)) + 1):
        order = Order.objects.filter(order_number=merchant_order_id, is_deleted=False).first()
        if order:
            return order
        if attempt < attempts:
            time.sleep(delay_seconds)
    return None


def _fetch_phonepe_order_status_with_retry(merchant_order_id, attempts=3, delay_seconds=1.0):
    """
    PhonePe status can be briefly unavailable right after redirect.
    Retry a few times before treating it as a hard failure.
    """
    last_exc = None
    for attempt in range(1, max(1, int(attempts)) + 1):
        try:
            return fetch_phonepe_order_status(
                merchant_order_id=merchant_order_id,
                **_phonepe_config(),
            )
        except PhonePeError as exc:
            last_exc = exc
            logger.warning(
                'PhonePe status lookup failed for %s on attempt %s/%s: %s',
                merchant_order_id,
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                time.sleep(delay_seconds)
    if last_exc:
        raise last_exc
    raise PhonePeError('Unable to verify PhonePe payment status.')


def _phonepe_test_mode_enabled():
    return _phonepe_config().get('mode', 'test').strip().lower() != 'live'


def _snapshot_age_seconds(snapshot):
    created_at_raw = (snapshot or {}).get('created_at') or ''
    if not created_at_raw:
        return None
    try:
        created_at = datetime.fromisoformat(created_at_raw)
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(created_at):
        created_at = timezone.make_aware(created_at, timezone.get_current_timezone())
    return max(0.0, (timezone.now() - created_at).total_seconds())


def _can_reconcile_phonepe_testmode_locally(snapshot, merchant_order_id):
    """
    Developer/test mode has no webhook and the sandbox status API can 500 even
    after a successful redirect. In that mode, allow a tightly-scoped local
    reconciliation using the still-present pending snapshot instead of treating
    the first status failure as a final payment failure.
    """
    if not _phonepe_test_mode_enabled():
        return False
    snapshot = snapshot or {}
    if (snapshot.get('merchant_ref') or '').strip() != (merchant_order_id or '').strip():
        return False
    if not snapshot.get('gateway_redirect_url'):
        return False
    if not snapshot.get('gateway_order_id'):
        return False
    return True


def _apply_phonepe_state_to_order(order, payload, source=''):
    """
    Idempotent PhonePe state sync for an already-existing Order.

    Called by phonepe_callback when the order record already exists in the
    database — either because a prior callback hit already created it, or the
    webhook path created it before the customer browser returned.

    Applies the minimal set of field updates required to keep payment_status
    and order_status consistent with the gateway state.  Uses get_or_create
    on OrderStatus so it is safe to call more than once.

    Returns the normalised state string ('COMPLETED', 'FAILED', or '').
    """
    state = str(payload.get('state') or '').upper()
    changed_fields = []

    if state == 'COMPLETED':
        if order.payment_status != 'paid':
            order.payment_status = 'paid'
            changed_fields.append('payment_status')
        if order.order_status == OrderStatusChoices.PENDING:
            order.order_status = OrderStatusChoices.CONFIRMED
            changed_fields.append('order_status')
            OrderStatus.objects.get_or_create(
                order=order,
                status=OrderStatusChoices.CONFIRMED,
                defaults={
                    'details': f'Auto-confirmed by PhonePe {source} callback.',
                    'created_at': timezone.now(),
                },
            )
    elif state == 'FAILED':
        if order.payment_status not in ('paid', 'failed'):
            order.payment_status = 'failed'
            changed_fields.append('payment_status')

    if changed_fields:
        order.save(update_fields=changed_fields)

    return state


SESSION_KEY_PENDING_ONLINE_CHECKOUT = 'pending_online_checkout'
SESSION_KEY_PENDING_KIOSK_ONLINE_CHECKOUT = 'pending_kiosk_online_checkout'
SESSION_KEY_LAST_KIOSK_ORDER = 'last_kiosk_online_order'
PENDING_PHONEPE_SNAPSHOT_CACHE_TTL = 6 * 60 * 60


def _pending_phonepe_snapshot_cache_key(source, merchant_ref):
    merchant_ref = (merchant_ref or '').strip()
    if not merchant_ref:
        return ''
    return f'neverq:phonepe:{source}:{merchant_ref}'


def _save_pending_phonepe_snapshot(source, snapshot):
    merchant_ref = (snapshot or {}).get('merchant_ref', '')
    cache_key = _pending_phonepe_snapshot_cache_key(source, merchant_ref)
    if cache_key:
        cache.set(cache_key, snapshot, PENDING_PHONEPE_SNAPSHOT_CACHE_TTL)


def _get_pending_phonepe_snapshot(source, merchant_ref):
    cache_key = _pending_phonepe_snapshot_cache_key(source, merchant_ref)
    if not cache_key:
        return None
    snapshot = cache.get(cache_key)
    return snapshot if isinstance(snapshot, dict) else None


def _clear_pending_phonepe_snapshot(source, merchant_ref):
    cache_key = _pending_phonepe_snapshot_cache_key(source, merchant_ref)
    if cache_key:
        cache.delete(cache_key)


def _save_pending_online_checkout(request, snapshot):
    request.session[SESSION_KEY_PENDING_ONLINE_CHECKOUT] = snapshot
    request.session.modified = True
    _save_pending_phonepe_snapshot('web', snapshot)


def _get_pending_online_checkout(request):
    snapshot = request.session.get(SESSION_KEY_PENDING_ONLINE_CHECKOUT)
    return snapshot if isinstance(snapshot, dict) else None


def _clear_pending_online_checkout(request):
    snapshot = request.session.get(SESSION_KEY_PENDING_ONLINE_CHECKOUT)
    merchant_ref = (snapshot or {}).get('merchant_ref', '')
    request.session.pop(SESSION_KEY_PENDING_ONLINE_CHECKOUT, None)
    request.session.modified = True
    _clear_pending_phonepe_snapshot('web', merchant_ref)


def _save_pending_kiosk_online_checkout(request, snapshot):
    request.session[SESSION_KEY_PENDING_KIOSK_ONLINE_CHECKOUT] = snapshot
    request.session.modified = True
    _save_pending_phonepe_snapshot('kiosk', snapshot)


def _get_pending_kiosk_online_checkout(request):
    snapshot = request.session.get(SESSION_KEY_PENDING_KIOSK_ONLINE_CHECKOUT)
    return snapshot if isinstance(snapshot, dict) else None


def _clear_pending_kiosk_online_checkout(request):
    snapshot = request.session.get(SESSION_KEY_PENDING_KIOSK_ONLINE_CHECKOUT)
    merchant_ref = (snapshot or {}).get('merchant_ref', '')
    request.session.pop(SESSION_KEY_PENDING_KIOSK_ONLINE_CHECKOUT, None)
    request.session.modified = True
    _clear_pending_phonepe_snapshot('kiosk', merchant_ref)


def _set_last_kiosk_order(request, *, merchant_ref, order_id, company_id, kiosk_slug=''):
    request.session[SESSION_KEY_LAST_KIOSK_ORDER] = {
        'merchant_ref': merchant_ref,
        'order_id': int(order_id),
        'company_id': int(company_id),
        'kiosk_slug': kiosk_slug or '',
    }
    request.session.modified = True


def _get_last_kiosk_order(request):
    snapshot = request.session.get(SESSION_KEY_LAST_KIOSK_ORDER)
    return snapshot if isinstance(snapshot, dict) else None


def _clear_last_kiosk_order(request):
    request.session.pop(SESSION_KEY_LAST_KIOSK_ORDER, None)
    request.session.modified = True


def _build_pending_online_checkout_snapshot(
    *,
    customer,
    company,
    summary,
    coupon,
    coupon_discount,
    my_pay,
    total_amount,
    wallet_apply,
    points_apply,
    payment_mode,
    order_type,
    scheduled_dt,
    request,
):
    cafe = _resolve_customer_cafe(customer, company, request=request)
    merchant_ref = _next_order_number('WEB', company=company)

    return {
        'merchant_ref': merchant_ref,
        'customer_id': customer.pk,
        'company_id': company.pk,
        'cafe_id': cafe.pk if cafe else None,
        'coupon_id': coupon.pk if coupon else 0,
        'coupon_discount': str(coupon_discount),
        'subtotal': str(summary['subtotal']),
        'offer_discount': str(summary['offer_discount']),
        'packing': str(summary['packing']),
        'bill_to_company': str(summary['bill_to_company']),
        'eligible_subtotal': str(summary.get('eligible_subtotal', Decimal('0.00'))),
        'my_pay': str(my_pay),
        'total_amount': str(total_amount),
        'wallet_used': str(wallet_apply),
        'points_redeemed': int(points_apply),
        'payment_mode': payment_mode,
        'order_type': int(order_type),
        'scheduled_dt': scheduled_dt.isoformat() if scheduled_dt else '',
        'cart_level_offer_id': summary['cart_level_offer'].pk if summary.get('cart_level_offer') else None,
        'items': [
            {
                'product_id': item['product'].pk,
                'qty': int(item['qty']),
                'site_price': str(item.get('site_price', item['product'].price)),
                'line_total': str(item['line_total']),
                'line_saving': str(item.get('line_saving', Decimal('0.00'))),
                'offer_id': item['offer'].pk if item.get('offer') else None,
            }
            for item in summary['items']
        ],
        'gateway_order_id': '',
        'gateway_redirect_url': '',
        'created_order_id': None,
        'created_at': timezone.now().isoformat(),
    }




def _build_pending_kiosk_online_checkout_snapshot(
    *,
    company,
    cafe,
    kiosk_slug,
    customer_name,
    customer_phone,
    gross_subtotal,
    effective_subtotal,
    total_offer_discount,
    items,
):
    merchant_ref = _next_order_number('KIO', company=company)

    return {
        'source': 'kiosk',
        'merchant_ref': merchant_ref,
        'company_id': company.pk,
        'cafe_id': cafe.pk if cafe else None,
        'kiosk_slug': kiosk_slug or '',
        'customer_name': customer_name,
        'customer_phone': customer_phone,
        'subtotal': str(gross_subtotal),
        'offer_discount': str(total_offer_discount),
        'my_pay': str(effective_subtotal),
        'total_amount': str(effective_subtotal),
        'payment_mode': PaymentModeChoices.ONLINE,
        'order_type': 1,
        'items': [
            {
                'product_id': item['product'].pk,
                'qty': int(item['qty']),
                'site_price': str(item.get('site_price', item['product'].price)),
                'line_total': str(item['line_total']),
                'line_saving': str(item.get('line_saving', Decimal('0.00'))),
                'offer_id': item['offer'].pk if item.get('offer') else None,
            }
            for item in items
        ],
        'gateway_order_id': '',
        'gateway_redirect_url': '',
        'created_order_id': None,
        'created_at': timezone.now().isoformat(),
    }

def _record_offer_usage_for_snapshot(customer, order, snapshot):
    from apps.menu.models import Offer, OfferUsage

    usage_date = timezone.localdate()
    offer_ids = set()

    for item in snapshot.get('items', []):
        offer_id = item.get('offer_id')
        if offer_id:
            offer_ids.add(offer_id)

    cart_offer_id = snapshot.get('cart_level_offer_id')
    if cart_offer_id:
        offer_ids.add(cart_offer_id)

    if not offer_ids:
        return

    one_use_types = {
        Offer.TYPE_BOGO,
        Offer.TYPE_FREE,
        Offer.TYPE_PERCENT,
        Offer.TYPE_FLAT,
        Offer.TYPE_CART,
    }

    for offer in Offer.objects.filter(pk__in=offer_ids, is_deleted=False):
        if offer.offer_type in one_use_types:
            OfferUsage.objects.get_or_create(
                offer=offer,
                customer=customer,
                used_on=usage_date,
                defaults={'order': order},
            )


def _apply_wallet_and_points_to_customer(customer, order, wallet_apply, points_apply):
    from apps.accounts.models import WalletTransaction as _WT

    wallet_apply = _money(wallet_apply)
    points_apply = int(points_apply or 0)

    if wallet_apply > 0:
        with transaction.atomic():
            locked = customer.__class__._default_manager.select_for_update().get(pk=customer.pk)
            current_wallet = locked.wallet_balance or Decimal('0.00')
            customer.__class__.objects.filter(pk=customer.pk).update(
                wallet_balance=max(Decimal('0.00'), current_wallet - wallet_apply)
            )
        customer.refresh_from_db(fields=['wallet_balance', 'royalty_points'])
        _WT.objects.create(
            customer=customer,
            txn_type=_WT.TYPE_ORDER_DEBIT,
            wallet_delta=-wallet_apply,
            balance_after=customer.wallet_balance,
            points_after=customer.royalty_points,
            order_ref=order.order_number,
            note=f'Wallet used for order {order.order_number}',
            created_by='customer',
        )

    if points_apply > 0:
        with transaction.atomic():
            locked = customer.__class__._default_manager.select_for_update().get(pk=customer.pk)
            current_points = locked.royalty_points or 0
            customer.__class__.objects.filter(pk=customer.pk).update(
                royalty_points=max(0, current_points - points_apply)
            )
        customer.refresh_from_db(fields=['wallet_balance', 'royalty_points'])
        _WT.objects.create(
            customer=customer,
            txn_type=_WT.TYPE_ROYALTY_REDEEM,
            points_delta=-points_apply,
            wallet_delta=Decimal(str(points_apply)),
            balance_after=customer.wallet_balance,
            points_after=customer.royalty_points,
            order_ref=order.order_number,
            note=f'{points_apply} royalty points redeemed for order {order.order_number}',
            created_by='customer',
        )


def _recompute_wallet_points_from_locked_customer(
    *,
    customer,
    company,
    my_pay,
    total_amount,
    payment_mode,
    use_wallet,
    use_points,
):
    wallet_apply = Decimal('0.00')
    points_apply = 0

    if payment_mode in (PaymentModeChoices.MONTHLY,):
        return my_pay, total_amount, wallet_apply, points_apply

    wallet_bal = _money(getattr(customer, 'wallet_balance', 0))
    try:
        points_bal = int(getattr(customer, 'royalty_points', 0) or 0)
    except (TypeError, ValueError):
        points_bal = 0
    min_redeem = int(getattr(company, 'royalty_min_redeem', 100) or 100)
    max_pct = int(getattr(company, 'royalty_max_redeem_pct', 50) or 50)

    if use_wallet and wallet_bal > 0 and my_pay > 0:
        wallet_apply = min(wallet_bal, my_pay)
        my_pay = max(Decimal('0.00'), my_pay - wallet_apply)
        total_amount = max(Decimal('0.00'), total_amount - wallet_apply)

    if use_points and getattr(company, 'royalty_enabled', False) and points_bal >= min_redeem and my_pay > 0:
        points_apply = int(min(points_bal, my_pay * Decimal(str(max_pct)) / 100))
        pts_value = Decimal(str(points_apply))
        my_pay = max(Decimal('0.00'), my_pay - pts_value)
        total_amount = max(Decimal('0.00'), total_amount - pts_value)

    return my_pay, total_amount, wallet_apply, points_apply


def _notify_new_order(order, customer_name):
    try:
        from apps.accounts.models import StaffUser
        from apps.core.models import Notification

        staff_qs = StaffUser.objects.filter(
            company=order.company,
            is_active=True,
            role__in=[StaffUser.ROLE_ADMIN, StaffUser.ROLE_POS, StaffUser.ROLE_CAFEMAN],
        )
        for staff in staff_qs:
            Notification.objects.create(
                company=order.company,
                staff_user=staff,
                notif_type=Notification.TYPE_ORDER,
                title=f'New Order #{order.order_number}',
                message=f'{customer_name} placed an order for ₹{order.total_amount}',
                link=f'/dashboard/orders/{order.pk}/',
            )
    except Exception as _exc:
        logger.warning('Order notification failed for %s: %s', order.order_number, _exc)


def _create_new_order_from_pending_snapshot(snapshot, transaction_id=''):
    from apps.accounts.models import Customer
    from apps.core.models import Coupon
    from apps.menu.models import Cafe as CafeModel

    created_order_id = snapshot.get('created_order_id')
    if created_order_id:
        existing = Order.objects.filter(pk=created_order_id, is_deleted=False).first()
        if existing:
            return existing

    merchant_ref = (snapshot.get('merchant_ref') or '').strip()
    existing = Order.objects.filter(
        order_number=merchant_ref,
        customer_id=snapshot.get('customer_id'),
        company_id=snapshot.get('company_id'),
        is_deleted=False,
    ).first()
    if existing:
        return existing

    customer = Customer.objects.select_related('company').get(pk=snapshot['customer_id'])
    company = Company.objects.get(pk=snapshot['company_id'])

    cafe = None
    if snapshot.get('cafe_id'):
        cafe = CafeModel.objects.filter(
            pk=snapshot['cafe_id'],
            company=company,
            is_deleted=False,
            is_active=True,
        ).first()

    scheduled_dt = None
    scheduled_raw = (snapshot.get('scheduled_dt') or '').strip()
    if scheduled_raw:
        scheduled_dt = datetime.fromisoformat(scheduled_raw)
        if timezone.is_naive(scheduled_dt):
            scheduled_dt = timezone.make_aware(scheduled_dt, timezone.get_current_timezone())

    subtotal = _money(snapshot.get('subtotal'))
    offer_discount = _money(snapshot.get('offer_discount'))
    packing = _money(snapshot.get('packing'))
    bill_to_company = _money(snapshot.get('bill_to_company'))
    my_pay = _money(snapshot.get('my_pay'))
    total_amount = _money(snapshot.get('total_amount'))
    coupon_discount = _money(snapshot.get('coupon_discount'))
    wallet_used = _money(snapshot.get('wallet_used'))
    points_redeemed = int(snapshot.get('points_redeemed') or 0)
    payment_mode = snapshot.get('payment_mode') or PaymentModeChoices.ONLINE
    order_type = int(snapshot.get('order_type') or 0)

    create_kwargs = {
        'company': company,
        'customer': customer,
        'cafe': cafe,
        'coupon_id': int(snapshot.get('coupon_id') or 0),
        'coupon_discount': coupon_discount,
        'subtotal': subtotal,
        'offer_discount': offer_discount,
        'shipping_cost': packing,
        'bill_to_company': bill_to_company,
        'my_pay': my_pay,
        'total_amount': total_amount,
        'wallet_used': wallet_used,
        'points_redeemed': points_redeemed,
        'payment_mode': payment_mode,
        'payment_status': 'paid',
        'order_type': order_type,
        'order_status': OrderStatusChoices.CONFIRMED,
        'scheduled_date': scheduled_dt,
        'order_number': merchant_ref,
        'transaction_id': transaction_id or snapshot.get('gateway_order_id', ''),
    }

    with transaction.atomic():
        customer = Customer.objects.select_related('company').select_for_update().get(pk=customer.pk)
        create_kwargs['customer'] = customer

        gross_total = max(Decimal('0.00'), subtotal - offer_discount + packing)
        benefit_date = timezone.localdate(scheduled_dt) if scheduled_dt else timezone.localdate()
        eligible_subtotal = _eligible_snapshot_subtotal_for_company(company, customer, snapshot)
        bill_to_company = customer.company_cover_for_amount(eligible_subtotal, benefit_date)

        locked_coupon = None
        if snapshot.get('coupon_id') and coupon_discount > 0:
            locked_coupon = Coupon.objects.select_for_update().filter(
                pk=snapshot['coupon_id'],
            ).filter(Q(company=company) | Q(company__isnull=True)).first()
            if not locked_coupon or not locked_coupon.is_valid:
                raise ValueError('Coupon is no longer valid.')
            if locked_coupon.usage_limit > 0:
                used_by_customer = Order.objects.filter(
                    customer=customer,
                    coupon_id=locked_coupon.pk,
                    is_deleted=False,
                ).count()
                if used_by_customer >= locked_coupon.usage_limit:
                    raise ValueError('Coupon usage limit already reached for this employee.')
            coupon_discount = locked_coupon.calculate_discount(max(Decimal('0.00'), subtotal - offer_discount))

        my_pay = max(Decimal('0.00'), gross_total - bill_to_company - coupon_discount)
        total_amount = max(Decimal('0.00'), gross_total - coupon_discount)
        my_pay, total_amount, wallet_used, points_redeemed = _recompute_wallet_points_from_locked_customer(
            customer=customer,
            company=company,
            my_pay=my_pay,
            total_amount=total_amount,
            payment_mode=payment_mode,
            use_wallet=wallet_used > 0,
            use_points=points_redeemed > 0,
        )
        if my_pay <= Decimal('0.00') and bill_to_company <= Decimal('0.00') and (wallet_used > 0 or points_redeemed > 0):
            payment_mode = PaymentModeChoices.WALLET
        create_kwargs.update({
            'coupon_id': locked_coupon.pk if locked_coupon else 0,
            'coupon_discount': coupon_discount,
            'bill_to_company': bill_to_company,
            'my_pay': my_pay,
            'total_amount': total_amount,
            'wallet_used': wallet_used,
            'points_redeemed': points_redeemed,
            'payment_mode': payment_mode,
        })

        try:
            with transaction.atomic():
                order = Order.objects.create(**create_kwargs)
        except IntegrityError:
            existing = Order.objects.filter(
                order_number=merchant_ref,
                customer_id=snapshot.get('customer_id'),
                company_id=snapshot.get('company_id'),
                is_deleted=False,
            ).first()
            if existing:
                return existing
            raise

        _apply_wallet_and_points_to_customer(customer, order, wallet_used, points_redeemed)

        for item_data in snapshot.get('items', []):
            product = Product.objects.get(
                pk=int(item_data['product_id']),
                company=company,
                is_deleted=False,
            )
            qty = int(item_data.get('qty') or 0)
            if qty <= 0:
                continue

            site_price = _money(item_data.get('site_price'))
            line_total = _money(item_data.get('line_total'))
            line_saving = _money(item_data.get('line_saving'))

            OrderItem.objects.create(
                company=company,
                order=order,
                product=product,
                counter=_resolve_product_counter(product, cafe=cafe),
                price=(line_total / qty) if qty else site_price,
                unit_price=site_price,
                item_offer_discount=line_saving,
                qty=qty,
                image_snapshot=str(product.image) if product.image else '',
                created_at=timezone.now(),
            )

            if not _deduct_stock(product, qty, 'web', order.pk, company, f'Web order {order.order_number}'):
                raise StockUnavailableError(f'{product.name} is out of stock or has insufficient quantity available.')

        _create_counter_tickets(order)

        if locked_coupon and coupon_discount > 0:
            Coupon.objects.filter(pk=locked_coupon.pk).update(used_count=F('used_count') + 1)

        _record_offer_usage_for_snapshot(customer, order, snapshot)

        order.auto_ready_at = order.calculate_auto_ready_at(start_from=timezone.now())
        order.save(update_fields=['auto_ready_at'])

        OrderStatus.objects.create(
            order=order,
            status=OrderStatusChoices.CONFIRMED,
            details='Order auto-confirmed after online payment.',
            created_at=timezone.now(),
        )

        _notify_new_order(order, customer.name)

        try:
            from apps.core.royalty_service import award_standard_points
            award_standard_points(customer, order)
        except Exception as _exc:
            logger.warning('Royalty award failed for order %s: %s', order.order_number, _exc)

        return order




def _create_new_kiosk_order_from_pending_snapshot(snapshot, transaction_id=''):
    from apps.accounts.models import Customer
    from apps.menu.models import Cafe as CafeModel

    created_order_id = snapshot.get('created_order_id')
    if created_order_id:
        existing = Order.objects.filter(pk=created_order_id, is_deleted=False).first()
        if existing:
            return existing

    merchant_ref = (snapshot.get('merchant_ref') or '').strip()
    existing = Order.objects.filter(
        order_number=merchant_ref,
        company_id=snapshot.get('company_id'),
        is_deleted=False,
    ).first()
    if existing:
        return existing

    company = Company.objects.get(pk=snapshot['company_id'])
    cafe = None
    if snapshot.get('cafe_id'):
        cafe = CafeModel.objects.filter(
            pk=snapshot['cafe_id'],
            company=company,
            is_deleted=False,
            is_active=True,
        ).first()

    kiosk_customer, created = Customer.objects.get_or_create(
        email=f'kiosk@{company.name[:20].replace(" ", "").lower()}.kiosk',
        defaults={
            'name': 'Kiosk Orders',
            'company': company,
            'is_active': True,
            'meal_benefit': 'none',
        }
    )
    if not created and kiosk_customer.meal_benefit != 'none':
        Customer.objects.filter(pk=kiosk_customer.pk).update(meal_benefit='none', subsidy_eligible=False)
        kiosk_customer.meal_benefit = 'none'

    subtotal = _money(snapshot.get('subtotal'))
    offer_discount = _money(snapshot.get('offer_discount'))
    total_amount = _money(snapshot.get('total_amount'))
    customer_name = (snapshot.get('customer_name') or 'Kiosk Customer').strip() or 'Kiosk Customer'
    payment_mode = snapshot.get('payment_mode') or PaymentModeChoices.ONLINE

    create_kwargs = {
        'company': company,
        'customer': kiosk_customer,
        'customer_name_snapshot': customer_name,
        'customer_phone_snapshot': (snapshot.get('customer_phone') or '').strip(),
        'cafe': cafe,
        'subtotal': subtotal,
        'total_amount': total_amount,
        'my_pay': total_amount,
        'offer_discount': offer_discount,
        'payment_mode': payment_mode,
        'payment_status': 'paid',
        'order_type': 1,
        'order_status': OrderStatusChoices.CONFIRMED,
        'order_number': merchant_ref,
        'transaction_id': transaction_id or snapshot.get('gateway_order_id', ''),
    }

    with transaction.atomic():
        try:
            with transaction.atomic():
                order = Order.objects.create(**create_kwargs)
        except IntegrityError:
            existing = Order.objects.filter(
                order_number=merchant_ref,
                company_id=snapshot.get('company_id'),
                is_deleted=False,
            ).first()
            if existing:
                return existing
            raise

        for item_data in snapshot.get('items', []):
            product = Product.objects.get(
                pk=int(item_data['product_id']),
                company=company,
                is_active=True,
                is_deleted=False,
            )
            qty = int(item_data.get('qty') or 0)
            if qty <= 0:
                continue

            site_price = _money(item_data.get('site_price'))
            line_total = _money(item_data.get('line_total'))
            line_saving = _money(item_data.get('line_saving'))

            OrderItem.objects.create(
                company=company,
                order=order,
                product=product,
                counter=_resolve_product_counter(product, cafe=cafe),
                price=(line_total / qty) if qty else site_price,
                unit_price=site_price,
                item_offer_discount=line_saving,
                qty=qty,
                image_snapshot=str(product.image) if product.image else '',
                created_at=timezone.now(),
            )

            if not _deduct_stock(product, qty, 'web', order.pk, company, f'Kiosk {order.order_number}'):
                raise StockUnavailableError(f'{product.name} is out of stock or has insufficient quantity available.')

        _create_counter_tickets(order)
        _record_offer_usage_for_snapshot(kiosk_customer, order, snapshot)
        order.auto_ready_at = order.calculate_auto_ready_at(start_from=timezone.now())
        order.save(update_fields=['auto_ready_at'])

        OrderStatus.objects.create(
            order=order,
            status=OrderStatusChoices.CONFIRMED,
            details=f'Kiosk order auto-confirmed after online payment. Customer: {customer_name}.',
            created_at=timezone.now(),
        )

        try:
            from apps.accounts.models import StaffUser
            from apps.core.models import Notification
            staff_qs = StaffUser.objects.filter(
                company=company, is_active=True,
                role__in=[StaffUser.ROLE_ADMIN, StaffUser.ROLE_POS, StaffUser.ROLE_CAFEMAN],
            )
            for staff in staff_qs:
                Notification.objects.create(
                    company=company, staff_user=staff,
                    notif_type=Notification.TYPE_ORDER,
                    title=f'New Kiosk Order #{order.order_number}',
                    message=f'{order.display_customer_name} placed a kiosk order for Rs. {order.total_amount}',
                    link=f'/dashboard/orders/{order.pk}/',
                )
        except Exception as _exc:
            logger.warning('Kiosk notification failed for %s: %s', order.order_number, _exc)

        return order


def _clear_post_success_checkout_state(request):
    request.session['cart'] = {}
    request.session.pop('coupon_id', None)
    request.session.pop('coupon_code', None)
    request.session.pop('coupon_discount', None)
    request.session.pop('web_cafe_id', None)
    request.session.pop('editing_order_id', None)
    _clear_pending_online_checkout(request)
    request.session.modified = True


def _clear_post_success_kiosk_state(request):
    request.session['kiosk_cart'] = {}
    _clear_pending_kiosk_online_checkout(request)
    request.session.modified = True


def _render_razorpay_checkout(request, snapshot):
    amount_paise = to_paise(_money(snapshot.get('my_pay')) or _money(snapshot.get('total_amount')))
    customer = request.current_customer
    company_name = getattr(getattr(customer, 'company', None), 'name', '') or 'NeverQ'
    gateway_order_id = (snapshot.get('gateway_order_id') or '').strip()
    merchant_ref = (snapshot.get('merchant_ref') or '').strip()
    contact = re.sub(r'\D+', '', getattr(customer, 'phone', '') or '')

    checkout_options = {
        'key': getattr(settings, 'RAZORPAY_KEY_ID', ''),
        'amount': amount_paise,
        'currency': 'INR',
        'name': company_name,
        'description': f'Order {merchant_ref}',
        'order_id': gateway_order_id,
        'prefill': {
            'name': getattr(customer, 'name', '') or '',
            'email': getattr(customer, 'email', '') or '',
            'contact': contact,
        },
        'notes': {
            'neverq_order_number': merchant_ref,
        },
        'theme': {
            'color': '#a01120',
        },
    }

    checkout_options_json = (
        json.dumps(checkout_options)
        .replace('<', '\\u003c')
        .replace('>', '\\u003e')
        .replace('&', '\\u0026')
    )

    return render(request, 'orders/razorpay_checkout.html', {
        'merchant_ref': merchant_ref,
        'amount_display': _money(snapshot.get('my_pay')),
        'amount_paise': amount_paise,
        'razorpay_order_id': gateway_order_id,
        'checkout_options_json': checkout_options_json,
        'cancel_url': reverse('orders:razorpay_cancel') + f'?merchant_order_id={merchant_ref}',
    })


@customer_login_required
def razorpay_initiate(request):
    snapshot = _get_pending_online_checkout(request)
    if not snapshot:
        messages.error(request, 'No pending online checkout was found.')
        return redirect('orders:checkout')

    if snapshot.get('customer_id') != request.current_customer.pk:
        _clear_pending_online_checkout(request)
        messages.error(request, 'The pending payment session does not belong to this customer.')
        return redirect('accounts:customer_login')

    created_order_id = snapshot.get('created_order_id')
    if created_order_id:
        existing = Order.objects.filter(pk=created_order_id, is_deleted=False).first()
        if existing:
            return redirect('orders:order_confirmation', pk=existing.pk)

    if snapshot.get('gateway') == 'razorpay' and snapshot.get('gateway_order_id'):
        return _render_razorpay_checkout(request, snapshot)

    temp_order = SimpleNamespace(
        order_number=snapshot['merchant_ref'],
        my_pay=_money(snapshot.get('my_pay')),
        total_amount=_money(snapshot.get('total_amount')),
        pk=0,
        company_id=snapshot['company_id'],
    )

    try:
        razorpay_response = create_razorpay_order(
            order=temp_order,
            customer=request.current_customer,
            **_razorpay_config(),
        )
    except RazorpayError as exc:
        logger.warning(
            'Razorpay initiation failed for web order %s (customer=%s, company=%s): %s',
            snapshot.get('merchant_ref'),
            request.current_customer.pk,
            snapshot.get('company_id'),
            exc,
        )
        messages.error(request, 'Unable to start Razorpay payment right now. Please try again in a moment.')
        return redirect('orders:checkout')

    gateway_order_id = (razorpay_response.get('id') or '').strip()
    if not gateway_order_id:
        logger.warning(
            'Razorpay did not return an order id for web order %s (customer=%s, company=%s). Response=%s',
            snapshot.get('merchant_ref'),
            request.current_customer.pk,
            snapshot.get('company_id'),
            razorpay_response,
        )
        messages.error(request, 'Razorpay did not return a checkout order.')
        return redirect('orders:checkout')

    snapshot['gateway'] = 'razorpay'
    snapshot['gateway_order_id'] = gateway_order_id
    snapshot['gateway_redirect_url'] = request.build_absolute_uri(reverse('orders:razorpay_initiate'))
    _save_pending_online_checkout(request, snapshot)

    return _render_razorpay_checkout(request, snapshot)


@customer_login_required
@require_POST
def razorpay_verify(request):
    merchant_ref = (request.POST.get('merchant_order_id') or '').strip()
    razorpay_order_id = (request.POST.get('razorpay_order_id') or '').strip()
    razorpay_payment_id = (request.POST.get('razorpay_payment_id') or '').strip()
    razorpay_signature = (request.POST.get('razorpay_signature') or '').strip()

    snapshot = _get_pending_online_checkout(request)
    if not snapshot or (snapshot.get('merchant_ref') or '').strip() != merchant_ref:
        snapshot = _get_pending_phonepe_snapshot('web', merchant_ref)

    if not snapshot:
        messages.error(request, 'No pending online checkout was found.')
        return redirect('orders:checkout')

    if snapshot.get('customer_id') != request.current_customer.pk:
        _clear_pending_online_checkout(request)
        messages.error(request, 'The pending payment session does not belong to this customer.')
        return redirect('accounts:customer_login')

    expected_order_id = (snapshot.get('gateway_order_id') or '').strip()
    if snapshot.get('gateway') != 'razorpay' or expected_order_id != razorpay_order_id:
        logger.warning(
            'Razorpay verification mismatch for web order %s: expected_order_id=%s posted_order_id=%s',
            merchant_ref,
            expected_order_id,
            razorpay_order_id,
        )
        messages.error(request, 'Payment verification failed. Your order was not completed.')
        return redirect('orders:checkout')

    if not verify_razorpay_signature(
        order_id=razorpay_order_id,
        payment_id=razorpay_payment_id,
        signature=razorpay_signature,
        key_secret=getattr(settings, 'RAZORPAY_KEY_SECRET', ''),
    ):
        logger.warning('Razorpay signature verification failed for web order %s.', merchant_ref)
        messages.error(request, 'Payment verification failed. Your order was not completed.')
        return redirect('orders:checkout')

    existing = Order.objects.filter(
        order_number=merchant_ref,
        customer_id=request.current_customer.pk,
        company_id=snapshot.get('company_id'),
        is_deleted=False,
    ).first()
    if existing:
        _clear_post_success_checkout_state(request)
        messages.success(request, f'Payment completed for order #{existing.order_number}.')
        return redirect('orders:order_confirmation', pk=existing.pk)

    try:
        order = _create_new_order_from_pending_snapshot(snapshot, transaction_id=razorpay_payment_id)
    except StockUnavailableError as exc:
        logger.warning('Razorpay paid order %s could not be finalized because stock changed: %s', merchant_ref, exc)
        messages.error(request, 'Payment was received but the order could not be finalized. Please contact support.')
        return redirect('orders:checkout')
    except Exception as exc:
        logger.exception('Razorpay paid order %s could not be finalized: %s', merchant_ref, exc)
        messages.error(request, 'Payment was received but the order could not be finalized. Please contact support.')
        return redirect('orders:checkout')

    _clear_post_success_checkout_state(request)
    messages.success(request, f'Payment completed for order #{order.order_number}.')
    return redirect('orders:order_confirmation', pk=order.pk)


@customer_login_required
def razorpay_cancel(request):
    merchant_ref = (request.GET.get('merchant_order_id') or '').strip()
    snapshot = _get_pending_online_checkout(request)
    if snapshot and (snapshot.get('merchant_ref') or '').strip() == merchant_ref:
        _clear_pending_online_checkout(request)
    elif merchant_ref:
        _clear_pending_phonepe_snapshot('web', merchant_ref)

    messages.error(request, 'Sorry, your order was not completed.')
    return redirect('orders:checkout')


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Server-side reconciliation endpoint for Razorpay webhook deliveries.

    Razorpay Configuration (Dashboard → Settings → Webhooks):
      URL    : https://q.neverno.in/orders/razorpay/webhook/
      Events : payment.captured   (the only event we act on)
      Secret : RAZORPAY_WEBHOOK_SECRET  (set in .env — distinct from RAZORPAY_KEY_SECRET)

    Why this exists
    ---------------
    ``razorpay_verify`` and ``kiosk_razorpay_verify`` depend on the browser
    reaching Django after the Razorpay checkout completes.  If the browser
    closes, the network drops, or the redirect never fires, Razorpay has
    captured money but NeverQ has no order.  This webhook closes that gap:
    Razorpay retries delivery up to 24 h, so the order will be created even
    when the browser path fails entirely.

    Idempotency
    -----------
    ``_create_new_order_from_pending_snapshot`` checks the DB for an existing
    order with the same ``order_number`` before inserting, and the inner
    ``transaction.atomic()`` block catches ``IntegrityError`` and returns the
    existing row.  Duplicate webhook deliveries are therefore safe.

    Security
    --------
    The raw POST body is verified with HMAC-SHA256 against
    ``RAZORPAY_WEBHOOK_SECRET`` before any business logic runs.  Requests
    with a missing or wrong ``X-Razorpay-Signature`` are rejected with 400.
    The view is @csrf_exempt because Razorpay POSTs from its own servers
    (not from a browser session with a CSRF cookie).
    """
    # ── 1. Signature verification ─────────────────────────────────────────────
    webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')
    if not webhook_secret:
        # Webhook secret not configured — log loudly and refuse to process.
        logger.error(
            'razorpay_webhook: RAZORPAY_WEBHOOK_SECRET is not set. '
            'Configure it in .env and in the Razorpay Dashboard.'
        )
        return JsonResponse({'error': 'Webhook not configured.'}, status=500)

    signature_header = request.headers.get('X-Razorpay-Signature', '')
    if not verify_razorpay_webhook_signature(
        body_bytes=request.body,
        signature_header=signature_header,
        webhook_secret=webhook_secret,
    ):
        logger.warning(
            'razorpay_webhook: signature verification failed '
            '(header=%r body_prefix=%r)',
            signature_header[:20] if signature_header else '',
            request.body[:80],
        )
        return JsonResponse({'error': 'Invalid webhook signature.'}, status=400)

    # ── 2. Parse event ────────────────────────────────────────────────────────
    try:
        event_data = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error('razorpay_webhook: could not parse body: %s', exc)
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    event = event_data.get('event', '')

    # Only act on payment.captured.  For every other event return 200 so
    # Razorpay does not keep retrying an endpoint that will never handle them.
    if event != 'payment.captured':
        return JsonResponse({'status': 'ignored', 'event': event})

    # ── 3. Extract identifiers from the event payload ─────────────────────────
    try:
        payment_entity = event_data['payload']['payment']['entity']
    except (KeyError, TypeError):
        logger.error('razorpay_webhook: unexpected payload structure: %s', str(event_data)[:400])
        return JsonResponse({'error': 'Unexpected payload structure.'}, status=400)

    gateway_order_id = (payment_entity.get('order_id') or '').strip()   # e.g. "order_XXXXX"
    razorpay_payment_id = (payment_entity.get('id') or '').strip()       # e.g. "pay_XXXXX"
    notes = payment_entity.get('notes') or {}
    # merchant_ref is the NeverQ order_number we stored in notes when creating the Razorpay order
    merchant_ref = (
        notes.get('neverq_order_number')
        or ''
    ).strip()

    if not merchant_ref or not gateway_order_id or not razorpay_payment_id:
        logger.error(
            'razorpay_webhook: payment.captured missing required fields '
            'merchant_ref=%r gateway_order_id=%r payment_id=%r',
            merchant_ref, gateway_order_id, razorpay_payment_id,
        )
        # Return 200 to prevent endless retries for a structurally bad event.
        return JsonResponse({'status': 'missing_fields'})

    logger.info(
        'razorpay_webhook: payment.captured merchant_ref=%s gateway_order_id=%s payment_id=%s',
        merchant_ref, gateway_order_id, razorpay_payment_id,
    )

    # ── 4. Idempotency guard — order may already exist (browser path won) ─────
    existing_order = Order.objects.filter(
        order_number=merchant_ref,
        is_deleted=False,
    ).first()
    if existing_order:
        logger.info(
            'razorpay_webhook: order %s already exists (pk=%s), skipping creation.',
            merchant_ref, existing_order.pk,
        )
        return JsonResponse({'status': 'already_exists'})

    # ── 5. Locate the pending snapshot (web or kiosk) ─────────────────────────
    web_snapshot = _get_pending_phonepe_snapshot('web', merchant_ref)
    kiosk_snapshot = _get_pending_phonepe_snapshot('kiosk', merchant_ref)

    if not web_snapshot and not kiosk_snapshot:
        # Snapshot expired from cache (> 6 h) or never existed.
        # Nothing we can safely reconstruct — log for manual follow-up.
        logger.error(
            'razorpay_webhook: payment.captured for %s but no pending snapshot found '
            '(cache may have expired). Manual order creation required. '
            'Razorpay payment_id=%s',
            merchant_ref, razorpay_payment_id,
        )
        # Return 200 so Razorpay does not retry indefinitely for a dead snapshot.
        return JsonResponse({'status': 'snapshot_expired'})

    snapshot = web_snapshot or kiosk_snapshot
    is_kiosk = kiosk_snapshot is not None and web_snapshot is None

    # Confirm the gateway_order_id stored in the snapshot matches the event
    # so we cannot be tricked into creating an order for a mismatched payment.
    expected_gateway_id = (snapshot.get('gateway_order_id') or '').strip()
    if expected_gateway_id and expected_gateway_id != gateway_order_id:
        logger.error(
            'razorpay_webhook: gateway_order_id mismatch for merchant_ref=%s '
            'snapshot=%r event=%r — refusing to create order.',
            merchant_ref, expected_gateway_id, gateway_order_id,
        )
        return JsonResponse({'error': 'order_id mismatch.'}, status=409)

    # ── 6. Create the NeverQ order ────────────────────────────────────────────
    try:
        if is_kiosk:
            order = _create_new_kiosk_order_from_pending_snapshot(
                kiosk_snapshot, transaction_id=razorpay_payment_id
            )
            _clear_pending_phonepe_snapshot('kiosk', merchant_ref)
            logger.info(
                'razorpay_webhook: kiosk order %s (pk=%s) created via webhook.',
                order.order_number, order.pk,
            )
        else:
            order = _create_new_order_from_pending_snapshot(
                web_snapshot, transaction_id=razorpay_payment_id
            )
            _clear_pending_phonepe_snapshot('web', merchant_ref)
            logger.info(
                'razorpay_webhook: web order %s (pk=%s) created via webhook.',
                order.order_number, order.pk,
            )
    except StockUnavailableError as exc:
        logger.error(
            'razorpay_webhook: stock unavailable finalizing order %s: %s. '
            'Razorpay payment_id=%s — manual refund may be required.',
            merchant_ref, exc, razorpay_payment_id,
        )
        # Return 409 so Razorpay retries (in case stock is restored).
        return JsonResponse({'error': str(exc)}, status=409)
    except Exception:
        logger.exception(
            'razorpay_webhook: unexpected error finalizing order %s '
            'Razorpay payment_id=%s',
            merchant_ref, razorpay_payment_id,
        )
        # Return 500 so Razorpay retries.
        return JsonResponse({'error': 'Internal error finalizing order.'}, status=500)

    return JsonResponse({'status': 'created', 'order_number': order.order_number})


def _render_kiosk_razorpay_checkout(request, company, snapshot):
    amount_paise = to_paise(_money(snapshot.get('my_pay')) or _money(snapshot.get('total_amount')))
    gateway_order_id = (snapshot.get('gateway_order_id') or '').strip()
    merchant_ref = (snapshot.get('merchant_ref') or '').strip()
    kiosk_slug = (snapshot.get('kiosk_slug') or _kiosk_read_slug(request) or '').strip()
    customer_phone = re.sub(r'\D+', '', snapshot.get('customer_phone') or '')
    verify_url = reverse('orders:kiosk_razorpay_verify', kwargs={'company_id': company.pk})
    cancel_url = reverse('orders:kiosk_razorpay_cancel', kwargs={'company_id': company.pk}) + f'?merchant_order_id={merchant_ref}'
    back_url = reverse('orders:kiosk_cart', kwargs={'company_id': company.pk})
    if kiosk_slug:
        cancel_url = f'{cancel_url}&kiosk={kiosk_slug}'
        back_url = f'{back_url}?kiosk={kiosk_slug}'

    checkout_options = {
        'key': getattr(settings, 'RAZORPAY_KEY_ID', ''),
        'amount': amount_paise,
        'currency': 'INR',
        'name': company.name or 'NeverQ',
        'description': f'Kiosk Order {merchant_ref}',
        'order_id': gateway_order_id,
        'prefill': {
            'name': snapshot.get('customer_name') or 'Kiosk Customer',
            'contact': customer_phone,
        },
        'notes': {
            'neverq_order_number': merchant_ref,
            'source': 'kiosk',
        },
        'theme': {
            'color': '#a01120',
        },
    }
    checkout_options_json = (
        json.dumps(checkout_options)
        .replace('<', '\\u003c')
        .replace('>', '\\u003e')
        .replace('&', '\\u0026')
    )

    return render(request, 'orders/razorpay_kiosk_checkout.html', {
        'company': company,
        'company_id': company.pk,
        'merchant_ref': merchant_ref,
        'amount_display': _money(snapshot.get('my_pay')),
        'amount_paise': amount_paise,
        'razorpay_order_id': gateway_order_id,
        'checkout_options_json': checkout_options_json,
        'verify_url': verify_url,
        'cancel_url': cancel_url,
        'back_url': back_url,
        'kiosk_slug': kiosk_slug,
        'page_title': 'Complete Kiosk Payment',
    })


def kiosk_razorpay_initiate(request, company_id):
    company = get_object_or_404(Company, pk=company_id, is_active=True, is_deleted=False)
    snapshot = _get_pending_kiosk_online_checkout(request)
    kiosk_slug = _kiosk_read_slug(request)
    if not snapshot or int(snapshot.get('company_id') or 0) != int(company.pk):
        messages.error(request, 'No pending kiosk online checkout was found.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    kiosk_slug = (snapshot.get('kiosk_slug') or kiosk_slug or '').strip()
    created_order_id = snapshot.get('created_order_id')
    if created_order_id:
        existing = Order.objects.filter(pk=created_order_id, company=company, is_deleted=False).first()
        if existing:
            return _kiosk_redirect('orders:kiosk_confirmation', company_id, kiosk_slug, pk=existing.pk)

    if snapshot.get('gateway') == 'razorpay' and snapshot.get('gateway_order_id'):
        return _render_kiosk_razorpay_checkout(request, company, snapshot)

    from apps.accounts.models import Customer
    kiosk_customer, created = Customer.objects.get_or_create(
        email=f'kiosk@{company.name[:20].replace(" ", "").lower()}.kiosk',
        defaults={
            'name': 'Kiosk Orders',
            'company': company,
            'is_active': True,
            'meal_benefit': 'none',
        }
    )
    if not created and kiosk_customer.meal_benefit != 'none':
        Customer.objects.filter(pk=kiosk_customer.pk).update(meal_benefit='none', subsidy_eligible=False)
        kiosk_customer.meal_benefit = 'none'

    temp_order = SimpleNamespace(
        order_number=snapshot['merchant_ref'],
        my_pay=_money(snapshot.get('my_pay')),
        total_amount=_money(snapshot.get('total_amount')),
        pk=0,
        company_id=snapshot['company_id'],
    )
    try:
        razorpay_response = create_razorpay_order(
            order=temp_order,
            customer=kiosk_customer,
            **_razorpay_config(),
        )
    except RazorpayError as exc:
        logger.warning(
            'Razorpay initiation failed for kiosk order %s (company=%s, kiosk=%s): %s',
            snapshot.get('merchant_ref'),
            company_id,
            kiosk_slug,
            exc,
        )
        messages.error(request, 'Unable to start Razorpay payment right now. Please try again in a moment.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    gateway_order_id = (razorpay_response.get('id') or '').strip()
    if not gateway_order_id:
        logger.warning(
            'Razorpay did not return an order id for kiosk order %s (company=%s, kiosk=%s). Response=%s',
            snapshot.get('merchant_ref'),
            company_id,
            kiosk_slug,
            razorpay_response,
        )
        messages.error(request, 'Razorpay did not return a checkout order.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    snapshot['gateway'] = 'razorpay'
    snapshot['gateway_order_id'] = gateway_order_id
    snapshot['gateway_redirect_url'] = request.build_absolute_uri(
        reverse('orders:kiosk_razorpay_initiate', kwargs={'company_id': company_id})
    )
    _save_pending_kiosk_online_checkout(request, snapshot)
    return _render_kiosk_razorpay_checkout(request, company, snapshot)


@require_POST
def kiosk_razorpay_verify(request, company_id):
    company = get_object_or_404(Company, pk=company_id, is_active=True, is_deleted=False)
    merchant_ref = (request.POST.get('merchant_order_id') or '').strip()
    razorpay_order_id = (request.POST.get('razorpay_order_id') or '').strip()
    razorpay_payment_id = (request.POST.get('razorpay_payment_id') or '').strip()
    razorpay_signature = (request.POST.get('razorpay_signature') or '').strip()

    snapshot = _get_pending_kiosk_online_checkout(request)
    if not snapshot or (snapshot.get('merchant_ref') or '').strip() != merchant_ref:
        snapshot = _get_pending_phonepe_snapshot('kiosk', merchant_ref)

    kiosk_slug = (snapshot or {}).get('kiosk_slug') or _kiosk_read_slug(request)
    if not snapshot or int(snapshot.get('company_id') or 0) != int(company.pk):
        messages.error(request, 'No pending kiosk online checkout was found.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    expected_order_id = (snapshot.get('gateway_order_id') or '').strip()
    if snapshot.get('gateway') != 'razorpay' or expected_order_id != razorpay_order_id:
        logger.warning(
            'Razorpay verification mismatch for kiosk order %s: expected_order_id=%s posted_order_id=%s',
            merchant_ref,
            expected_order_id,
            razorpay_order_id,
        )
        messages.error(request, 'Payment verification failed. Your kiosk order was not completed.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    if not verify_razorpay_signature(
        order_id=razorpay_order_id,
        payment_id=razorpay_payment_id,
        signature=razorpay_signature,
        key_secret=getattr(settings, 'RAZORPAY_KEY_SECRET', ''),
    ):
        logger.warning('Razorpay signature verification failed for kiosk order %s.', merchant_ref)
        messages.error(request, 'Payment verification failed. Your kiosk order was not completed.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    existing = Order.objects.filter(
        order_number=merchant_ref,
        company=company,
        is_deleted=False,
    ).first()
    if existing:
        _clear_post_success_kiosk_state(request)
        _set_last_kiosk_order(
            request,
            merchant_ref=merchant_ref,
            order_id=existing.pk,
            company_id=company_id,
            kiosk_slug=kiosk_slug,
        )
        messages.success(request, f'Payment completed for kiosk order #{existing.order_number}.')
        return _kiosk_redirect('orders:kiosk_confirmation', company_id, kiosk_slug, pk=existing.pk)

    try:
        order = _create_new_kiosk_order_from_pending_snapshot(snapshot, transaction_id=razorpay_payment_id)
    except StockUnavailableError as exc:
        logger.warning('Razorpay paid kiosk order %s could not be finalized because stock changed: %s', merchant_ref, exc)
        messages.error(request, 'Payment was received but the kiosk order could not be finalized. Please contact support.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)
    except Exception as exc:
        logger.exception('Razorpay paid kiosk order %s could not be finalized: %s', merchant_ref, exc)
        messages.error(request, 'Payment was received but the kiosk order could not be finalized. Please contact support.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    _clear_post_success_kiosk_state(request)
    _set_last_kiosk_order(
        request,
        merchant_ref=merchant_ref,
        order_id=order.pk,
        company_id=company_id,
        kiosk_slug=kiosk_slug,
    )
    messages.success(request, f'Payment completed for kiosk order #{order.order_number}.')
    return _kiosk_redirect('orders:kiosk_confirmation', company_id, kiosk_slug, pk=order.pk)


def kiosk_razorpay_cancel(request, company_id):
    company = get_object_or_404(Company, pk=company_id, is_active=True, is_deleted=False)
    merchant_ref = (request.GET.get('merchant_order_id') or '').strip()
    snapshot = _get_pending_kiosk_online_checkout(request)
    kiosk_slug = (snapshot or {}).get('kiosk_slug') or _kiosk_read_slug(request)
    if snapshot and (snapshot.get('merchant_ref') or '').strip() == merchant_ref:
        _clear_pending_kiosk_online_checkout(request)
    elif merchant_ref:
        _clear_pending_phonepe_snapshot('kiosk', merchant_ref)

    messages.error(request, 'Sorry, your kiosk order was not completed.')
    return _kiosk_redirect('orders:kiosk_cart', company.pk, kiosk_slug)


@customer_login_required
def phonepe_initiate(request):
    snapshot = _get_pending_online_checkout(request)
    if not snapshot:
        messages.error(request, 'No pending online checkout was found.')
        return redirect('orders:checkout')

    if snapshot.get('customer_id') != request.current_customer.pk:
        _clear_pending_online_checkout(request)
        messages.error(request, 'The pending payment session does not belong to this customer.')
        return redirect('accounts:customer_login')

    created_order_id = snapshot.get('created_order_id')
    if created_order_id:
        existing = Order.objects.filter(pk=created_order_id, is_deleted=False).first()
        if existing:
            return redirect('orders:order_confirmation', pk=existing.pk)

    existing_redirect_url = snapshot.get('gateway_redirect_url')
    if existing_redirect_url:
        return redirect(existing_redirect_url)

    redirect_url = request.build_absolute_uri(
        reverse('orders:phonepe_callback')
    ) + f'?merchant_order_id={snapshot["merchant_ref"]}'

    temp_order = SimpleNamespace(
        order_number=snapshot['merchant_ref'],
        my_pay=_money(snapshot.get('my_pay')),
        total_amount=_money(snapshot.get('total_amount')),
        pk=0,
        company_id=snapshot['company_id'],
    )

    try:
        phonepe_response = create_phonepe_payment(
            order=temp_order,
            customer=request.current_customer,
            redirect_url=redirect_url,
            **_phonepe_config(),
        )
    except PhonePeError as exc:
        logger.warning(
            'PhonePe initiation failed for web order %s (customer=%s, company=%s): %s',
            snapshot.get('merchant_ref'),
            request.current_customer.pk,
            snapshot.get('company_id'),
            exc,
        )
        messages.error(request, 'Unable to start PhonePe payment right now. Please try again in a moment.')
        return redirect('orders:checkout')

    # PhonePe v2 sandbox may return the order id under different top-level keys.
    # Fall back to the merchant_ref so _can_reconcile_phonepe_testmode_locally
    # is never blocked by a missing field in the gateway response.
    gateway_order_id = (
        phonepe_response.get('orderId')
        or phonepe_response.get('merchantOrderId')
        or snapshot['merchant_ref']
    )
    redirect_to = phonepe_response.get('redirectUrl') or ''

    if not redirect_to:
        logger.warning(
            'PhonePe did not return a checkout URL for web order %s (customer=%s, company=%s). Response=%s',
            snapshot.get('merchant_ref'),
            request.current_customer.pk,
            snapshot.get('company_id'),
            phonepe_response,
        )
        messages.error(request, 'PhonePe did not return a checkout URL.')
        return redirect('orders:checkout')

    snapshot['gateway_order_id'] = gateway_order_id
    snapshot['gateway_redirect_url'] = redirect_to
    _save_pending_online_checkout(request, snapshot)

    return redirect(redirect_to)


@csrf_exempt
def phonepe_callback(request):
    if request.method == 'POST':
        # ── PhonePe v1 callback ───────────────────────────────────────────
        # Body: form-encoded fields including merchantId, transactionId,
        # merchantOrderId, amount, providerReferenceId, checksum
        try:
            checksum_field, payload = phonepe_decode_callback(request.body)
        except PhonePeError as exc:
            import logging as _logging
            _logging.getLogger('django').error(
                'PHONEPE_CALLBACK_FAIL body=%r error=%s',
                request.body[:500], exc,
            )
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

        cfg = _phonepe_config()
        if not phonepe_callback_authorized(
            cfg['salt_key'],
            cfg['salt_index'],
            checksum_field,
            payload,
        ):
            return JsonResponse({'success': False, 'error': 'Invalid webhook authorization.'}, status=403)

        merchant_order_id = (
            payload.get('merchantOrderId')
            or payload.get('transactionId')
            or ''
        )

        if not merchant_order_id:
            return JsonResponse({'success': False, 'error': 'Missing merchant order id.'}, status=400)

        order = Order.objects.filter(
            order_number=merchant_order_id,
            is_deleted=False,
        ).first()

        normalised = {
            'state':         payload.get('state') or '',
            'orderId':       payload.get('providerReferenceId') or merchant_order_id,
            'transactionId': payload.get('transactionId') or '',
        }

        if order:
            _apply_phonepe_state_to_order(order, normalised, source='webhook')
            return JsonResponse({'success': True})

        state        = str(payload.get('state') or '').upper()
        web_snapshot = _get_pending_phonepe_snapshot('web',   merchant_order_id)
        kiosk_snapshot = _get_pending_phonepe_snapshot('kiosk', merchant_order_id)
        phonepe_txn  = payload.get('providerReferenceId') or payload.get('transactionId') or ''

        if web_snapshot:
            if state == 'COMPLETED':
                try:
                    _create_new_order_from_pending_snapshot(web_snapshot, transaction_id=phonepe_txn)
                except StockUnavailableError as exc:
                    logger.error('Webhook could not finalize web order %s: %s', merchant_order_id, exc)
                    return JsonResponse({'success': False, 'error': str(exc)}, status=409)
                except Exception:
                    logger.exception('Webhook could not finalize web order %s', merchant_order_id)
                    return JsonResponse({'success': False, 'error': 'Unable to finalize paid web order.'}, status=500)
                _clear_pending_phonepe_snapshot('web', merchant_order_id)
            elif state == 'FAILED':
                _clear_pending_phonepe_snapshot('web', merchant_order_id)
            return JsonResponse({'success': True})

        if kiosk_snapshot:
            if state == 'COMPLETED':
                try:
                    _create_new_kiosk_order_from_pending_snapshot(kiosk_snapshot, transaction_id=phonepe_txn)
                except StockUnavailableError as exc:
                    logger.error('Webhook could not finalize kiosk order %s: %s', merchant_order_id, exc)
                    return JsonResponse({'success': False, 'error': str(exc)}, status=409)
                except Exception:
                    logger.exception('Webhook could not finalize kiosk order %s', merchant_order_id)
                    return JsonResponse({'success': False, 'error': 'Unable to finalize paid kiosk order.'}, status=500)
                _clear_pending_phonepe_snapshot('kiosk', merchant_order_id)
            elif state == 'FAILED':
                _clear_pending_phonepe_snapshot('kiosk', merchant_order_id)
            return JsonResponse({'success': True})

        return JsonResponse({'success': False, 'error': 'Order not found.'}, status=404)

    web_snapshot = _get_pending_online_checkout(request)
    kiosk_snapshot = _get_pending_kiosk_online_checkout(request)
    last_kiosk_order = _get_last_kiosk_order(request)
    merchant_order_id = (
        request.GET.get('merchantOrderId')
        or request.GET.get('merchant_order_id')
        or (web_snapshot.get('merchant_ref') if web_snapshot else '')
        or (kiosk_snapshot.get('merchant_ref') if kiosk_snapshot else '')
        or (last_kiosk_order.get('merchant_ref') if last_kiosk_order else '')
    )

    if not merchant_order_id:
        messages.error(request, 'We could not find the payment order to verify.')
        if request.session.get('customer_id'):
            return redirect('orders:checkout')
        return redirect('accounts:customer_login')

    existing_order = Order.objects.filter(order_number=merchant_order_id, is_deleted=False).first()
    if existing_order:
        try:
            status_payload = _fetch_phonepe_order_status_with_retry(existing_order.order_number)
            state = _apply_phonepe_state_to_order(existing_order, status_payload, source='redirect')
            if state == 'COMPLETED':
                messages.success(request, f'Payment completed for order #{existing_order.order_number}.')
            elif state == 'FAILED':
                messages.error(request, f'Payment failed for order #{existing_order.order_number}.')
            else:
                messages.info(request, f'Payment is still pending for order #{existing_order.order_number}.')
        except PhonePeError:
            if existing_order.payment_status == 'paid':
                messages.success(request, f'Payment completed for order #{existing_order.order_number}.')
            elif existing_order.payment_status == 'failed':
                messages.error(request, f'Payment failed for order #{existing_order.order_number}.')
            else:
                messages.warning(request, 'Unable to verify PhonePe payment right now. Please check again after a moment.')

        if web_snapshot and web_snapshot.get('merchant_ref') == merchant_order_id and existing_order.payment_status == 'paid':
            _clear_post_success_checkout_state(request)
        if kiosk_snapshot and kiosk_snapshot.get('merchant_ref') == merchant_order_id and existing_order.payment_status == 'paid':
            _set_last_kiosk_order(
                request,
                merchant_ref=merchant_order_id,
                order_id=existing_order.pk,
                company_id=kiosk_snapshot['company_id'],
                kiosk_slug=kiosk_snapshot.get('kiosk_slug', ''),
            )
            _clear_post_success_kiosk_state(request)

        if kiosk_snapshot and kiosk_snapshot.get('merchant_ref') == merchant_order_id:
            return _kiosk_redirect(
                'orders:kiosk_confirmation',
                kiosk_snapshot['company_id'],
                kiosk_snapshot.get('kiosk_slug', ''),
                pk=existing_order.pk,
            )
        if last_kiosk_order and last_kiosk_order.get('merchant_ref') == merchant_order_id:
            return _kiosk_redirect(
                'orders:kiosk_confirmation',
                last_kiosk_order['company_id'],
                last_kiosk_order.get('kiosk_slug', ''),
                pk=existing_order.pk,
            )
        return redirect('orders:order_confirmation', pk=existing_order.pk)

    if web_snapshot and web_snapshot.get('merchant_ref') == merchant_order_id:
        try:
            status_payload = _fetch_phonepe_order_status_with_retry(merchant_order_id)
        except PhonePeError:
            fallback_order = _find_existing_order_with_retry(merchant_order_id)
            if fallback_order and fallback_order.payment_status == 'paid':
                _clear_post_success_checkout_state(request)
                messages.success(request, f'Payment completed for order #{fallback_order.order_number}.')
                return redirect('orders:order_confirmation', pk=fallback_order.pk)
            if fallback_order and fallback_order.payment_status == 'failed':
                _clear_pending_online_checkout(request)
                messages.error(request, 'Sorry, your order was not completed.')
                return redirect('orders:checkout')
            if _can_reconcile_phonepe_testmode_locally(web_snapshot, merchant_order_id):
                try:
                    order = _create_new_order_from_pending_snapshot(
                        web_snapshot,
                        transaction_id=web_snapshot.get('gateway_order_id', ''),
                    )
                except StockUnavailableError as exc:
                    messages.error(request, f'Payment was received but the order could not be finalized: {exc}')
                    return redirect('orders:checkout')
                except Exception:
                    logger.exception('Test-mode local web reconciliation failed for %s', merchant_order_id)
                else:
                    _clear_post_success_checkout_state(request)
                    messages.success(request, f'Payment completed for order #{order.order_number}.')
                    return redirect('orders:order_confirmation', pk=order.pk)
            messages.warning(request, 'Unable to verify PhonePe payment right now. Please check My Orders after a moment or try again.')
            return redirect('orders:checkout')

        state = str(status_payload.get('state') or '').upper()
        payment_details = status_payload.get('paymentDetails') or []
        latest_payment = payment_details[0] if payment_details else {}
        phonepe_txn = latest_payment.get('transactionId') or status_payload.get('orderId') or web_snapshot.get('gateway_order_id', '')

        if state == 'COMPLETED':
            try:
                order = _create_new_order_from_pending_snapshot(web_snapshot, transaction_id=phonepe_txn)
            except StockUnavailableError as exc:
                messages.error(request, f'Payment was received but the order could not be finalized: {exc}')
                return redirect('orders:checkout')
            except Exception as exc:
                logger.exception('Post-payment order creation failed for %s', merchant_order_id)
                messages.error(request, f'Payment was received but the order could not be finalized: {exc}')
                return redirect('orders:checkout')

            _clear_post_success_checkout_state(request)
            messages.success(request, f'Payment completed for order #{order.order_number}.')
            return redirect('orders:order_confirmation', pk=order.pk)

        if state == 'FAILED':
            _clear_pending_online_checkout(request)
            messages.error(request, 'Sorry, your order was not completed.')
            return redirect('orders:checkout')

        messages.info(request, 'Payment is still pending. Your order has not been placed yet.')
        return redirect('orders:checkout')

    if kiosk_snapshot and kiosk_snapshot.get('merchant_ref') == merchant_order_id:
        company_id = int(kiosk_snapshot['company_id'])
        kiosk_slug = kiosk_snapshot.get('kiosk_slug', '')
        try:
            status_payload = _fetch_phonepe_order_status_with_retry(merchant_order_id)
        except PhonePeError:
            fallback_order = _find_existing_order_with_retry(merchant_order_id)
            if fallback_order and fallback_order.payment_status == 'paid':
                _set_last_kiosk_order(
                    request,
                    merchant_ref=merchant_order_id,
                    order_id=fallback_order.pk,
                    company_id=company_id,
                    kiosk_slug=kiosk_slug,
                )
                _clear_post_success_kiosk_state(request)
                messages.success(request, f'Payment completed for order #{fallback_order.order_number}.')
                return _kiosk_redirect('orders:kiosk_confirmation', company_id, kiosk_slug, pk=fallback_order.pk)
            if fallback_order and fallback_order.payment_status == 'failed':
                _clear_pending_kiosk_online_checkout(request)
                messages.error(request, 'Payment was not completed. Your kiosk order was not placed.')
                return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)
            if _can_reconcile_phonepe_testmode_locally(kiosk_snapshot, merchant_order_id):
                try:
                    order = _create_new_kiosk_order_from_pending_snapshot(
                        kiosk_snapshot,
                        transaction_id=kiosk_snapshot.get('gateway_order_id', ''),
                    )
                except StockUnavailableError as exc:
                    messages.error(request, f'Payment was received but the kiosk order could not be finalized: {exc}')
                    return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)
                except Exception:
                    logger.exception('Test-mode local kiosk reconciliation failed for %s', merchant_order_id)
                else:
                    _set_last_kiosk_order(
                        request,
                        merchant_ref=merchant_order_id,
                        order_id=order.pk,
                        company_id=company_id,
                        kiosk_slug=kiosk_slug,
                    )
                    _clear_post_success_kiosk_state(request)
                    messages.success(request, f'Payment completed for order #{order.order_number}.')
                    return _kiosk_redirect('orders:kiosk_confirmation', company_id, kiosk_slug, pk=order.pk)
            messages.warning(request, 'Unable to verify the payment right now. Your kiosk order has not been placed yet.')
            return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

        state = str(status_payload.get('state') or '').upper()
        payment_details = status_payload.get('paymentDetails') or []
        latest_payment = payment_details[0] if payment_details else {}
        phonepe_txn = latest_payment.get('transactionId') or status_payload.get('orderId') or kiosk_snapshot.get('gateway_order_id', '')

        if state == 'COMPLETED':
            try:
                order = _create_new_kiosk_order_from_pending_snapshot(kiosk_snapshot, transaction_id=phonepe_txn)
            except StockUnavailableError as exc:
                messages.error(request, f'Payment was received but the kiosk order could not be finalized: {exc}')
                return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)
            except Exception:
                logger.exception('Kiosk post-payment order creation failed for %s', merchant_order_id)
                messages.error(request, 'Payment was received but the kiosk order could not be finalized.')
                return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

            _set_last_kiosk_order(
                request,
                merchant_ref=merchant_order_id,
                order_id=order.pk,
                company_id=company_id,
                kiosk_slug=kiosk_slug,
            )
            _clear_post_success_kiosk_state(request)
            messages.success(request, f'Payment completed for order #{order.order_number}.')
            return _kiosk_redirect('orders:kiosk_confirmation', company_id, kiosk_slug, pk=order.pk)

        if state == 'FAILED':
            _clear_pending_kiosk_online_checkout(request)
            messages.error(request, 'Payment was not completed. Your kiosk order was not placed.')
            return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

        messages.info(request, 'Payment is still pending. Your kiosk order has not been placed yet.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    messages.error(request, 'Payment could not be matched to a pending checkout session.')
    if request.session.get('customer_id'):
        return redirect('orders:checkout')
    if last_kiosk_order and last_kiosk_order.get('merchant_ref') == merchant_order_id:
        return _kiosk_redirect(
            'orders:kiosk_confirmation',
            last_kiosk_order['company_id'],
            last_kiosk_order.get('kiosk_slug', ''),
            pk=last_kiosk_order['order_id'],
        )
    return redirect('accounts:customer_login')

@customer_login_required
def menu(request):
    """Direct entry point for the customer menu — no redirect hop."""
    from apps.menu.views import customer_menu
    return customer_menu(request)


@never_cache
@customer_login_required
def checkout(request):
    customer = request.current_customer
    company = _fresh_company(customer)
    summary = _build_cart_summary(customer, request.session.get('cart', {}), timezone.localdate(), request=request)
    request.session['cart'] = summary['cart']
    request.session.modified = True

    if not summary['items']:
        messages.warning(request, 'Your cart is empty. Order now.')
        return redirect('menu:menu')

    if not company.is_store_open:
        messages.error(request, _ordering_closed_message(company))
        return redirect('menu:cart')

    unavailable_items = _unavailable_cart_item_names(summary)
    if unavailable_items:
        messages.error(request, 'Some cart items are no longer available: ' + ', '.join(unavailable_items[:5]))
        return redirect('menu:cart')

    payment_modes = _allowed_payment_modes(company, customer, summary['my_pay'], summary['bill_to_company'])
    editing_order = None
    editing_order_id = request.session.get('editing_order_id')
    if editing_order_id:
        editing_order = Order.objects.filter(pk=editing_order_id, customer=customer, is_deleted=False).first()
        if editing_order and (editing_order.order_status in (OrderStatusChoices.DELIVERED, OrderStatusChoices.CANCELLED) or editing_order.picked_items_count):
            editing_order = None
            _clear_edit_order_session(request)
    # ── Wallet / royalty points availability ─────────────────────
    wallet_bal  = Decimal(str(getattr(customer, 'wallet_balance', 0) or 0))
    points_bal  = int(getattr(customer, 'royalty_points', 0) or 0)
    min_redeem  = int(getattr(company, 'royalty_min_redeem', 100) or 100)
    max_pct     = int(getattr(company, 'royalty_max_redeem_pct', 50) or 50)
    my_pay_val  = Decimal(str(summary.get('my_pay', 0)))
    # Max wallet the customer can apply (capped at order amount)
    wallet_max_apply  = min(wallet_bal, my_pay_val)
    # Max points they can redeem: must have >= min_redeem, capped at max_pct of my_pay
    points_eligible   = points_bal >= min_redeem and getattr(company, 'royalty_enabled', False)
    points_max_apply  = 0
    if points_eligible and my_pay_val > 0:
        points_max_apply = int(min(points_bal, my_pay_val * Decimal(str(max_pct)) / 100))

    # Collect live cart-level offers for unlock nudge on checkout page
    from apps.menu.models import Offer as _OfferModel
    _cafe = _resolve_customer_cafe(customer, company, request=request)
    _live_cart_offers = []
    for _ot in (_OfferModel.TYPE_FLAT, _OfferModel.TYPE_CART):
        for _o in _OfferModel.objects.filter(
            company=company, is_active=True, is_deleted=False, offer_type=_ot
        ).order_by('min_order_value'):
            if _o.is_live:
                _live_cart_offers.append(_o)

    cart_unlock_nudge = None
    if _live_cart_offers:
        _first_offer = _live_cart_offers[0]
        _min_value = Decimal(str(_first_offer.min_order_value or 0))
        cart_unlock_nudge = {
            'title': _first_offer.title,
            'min_order_value': _min_value,
            'remaining_value': max(Decimal('0.00'), _min_value - Decimal(str(summary['subtotal']))),
        } if _min_value > 0 else None

    context = {
        **summary,
        'company': company,
        'customer': customer,
        'payment_modes': payment_modes,
        'selected_payment_mode': payment_modes[0][0] if payment_modes else PaymentModeChoices.ONLINE,
        'ordering_closed_message': company.ordering_status_message if not company.is_store_open else '',
        'editing_order': editing_order,
        # wallet / points
        'wallet_balance': wallet_bal,
        'wallet_max_apply': wallet_max_apply,
        'royalty_points': points_bal,
        'points_max_apply': points_max_apply,
        'points_eligible': points_eligible,
        'royalty_min_redeem': min_redeem,
        'live_cart_offers': _live_cart_offers,
        'cart_unlock_nudge': cart_unlock_nudge,
        'selected_cafe': _cafe,
        'page_title': 'Checkout',
    }
    return render(request, 'orders/checkout.html', context)



@require_POST
@customer_login_required
def place_order(request):
    customer = request.current_customer
    company = _fresh_company(customer)

    summary = _build_cart_summary(customer, request.session.get('cart', {}), timezone.localdate(), request=request)
    request.session['cart'] = summary['cart']
    request.session.modified = True

    if not summary['items']:
        messages.error(request, 'Your cart is empty. Order now.')
        return redirect('menu:menu')
    if not company.is_store_open:
        messages.error(request, _ordering_closed_message(company))
        return redirect('menu:cart')
    unavailable_items = _unavailable_cart_item_names(summary)
    if unavailable_items:
        messages.error(request, 'Some cart items are no longer available: ' + ', '.join(unavailable_items[:5]))
        return redirect('menu:cart')

    try:
        order_type = int(request.POST.get('order_type', 0))
    except (TypeError, ValueError):
        order_type = 0
    if order_type not in (0, 1, 2):
        order_type = 0

    scheduled_dt = _parse_scheduled_datetime(request.POST.get('scheduled_date'))
    if request.POST.get('scheduled_date') and scheduled_dt is None:
        messages.error(request, 'Please enter a valid schedule date and time.')
        return redirect('orders:checkout')
    if scheduled_dt and scheduled_dt < timezone.now():
        messages.error(request, 'Scheduled time cannot be in the past.')
        return redirect('orders:checkout')

    benefit_date = timezone.localdate(scheduled_dt) if scheduled_dt else timezone.localdate()
    summary = _build_cart_summary(customer, request.session.get('cart', {}), benefit_date, request=request)
    request.session['cart'] = summary['cart']
    request.session.modified = True

    allowed_payment_modes = [value for value, _ in _allowed_payment_modes(company, customer, summary['my_pay'], summary['bill_to_company'])]
    payment_mode = request.POST.get('payment_mode', PaymentModeChoices.ONLINE)
    if payment_mode not in allowed_payment_modes:
        payment_mode = allowed_payment_modes[0] if allowed_payment_modes else PaymentModeChoices.ONLINE

    coupon = None
    coupon_discount = Decimal('0.00')
    after_offer_subtotal = summary['after_offer_subtotal']
    coupon_id = request.session.get('coupon_id')
    if coupon_id:
        try:
            from apps.core.models import Coupon
            coupon = Coupon.objects.get(pk=coupon_id)
            if coupon.company and coupon.company != company:
                coupon = None
            elif not coupon.is_valid:
                coupon = None
        except Exception:
            coupon = None
        if coupon is not None:
            coupon_discount = coupon.calculate_discount(after_offer_subtotal)
            if coupon_discount < 0:
                coupon_discount = Decimal('0.00')
        else:
            request.session.pop('coupon_id', None)
            request.session.pop('coupon_code', None)
            request.session.pop('coupon_discount', None)

    my_pay = max(Decimal('0.00'), summary['my_pay'] - coupon_discount)
    total_amount = max(Decimal('0.00'), summary['total'] - coupon_discount)

    wallet_bal = Decimal(str(getattr(customer, 'wallet_balance', 0) or 0))
    points_bal = int(getattr(customer, 'royalty_points', 0) or 0)
    min_redeem = int(getattr(company, 'royalty_min_redeem', 100) or 100)
    max_pct = int(getattr(company, 'royalty_max_redeem_pct', 50) or 50)
    # Monthly billing means deferred payment — wallet/points must not be deducted.
    # Discard any wallet/points POST fields when payment_mode is monthly.
    _is_deferred = payment_mode in (PaymentModeChoices.MONTHLY,)
    use_wallet = (request.POST.get('use_wallet') == '1') and not _is_deferred
    use_points = (request.POST.get('use_points') == '1') and not _is_deferred
    wallet_apply = Decimal('0.00')
    points_apply = 0

    if use_wallet and wallet_bal > 0 and my_pay > 0:
        wallet_apply = min(wallet_bal, my_pay)
        my_pay = max(Decimal('0.00'), my_pay - wallet_apply)
        total_amount = max(Decimal('0.00'), total_amount - wallet_apply)

    if use_points and getattr(company, 'royalty_enabled', False) and points_bal >= min_redeem and my_pay > 0:
        points_max = int(min(points_bal, my_pay * Decimal(str(max_pct)) / 100))
        points_apply = points_max
        pts_value = Decimal(str(points_apply))
        my_pay = max(Decimal('0.00'), my_pay - pts_value)
        total_amount = max(Decimal('0.00'), total_amount - pts_value)

    if my_pay <= Decimal('0.00') and summary['bill_to_company'] <= Decimal('0.00') and (wallet_apply > 0 or points_apply > 0):
        payment_mode = PaymentModeChoices.WALLET

    auto_confirm = payment_mode in (
        PaymentModeChoices.MONTHLY,
        PaymentModeChoices.COMPANY,
        PaymentModeChoices.WALLET,
    )
    initial_status = OrderStatusChoices.CONFIRMED if auto_confirm else OrderStatusChoices.PENDING
    payment_status = 'paid' if payment_mode in (PaymentModeChoices.COMPANY, PaymentModeChoices.WALLET) else (
        'approved' if payment_mode == PaymentModeChoices.MONTHLY else 'pending'
    )
    if payment_mode == PaymentModeChoices.ONLINE and my_pay <= Decimal('0.00'):
        payment_mode = PaymentModeChoices.COMPANY
        payment_status = 'paid'
        initial_status = OrderStatusChoices.CONFIRMED
        auto_confirm = True

    editing_order = None
    editing_order_id = request.session.get('editing_order_id')
    if editing_order_id:
        editing_order = Order.objects.filter(pk=editing_order_id, customer=customer, is_deleted=False).first()
        if editing_order and (
            editing_order.order_status in (OrderStatusChoices.DELIVERED, OrderStatusChoices.CANCELLED)
            or editing_order.picked_items_count
        ):
            editing_order = None
            _clear_edit_order_session(request)

    if editing_order and payment_mode == PaymentModeChoices.ONLINE:
        messages.error(request, 'Online payment is not available while editing an existing order. Please choose another payment mode.')
        return redirect('orders:checkout')

    if not editing_order and payment_mode == PaymentModeChoices.ONLINE:
        snapshot = _build_pending_online_checkout_snapshot(
            customer=customer,
            company=company,
            summary=summary,
            coupon=coupon,
            coupon_discount=coupon_discount,
            my_pay=my_pay,
            total_amount=total_amount,
            wallet_apply=wallet_apply,
            points_apply=points_apply,
            payment_mode=payment_mode,
            order_type=order_type,
            scheduled_dt=scheduled_dt,
            request=request,
        )
        _save_pending_online_checkout(request, snapshot)
        return redirect('orders:razorpay_initiate')

    try:
        with transaction.atomic():
            customer = customer.__class__._default_manager.select_related('company').select_for_update().get(pk=customer.pk)
            if editing_order:
                _restore_order_stock(editing_order)
                status_note = 'Order updated by customer.'
                summary_for_save = {**summary, 'my_pay': my_pay, 'total': total_amount}
                order = _rewrite_order_from_summary(
                    editing_order,
                    summary_for_save,
                    payment_mode,
                    payment_status,
                    order_type,
                    scheduled_dt,
                    initial_status,
                    status_note,
                    coupon=coupon,
                    coupon_discount=coupon_discount,
                )
                success_message = f'Order #{order.order_number} updated successfully!'
            else:
                initial_status_note = (
                    f'Order auto-confirmed after {payment_mode} payment.'
                    if auto_confirm else
                    'Order placed by customer and waiting for cashier confirmation.'
                )
                _resolved_web_cafe = _resolve_customer_cafe(customer, company, request=request)
                if coupon is not None and coupon_discount > 0:
                    coupon = Coupon.objects.select_for_update().filter(pk=coupon.pk).first()
                    if not coupon or not coupon.is_valid:
                        raise ValueError('Coupon is no longer valid.')
                    if coupon.usage_limit > 0:
                        used_by_customer = Order.objects.filter(
                            customer=customer,
                            coupon_id=coupon.pk,
                            is_deleted=False,
                        ).count()
                        if used_by_customer >= coupon.usage_limit:
                            raise ValueError('Coupon usage limit already reached for this employee.')
                    coupon_discount = coupon.calculate_discount(after_offer_subtotal)

                gross_total = max(Decimal('0.00'), summary['subtotal'] - summary['offer_discount'] + summary['packing'])
                eligible_subtotal = summary.get('eligible_subtotal', Decimal('0.00'))
                bill_to_company = customer.company_cover_for_amount(eligible_subtotal, benefit_date)
                my_pay = max(Decimal('0.00'), gross_total - bill_to_company - coupon_discount)
                total_amount = max(Decimal('0.00'), gross_total - coupon_discount)
                my_pay, total_amount, wallet_apply, points_apply = _recompute_wallet_points_from_locked_customer(
                    customer=customer,
                    company=company,
                    my_pay=my_pay,
                    total_amount=total_amount,
                    payment_mode=payment_mode,
                    use_wallet=use_wallet,
                    use_points=use_points,
                )
                if my_pay <= Decimal('0.00') and bill_to_company <= Decimal('0.00') and (wallet_apply > 0 or points_apply > 0):
                    payment_mode = PaymentModeChoices.WALLET
                if payment_mode == PaymentModeChoices.COMPANY and bill_to_company <= Decimal('0.00') and my_pay > Decimal('0.00'):
                    raise ValueError('No company-paid meals are remaining today. Please choose another payment mode.')
                auto_confirm = payment_mode in (
                    PaymentModeChoices.MONTHLY,
                    PaymentModeChoices.COMPANY,
                    PaymentModeChoices.WALLET,
                )
                initial_status = OrderStatusChoices.CONFIRMED if auto_confirm else OrderStatusChoices.PENDING
                payment_status = 'paid' if payment_mode in (PaymentModeChoices.COMPANY, PaymentModeChoices.WALLET) else (
                    'approved' if payment_mode == PaymentModeChoices.MONTHLY else 'pending'
                )
                initial_status_note = (
                    f'Order auto-confirmed after {payment_mode} payment.'
                    if auto_confirm else
                    'Order placed by customer and waiting for cashier confirmation.'
                )
                order = Order.objects.create(
                    company=company,
                    customer=customer,
                    cafe=_resolved_web_cafe,
                    coupon_id=coupon.pk if coupon else 0,
                    coupon_discount=coupon_discount,
                    subtotal=summary['subtotal'],
                    offer_discount=summary['offer_discount'],
                    shipping_cost=summary['packing'],
                    bill_to_company=bill_to_company,
                    my_pay=my_pay,
                    total_amount=total_amount,
                    wallet_used=wallet_apply,
                    points_redeemed=points_apply,
                    payment_mode=payment_mode,
                    payment_status=payment_status,
                    order_type=order_type,
                    order_status=initial_status,
                    scheduled_date=scheduled_dt,
                    order_number=_next_order_number('WEB', company=company),
                )

                _apply_wallet_and_points_to_customer(customer, order, wallet_apply, points_apply)

                for item in summary['items']:
                    product = item['product']
                    qty = item['qty']
                    gross_unit = item.get('site_price', product.price)
                    line_saving = item.get('line_saving', Decimal('0.00'))
                    effective_unit = (item['line_total'] / qty) if qty else gross_unit
                    _web_cafe = _resolve_customer_cafe(customer, company, request=request)
                    OrderItem.objects.create(
                        company=company,
                        order=order,
                        product=product,
                        counter=_resolve_product_counter(product, cafe=_web_cafe),
                        price=effective_unit,
                        unit_price=gross_unit,
                        item_offer_discount=line_saving,
                        qty=qty,
                        image_snapshot=str(product.image) if product.image else '',
                        created_at=timezone.now(),
                    )
                    if not _deduct_stock(product, qty, 'web', order.pk, company, f'Web order {order.order_number}'):
                        raise StockUnavailableError(f'{product.name} is out of stock or has insufficient quantity available.')

                _create_counter_tickets(order)

                if coupon is not None and coupon_discount > 0:
                    Coupon.objects.filter(pk=coupon.pk).update(used_count=F('used_count') + 1)

                _record_offer_usage_for_snapshot(customer, order, {
                    'items': [
                        {'offer_id': item['offer'].pk if item.get('offer') else None}
                        for item in summary['items']
                    ],
                    'cart_level_offer_id': summary['cart_level_offer'].pk if summary.get('cart_level_offer') else None,
                })

                if auto_confirm:
                    order.auto_ready_at = order.calculate_auto_ready_at(start_from=timezone.now())
                    order.save(update_fields=['auto_ready_at'])

                OrderStatus.objects.create(
                    order=order,
                    status=initial_status,
                    details=initial_status_note,
                    created_at=timezone.now(),
                )

                _notify_new_order(order, customer.name)

                request.session.pop('web_cafe_id', None)
                request.session.modified = True
                success_message = f'Order #{order.order_number} placed successfully!'

    except StockUnavailableError as exc:
        messages.error(request, str(exc))
        return redirect('menu:cart')
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('orders:checkout')

    request.session['cart'] = {}
    _clear_edit_order_session(request)
    request.session.pop('coupon_id', None)
    request.session.pop('coupon_code', None)
    request.session.pop('coupon_discount', None)
    request.session.modified = True

    try:
        if not editing_order:
            from apps.core.royalty_service import award_standard_points
            award_standard_points(customer, order)
    except Exception as _exc:
        logger.warning('Royalty award failed for order %s: %s', order.order_number, _exc)

    messages.success(request, success_message)
    return redirect('orders:order_confirmation', pk=order.pk)


@customer_login_required
def order_confirmation(request, pk):
    _promote_due_ready_orders(customer=request.current_customer)
    order = get_object_or_404(Order, pk=pk, customer=request.current_customer)
    items = order.items.select_related('product', 'counter').all()
    tickets = _ticket_queryset().filter(order=order)
    is_delivery_mode = getattr(order.company, 'is_packet_delivery', False)
    return render(request, 'orders/confirmation.html', {
        'order': order,
        'items': items,
        'tickets': tickets,
        'customer': request.current_customer,
        'progress_steps': _progress_steps(order),
        'is_delivery_mode': is_delivery_mode,
        'page_title': f'Order Placed — #{order.order_number}',
    })


@never_cache
@customer_login_required
def order_history(request):
    customer = request.current_customer
    _promote_due_ready_orders(customer=customer)
    base_orders = Order.objects.filter(customer=customer, is_deleted=False).order_by('-created_at')
    orders = base_orders.prefetch_related('items__product')[:80]

    stats = {
        'total_orders': base_orders.count(),
        'active_orders': base_orders.filter(order_status__in=[1, 2, 3, 4]).count(),
        'delivered_orders': base_orders.filter(order_status=OrderStatusChoices.DELIVERED).count(),
        'total_spend': base_orders.aggregate(total=Sum('total_amount')).get('total') or Decimal('0.00'),
    }

    for order in orders:
        if order.is_wallet_recharge:
            txn = order.recharge_transaction
            order.display_title = 'Wallet Recharge'
            order.item_count_display = 0
            order.can_leave_review = False
            order.recharge_wallet_amount = txn.wallet_delta if txn else order.subtotal
            order.recharge_payment_label = txn.get_payment_mode_display() if txn else order.get_payment_mode_display()
            continue
        prefetched_items = list(order.items.all())
        names = [item.product.name for item in prefetched_items if getattr(item, 'product', None)]
        if names:
            order.display_title = names[0] if len(names) == 1 else f"{names[0]} +{len(names)-1} more"
        else:
            order.display_title = 'Order items'
        order.item_count_display = len(prefetched_items)
        order.can_leave_review = (not order.review_given) and (
            order.order_status == OrderStatusChoices.DELIVERED
            or any(getattr(item, 'picked_up_at', None) for item in prefetched_items)
        )

    return render(request, 'orders/history.html', {
        'orders': orders,
        'stats': stats,
        'customer': customer,
        'page_title': 'Order History',
    })


@never_cache
@customer_login_required
def order_detail(request, pk):
    _promote_due_ready_orders(customer=request.current_customer)
    order = get_object_or_404(Order, pk=pk, customer=request.current_customer, is_deleted=False)
    items = order.items.select_related('product', 'counter').all()
    tickets = _ticket_queryset().filter(order=order)
    statuses = order.status_history.order_by('created_at')
    is_delivery_mode = getattr(order.company, 'is_packet_delivery', False)
    recharge_txn = order.recharge_transaction if order.is_wallet_recharge else None
    return render(request, 'orders/detail.html', {
        'order': order,
        'items': items,
        'tickets': tickets,
        'statuses': statuses,
        'customer': request.current_customer,
        'progress_steps': _progress_steps(order),
        'is_delivery_mode': is_delivery_mode,
        'recharge_txn': recharge_txn,
        'page_title': f'Order #{order.order_number}',
    })


@customer_login_required
def customer_order_history_feed(request):
    customer = request.current_customer
    _promote_due_ready_orders(customer=customer)
    orders = list(
        Order.objects.filter(customer=customer, is_deleted=False)
        .order_by('-created_at')
        .values('pk', 'order_status', 'updated_at')[:80]
    )
    response = JsonResponse({
        'orders': [
            {
                'pk': row['pk'],
                'order_status': row['order_status'],
                'updated_at': row['updated_at'].isoformat() if row['updated_at'] else '',
            }
            for row in orders
        ]
    })
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@staff_role_required('superadmin','admin','pos','cafeman')
def pickup_scan_terminal(request):
    code = (request.POST.get('pickup_code') if request.method == 'POST' else request.GET.get('pickup_code') or '').strip()
    company = None if getattr(request.user, 'is_superadmin', False) else getattr(request.user, 'company', None)
    item, ticket = _find_pickup_targets(code, company=company)
    expired_error = ''
    if ticket and _pickup_target_is_expired(ticket):
        expired_error = _pickup_expired_message(ticket)
        ticket = None
    elif item and _pickup_target_is_expired(item):
        expired_error = _pickup_expired_message(item)
        item = None
    context = {
        'pickup_code': code,
        'item': item,
        'ticket': ticket,
        'expired_error': expired_error,
        'page_title': 'Counter Pickup Scan',
    }
    return render(request, 'dashboard/orders/pickup_scan.html', context)


@require_POST
@staff_role_required('superadmin','admin','pos','cafeman')
def pickup_mark_collected(request, item_id):
    item = get_object_or_404(OrderItem.objects.select_related('order','order__company','product','counter'), pk=item_id, is_deleted=False)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    # SAFETY: block QR pickup for delivery-mode company orders
    if getattr(item.order.company, 'is_packet_delivery', False):
        error_msg = 'QR pickup is not enabled for this order. This company uses packet delivery.'
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect('orders:pickup_scan_terminal')
    if _pickup_target_is_expired(item):
        error_msg = _pickup_expired_message(item)
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect('orders:pickup_scan_terminal')
    already_done = bool(item.picked_up_at)
    if not already_done:
        item.picked_up_at = timezone.now()
        item.save(update_fields=['picked_up_at'])
        order = item.order
        if item.counter_id:
            from apps.orders.models import CounterTicket
            ticket = CounterTicket.objects.filter(order=order, counter=item.counter).first()
            if ticket:
                _sync_ticket_status_from_items(ticket)
        _refresh_order_delivery_state(order, detail='Counter item collected.')
        kot = {
            'order_number': order.order_number,
            'counter_name': item.counter.name if item.counter else 'Counter',
            'printer_label': item.counter.effective_printer_label if item.counter else '',
            'printer_route_key': item.counter.printer_route_key if item.counter else 'default',
            'company_name': order.company.name if order.company else '',
            'customer_name': order.display_customer_name,
            'customer_phone': order.display_customer_phone,
            'items': [{'name': item.product.name if item.product else 'Item',
                       'qty': item.qty, 'price': str(item.price)}],
            'total': str(item.price * item.qty),
            'created_at': timezone.now().strftime('%d-%m-%Y %H:%M'),
            'scheduled_date': '',
        }
        if is_ajax:
            return JsonResponse({'success': True, 'already_done': False, 'kot': kot, 'kind': 'item'})
        messages.success(request, f'Pickup marked for {item.product.name if item.product else "item"}.')
    else:
        if is_ajax:
            return JsonResponse({'success': True, 'already_done': True, 'kot': None, 'kind': 'item'})
        messages.info(request, 'This pickup was already completed earlier.')
    return redirect('orders:pickup_scan_terminal')


@require_POST
@staff_role_required('superadmin','admin','pos','cafeman')
def pickup_ticket_mark_collected(request, ticket_id):
    from apps.orders.models import CounterTicket
    ticket = get_object_or_404(_ticket_queryset(), pk=ticket_id)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    # SAFETY: block QR pickup for delivery-mode company orders
    if getattr(ticket.order.company, 'is_packet_delivery', False):
        error_msg = 'QR pickup is not enabled for this order. This company uses packet delivery.'
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect('orders:pickup_scan_terminal')
    if _pickup_target_is_expired(ticket):
        error_msg = _pickup_expired_message(ticket)
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect('orders:pickup_scan_terminal')
    changed = _mark_ticket_collected(ticket)
    kot = ticket.kot_data()
    if is_ajax:
        return JsonResponse({'success': True, 'already_done': not changed, 'kot': kot, 'kind': 'ticket'})
    messages.success(request, f'{ticket.ticket_number} marked collected.')
    return redirect('orders:pickup_scan_terminal')


@require_POST
@customer_login_required
def edit_order(request, pk):
    customer = request.current_customer
    order = get_object_or_404(Order, pk=pk, customer=customer, is_deleted=False)
    if order.order_status in (OrderStatusChoices.DELIVERED, OrderStatusChoices.CANCELLED) or order.picked_items_count:
        messages.error(request, 'This order can no longer be edited.')
        return redirect('orders:order_detail', pk=pk)

    company = _fresh_company(customer)
    if not company.is_store_open:
        messages.error(request, _ordering_closed_message(company))
        return redirect('orders:order_detail', pk=pk)

    _load_order_into_cart(request, order)
    messages.info(request, f'Editing order #{order.order_number}. Update your cart and checkout to save changes.')
    return redirect('orders:checkout')


@require_POST
@customer_login_required
def set_web_cafe(request):
    """
    AJAX POST: store the customer's chosen cafe in the session for this order.
    Validates that the cafe belongs to the customer's company.
    """
    from django.http import JsonResponse
    from apps.menu.models import Cafe as _CafeModel
    customer = request.current_customer
    company  = customer.company
    cafe_id  = request.POST.get('cafe_id', '').strip()
    if not cafe_id:
        request.session.pop('web_cafe_id', None)
        request.session.modified = True
        return JsonResponse({'success': True, 'cafe_name': None})
    cafe = _CafeModel.objects.filter(
        pk=cafe_id, company=company, is_active=True, is_deleted=False
    ).first()
    if not cafe:
        return JsonResponse({'success': False, 'error': 'Invalid cafe selection.'}, status=400)
    request.session['web_cafe_id'] = cafe.pk
    request.session.modified = True
    return JsonResponse({'success': True, 'cafe_name': cafe.name})


@require_POST
@customer_login_required
def cancel_order(request, pk):
    order = get_object_or_404(Order, pk=pk, customer=request.current_customer)
    messages.error(request, 'Once an order is placed, cancellation and refund are not allowed. T&C Applied.')
    return redirect('orders:order_detail', pk=pk)



@require_POST
@customer_login_required
def reorder_order(request, pk):
    customer = request.current_customer
    company = _fresh_company(customer)
    order = get_object_or_404(Order, pk=pk, customer=customer, is_deleted=False)

    if not company.is_store_open:
        messages.error(request, _ordering_closed_message(company))
        return redirect('orders:order_detail', pk=pk)

    cart = request.session.get('cart', {})
    added = 0
    skipped = []

    for item in order.items.select_related('product').all():
        product = item.product
        if not product or product.company_id != customer.company_id or product.is_deleted or not product.is_active:
            skipped.append(item.product.name if item.product else 'Unknown item')
            continue
        _web_cap = _get_web_max_qty(product)
        if not product.is_available_now() or _web_cap <= 0:
            skipped.append(product.name)
            continue

        key = str(product.pk)
        current_qty = int(cart.get(key, {}).get('qty', 0) or 0)
        new_qty = min(current_qty + item.qty, _web_cap)
        if new_qty <= current_qty:
            skipped.append(product.name)
            continue

        cart[key] = {
            'qty': new_qty,
            'price': str(product.price),
            'name': product.name,
        }
        added += max(0, new_qty - current_qty)

    request.session['cart'] = cart
    request.session.modified = True

    if added:
        messages.success(request, f'{added} item(s) added back to your cart.')
    else:
        messages.warning(request, 'No items from this order are currently available.')

    if skipped and added:
        messages.warning(request, 'Some items could not be reordered because they are unavailable or out of stock.')

    return redirect('menu:cart')


@require_POST
@customer_login_required
def apply_coupon(request):
    """
    AJAX endpoint — validate coupon and return discount amount.
    FIX-2/3: The coupon eligibility and discount are computed entirely from the
    server-side session cart summary.  The browser-sent subtotal value is
    IGNORED — it is accepted in the POST body only for legacy compatibility but
    is never used in any calculation.  This ensures the preview amount shown to
    the customer is identical to what will be deducted when the order is saved.
    """
    from apps.core.models import Coupon

    code = request.POST.get('coupon_code', '').strip().upper()
    customer = request.current_customer
    company  = _fresh_company(customer)

    if not code:
        return JsonResponse({'success': False, 'error': 'Enter a coupon code.'})

    try:
        coupon = Coupon.objects.get(code=code)
    except Coupon.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid coupon code.'})

    if coupon.company and coupon.company != company:
        return JsonResponse({'success': False, 'error': 'This coupon is not valid for your company.'})

    if not coupon.is_valid:
        return JsonResponse({'success': False, 'error': 'This coupon has expired or is inactive.'})

    if coupon.usage_limit > 0:
        used_by_customer = Order.objects.filter(
            customer=customer,
            coupon_id=coupon.pk,
            is_deleted=False,
        ).count()
        if used_by_customer >= coupon.usage_limit:
            return JsonResponse({'success': False, 'error': 'This Coupon is already used Try another one'})

    # FIX-2/3: recompute the cart summary server-side so the coupon base is
    # after_offer_subtotal — exactly the same value used by place_order().
    # Never trust the browser-submitted subtotal.
    summary = _build_cart_summary(customer, request.session.get('cart', {}), request=request)
    after_offer_subtotal = summary['after_offer_subtotal']

    discount = coupon.calculate_discount(after_offer_subtotal)
    if discount <= 0:
        return JsonResponse({'success': False, 'error': f'Minimum order of ₹{coupon.min_order} required.'})

    request.session['coupon_id'] = coupon.pk
    request.session['coupon_code'] = coupon.code
    request.session['coupon_discount'] = str(discount)
    request.session.modified = True

    return JsonResponse({
        'success': True,
        'code': coupon.code,
        'discount': str(discount),
        'description': coupon.description or f'{coupon.get_discount_type_display()} discount applied',
    })


# ─────────────────────────────────────────────────────────────
#  LIVE DISPLAY BOARD  (public screen showing active orders)
# ─────────────────────────────────────────────────────────────

def _display_board_company(request, company_id=None):
    companies = Company.objects.filter(is_active=True, is_deleted=False).order_by('name')
    company = None
    requested = company_id or request.GET.get('company')
    if requested:
        company = companies.filter(pk=requested).first()
    require_selection = company is None and companies.count() > 1
    if not require_selection and company is None and companies.count() == 1:
        company = companies.first()
    return companies, company, require_selection


def _display_board_config(company, request):
    if not company:
        return None
    from apps.core.models import resolve_display_board_config
    return resolve_display_board_config(company=company, slug=request.GET.get('board', ''))


def _serialize_display_groups(qs):
    groups = {
        'pending': [],
        'confirmed': [],
        'preparing': [],
        'ready': [],
    }
    status_map = {
        OrderStatusChoices.PENDING: 'pending',
        OrderStatusChoices.CONFIRMED: 'confirmed',
        OrderStatusChoices.PREPARING: 'preparing',
        OrderStatusChoices.READY: 'ready',
    }
    for order in qs:
        key = status_map.get(order.order_status)
        if not key:
            continue
        customer_name = order.display_customer_name
        item_names = []
        for item in order.items.all()[:4]:
            item_name = ''
            if getattr(item, 'product', None):
                item_name = (item.product.name or '').strip()
            if item_name:
                item_names.append(item_name)
        groups[key].append({
            'id': order.pk,
            'order_number': order.order_number,
            'customer_name': customer_name or 'Guest',
            'announcement_name': customer_name or order.order_number,
            'items_preview': ', '.join(item_names),
        })
    return groups


def _display_board_payload(company, require_selection=False):
    if require_selection and company is None:
        groups = _serialize_display_groups([])
        counts = {key: len(value) for key, value in groups.items()}
        return {
            'groups': groups,
            'counts': counts,
            'generated_at': timezone.now().isoformat(),
            'requires_company_selection': True,
        }

    company_id = getattr(company, 'pk', None)
    if company_id is not None:
        cache_key = f'neverq:display-board-payload:{company_id}'
        cached_payload = cache.get(cache_key)
        if cached_payload is not None:
            return cached_payload

    qs = Order.objects.filter(
        is_deleted=False,
        order_status__in=[1, 2, 3, 4],
    ).select_related('customer', 'company').prefetch_related('items__product').order_by('created_at')
    if company:
        qs = qs.filter(company=company)
    else:
        qs = qs.none()
    groups = _serialize_display_groups(qs)
    counts = {key: len(value) for key, value in groups.items()}
    payload = {
        'groups': groups,
        'counts': counts,
        'generated_at': timezone.now().isoformat(),
        'requires_company_selection': False,
    }
    if company_id is not None:
        cache.set(cache_key, payload, 10)
    return payload


def display_board(request, company_id=None):
    """Public-facing live board — no login required."""
    companies, company, require_selection = _display_board_company(request, company_id=company_id)
    board_cfg = _display_board_config(company, request)
    from apps.core.models import DisplayBoardConfig
    board_configs = DisplayBoardConfig.objects.none()
    if company:
        board_configs = (
            DisplayBoardConfig.objects
            .filter(company=company, is_active=True)
            .select_related('building')
            .order_by('name')
        )
    board_data = _display_board_payload(company, require_selection=require_selection)
    columns = [
        ('pending', (board_cfg.pending_label if board_cfg else 'Pending')),
        ('confirmed', (board_cfg.confirmed_label if board_cfg else 'Order Placed')),
        ('preparing', (board_cfg.preparing_label if board_cfg else 'Preparing')),
        ('ready', (board_cfg.ready_label if board_cfg else 'Food Ready')),
    ]
    return render(request, 'orders/display_board.html', {
        'company': company,
        'companies': companies,
        'board_cfg': board_cfg,
        'board_configs': board_configs,
        'columns': columns,
        'page_title': 'Live Display Board',
        'refresh_seconds': 8,
        'initial_board_data': board_data,
        'feed_url': reverse('orders:display_board_feed') + (f'?company={company.pk}' if company else ''),
        'requires_company_selection': require_selection,
    })


@customer_login_required
def customer_order_status_feed(request, pk):
    _promote_due_ready_orders(customer=request.current_customer)
    order = get_object_or_404(
        Order,
        pk=pk,
        customer=request.current_customer,
        is_deleted=False,
    )
    response = JsonResponse({
        'order_status': order.order_status,
        'updated_at': order.updated_at.isoformat() if order.updated_at else '',
        'picked_items_count': order.picked_items_count,
    })
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


def display_board_feed(request):
    """Public JSON feed for the live display board screen.
    Restricted to XHR/fetch callers only — direct URL navigation is blocked.
    """
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()
    _, company, require_selection = _display_board_company(request)
    payload = _display_board_payload(company, require_selection=require_selection)
    response = JsonResponse(payload)
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


# ─────────────────────────────────────────────────────────────
#  KOT — Kitchen Order Ticket
# ─────────────────────────────────────────────────────────────

from apps.accounts.decorators import staff_role_required as _staff_role_required


@_staff_role_required('superadmin', 'admin', 'pos', 'cafeman')
def kot_data(request, pk):
    """Returns KOT data as JSON for direct Bluetooth printing — no new window."""
    from apps.accounts.models import StaffUser

    user = request.user

    try:
        order = Order.objects.get(pk=pk, is_deleted=False)
    except Order.DoesNotExist:
        return JsonResponse({'error': f'Order #{pk} not found.'}, status=404)

    if not isinstance(user, StaffUser) or not user.is_superadmin:
        if hasattr(user, 'company') and user.company and order.company != user.company:
            return JsonResponse({'error': 'Forbidden'}, status=403)

    items = []
    for item in order.items.select_related('product').all():
        items.append({
            'name': item.product.name if item.product else 'Item',
            'qty': item.qty,
            'price': str(item.price),
        })

    primary_counter = None
    counters = list(order.items.select_related('counter').exclude(counter__isnull=True).values_list('counter_id', flat=True).distinct()[:2])
    if len(counters) == 1:
        primary_counter = order.items.select_related('counter').filter(counter_id=counters[0]).first().counter

    return JsonResponse({
        'order_number': order.order_number,
        'customer_name': order.display_customer_name,
        'customer_phone': order.display_customer_phone,
        'company_name': order.company.name,
        'items': items,
        'total': str(order.total_amount),
        'payment_mode': order.get_payment_mode_display(),
        'order_type': order.get_order_type_display(),
        'created_at': order.created_at.strftime('%d-%m-%Y %H:%M') if order.created_at else '',
        'scheduled_date': order.scheduled_date.strftime('%d-%m-%Y') if order.scheduled_date else '',
        'note': order.session_item_date or '',
        'counter_name': primary_counter.name if primary_counter else '',
        'printer_label': primary_counter.effective_printer_label if primary_counter else '',
        # Return '' (not 'default') when there is no counter so resolveRouteInfo
        # falls through to window.btPreferredRouteKey and uses whatever printer
        # is currently connected — prevents a silent route mismatch.
        'printer_route_key': primary_counter.printer_route_key if primary_counter else '',
    })



@_staff_role_required('superadmin', 'admin', 'pos', 'cafeman')
def kot_print_html(request, pk):
    """
    Returns a self-contained, auto-printing HTML page for an order KOT.
    Works with any printer (USB, network, thermal) via the browser print dialog.
    This is the reliable fallback when Bluetooth is unavailable.
    """
    from apps.accounts.models import StaffUser
    from django.http import HttpResponse

    user = request.user

    try:
        order = Order.objects.get(pk=pk, is_deleted=False)
    except Order.DoesNotExist:
        return HttpResponse('<h3>Order not found.</h3>', status=404)

    if not isinstance(user, StaffUser) or not user.is_superadmin:
        if hasattr(user, 'company') and user.company and order.company != user.company:
            return HttpResponse('<h3>Forbidden.</h3>', status=403)

    items = order.items.select_related('product').filter(is_deleted=False)

    item_rows = ''.join(
        '<tr><td>' + (item.product.name if item.product else 'Item') + '</td>'
        '<td style="text-align:right;padding-left:12px;">' + str(item.qty) + '</td></tr>'
        for item in items
    )

    scheduled = order.scheduled_date.strftime('%d-%m-%Y') if order.scheduled_date else ''
    created   = order.created_at.strftime('%d-%m-%Y %H:%M') if order.created_at else ''
    note      = order.session_item_date or ''
    phone_str = (' &middot; ' + order.display_customer_phone) if order.display_customer_phone else ''
    cafe_row  = ('<div class="info"><strong>Cafeteria:</strong> ' + order.cafe.name + '</div>') if getattr(order, 'cafe', None) else ''
    sched_row = ('<div class="info"><strong>Delivery:</strong> ' + scheduled + '</div>') if scheduled else ''
    note_row  = ('<div class="info"><strong>Note:</strong> ' + note + '</div>') if note else ''
    total_str = '{:.2f}'.format(order.total_amount)

    html = (
        '<!DOCTYPE html><html><head>'
        '<meta charset="utf-8">'
        '<title>KOT ' + order.order_number + '</title>'
        '<style>'
        '@page{size:80mm auto;margin:4mm}'
        '*{box-sizing:border-box;margin:0;padding:0}'
        'body{font-family:"Courier New",Courier,monospace;font-size:12px;width:72mm;color:#000}'
        '.center{text-align:center}'
        '.company{font-size:15px;font-weight:700;text-transform:uppercase}'
        '.title{font-size:11px;letter-spacing:2px;margin-top:2px}'
        '.div{border-top:1px dashed #333;margin:6px 0}'
        'table{width:100%;border-collapse:collapse;margin:4px 0}'
        'th{font-size:10px;text-align:left;border-bottom:1px solid #000;padding:2px 0}'
        'td{padding:3px 0;vertical-align:top;border-bottom:1px dotted #ccc}'
        '.tot{font-weight:700;font-size:13px;border-top:2px solid #000;border-bottom:none}'
        '.info{font-size:11px;margin:2px 0}'
        '.foot{text-align:center;font-size:10px;margin-top:8px}'
        '@media screen{body{margin:20px auto;border:1px dashed #ccc;padding:12px}}'
        '</style></head><body>'
        '<div class="center">'
        '<div class="company">' + order.company.name + '</div>'
        '<div class="title">KITCHEN ORDER TICKET</div>'
        '</div>'
        '<div class="div"></div>'
        '<div class="info"><strong>Order:</strong> ' + order.order_number + '</div>'
        '<div class="info"><strong>Date:</strong> ' + created + '</div>'
        '<div class="info"><strong>Customer:</strong> ' + order.display_customer_name + phone_str + '</div>'
        + cafe_row + sched_row + note_row +
        '<div class="info"><strong>Payment:</strong> ' + order.get_payment_mode_display() + '</div>'
        '<div class="div"></div>'
        '<table>'
        '<thead><tr><th>Item</th><th style="text-align:right">Qty</th></tr></thead>'
        '<tbody>' + item_rows + '</tbody>'
        '<tfoot><tr class="tot">'
        '<td><strong>TOTAL</strong></td>'
        '<td style="text-align:right"><strong>Rs.' + total_str + '</strong></td>'
        '</tr></tfoot></table>'
        '<div class="foot">Thank you!</div>'
        '<script>window.addEventListener("load",function(){setTimeout(function(){window.print();},350);});</script>'
        '</body></html>'
    )

    return HttpResponse(html, content_type='text/html; charset=utf-8')


@_staff_role_required('superadmin', 'admin', 'pos', 'cafeman')
def new_orders_poll(request):
    """Poll endpoint — returns orders newer than a given timestamp for auto-alert."""
    from apps.accounts.models import StaffUser
    from django.utils import timezone as tz

    user = request.user
    since_str = request.GET.get('since', '')
    company_id = request.GET.get('company', '')

    company_filter = {}
    if isinstance(user, StaffUser) and not user.is_superadmin and user.company:
        company_filter['company'] = user.company
    elif company_id:
        company_filter['company_id'] = company_id

    qs = Order.objects.filter(
        is_deleted=False,
        order_status__in=[OrderStatusChoices.PENDING, OrderStatusChoices.CONFIRMED],
        **company_filter,
    )

    if since_str:
        try:
            since_dt = tz.make_aware(datetime.strptime(since_str, '%Y-%m-%dT%H:%M:%S'))
            qs = qs.filter(created_at__gt=since_dt)
        except (ValueError, OverflowError, OSError):
            pass

    orders = []
    for order in qs.select_related('customer', 'cafe').prefetch_related('items__product').order_by('-created_at')[:20]:
        orders.append({
            'id': order.pk,
            'order_number': order.order_number,
            'customer': order.display_customer_name,
            'phone': order.display_customer_phone,
            'cafe_name': order.cafe.name if getattr(order, 'cafe', None) else '',
            'total': str(order.total_amount),
            'items_count': order.items.count(),
            'created_at': order.created_at.strftime('%Y-%m-%dT%H:%M:%S') if order.created_at else '',
            'order_status': order.order_status,
            'status_label': order.status_label,
            'payment_mode': order.get_payment_mode_display(),
            'scheduled_date': order.scheduled_date.strftime('%d-%m-%Y') if order.scheduled_date else '',
        })

    return JsonResponse({'orders': orders, 'count': len(orders)})


# ════════════════════════════════════════════════════════════════
#  SELF-KIOSK  —  company-scoped, session-based, no login needed
# ════════════════════════════════════════════════════════════════

def _kiosk_redirect(view_name, company_id, slug, **kwargs):
    """
    Build a slug-preserving redirect response for kiosk views.
    Appends ?kiosk=<slug> when a slug is active so the kiosk config
    (theme/logo/layout) is never lost across error-path redirects.
    """
    from django.urls import reverse
    url = reverse(view_name, kwargs={'company_id': company_id, **kwargs})
    if slug:
        url = f'{url}?kiosk={slug}'
    return redirect(url)


def _kiosk_read_slug(request):
    """
    Read kiosk slug: GET param takes precedence (deep-link / direct entry),
    falls back to whatever is already stored in the session.
    Always writes the winning value back to the session.
    """
    slug = request.GET.get('kiosk', '').strip()
    if slug:
        request.session['kiosk_slug'] = slug
    else:
        slug = request.session.get('kiosk_slug', '')
    return slug


def _kiosk_pricing_mode(request):
    """
    Public kiosk uses the staff/base price. Visitor and room-service pricing
    are POS-only.
    """
    if request.session.get('kiosk_pricing_mode') != PRICING_MODE_STAFF:
        request.session['kiosk_pricing_mode'] = PRICING_MODE_STAFF
        request.session.modified = True
    return PRICING_MODE_STAFF


def kiosk_home(request, company_id):
    """
    Kiosk entry point.
    Hierarchy: Offering → Category → Products
    Schedules respected at all three levels.
    schedule_bypass on a product skips offering/category schedule but still
    respects the product's own explicit time/date window.
    """
    from apps.core.models import Company as CompanyModel, Building
    from apps.menu.models import Advertise, Category, Cafe, Offering, FoodType
    company = get_object_or_404(CompanyModel, pk=company_id, is_active=True, is_deleted=False)
    request.session['kiosk_company_id'] = company.pk
    request.session['kiosk_cart'] = request.session.get('kiosk_cart', {})
    building, cafe = _get_kiosk_scope(request, company)

    # ── Per-kiosk config (optional — falls back to company defaults) ──
    # Preserve slug across navigation: save to session when present in GET,
    # fall back to session value when navigating within the kiosk flow.
    from apps.core.models import KioskConfig
    kiosk_slug = _kiosk_read_slug(request)
    pricing_mode = _kiosk_pricing_mode(request)
    kiosk_cfg = KioskConfig.objects.filter(
        company=company, slug=kiosk_slug, is_active=True
    ).first() if kiosk_slug else None

    # ── Veg filter ────────────────────────────────────────────────
    if 'veg' in request.GET:
        veg_filter = (request.GET.get('veg') or '').strip()
        request.session['kiosk_veg_filter'] = veg_filter
        request.session.modified = True
    else:
        veg_filter = (request.session.get('kiosk_veg_filter', '') or '').strip()
    calorie_max_raw = (request.GET.get('calorie_max') or '').strip()
    try:
        kiosk_calorie_max = int(calorie_max_raw) if calorie_max_raw else None
    except (TypeError, ValueError):
        kiosk_calorie_max = None
    kiosk_calorie_presets = [200, 400, 600, 800]

    # ── Step 1: Live offerings ────────────────────────────────────
    offering_qs = Offering.objects.filter(
        company=company, is_active=True, is_deleted=False
    ).order_by('position_order', 'name')
    live_offerings = [o for o in offering_qs if o.is_active_now()]

    selected_offering_id = (request.GET.get('offering') or '').strip()
    selected_offering = next((o for o in live_offerings if str(o.pk) == selected_offering_id), None)

    selected_category_id = (request.GET.get('category') or '').strip()

    # ── Step 2: Categories under selected offering ────────────────
    if selected_offering:
        cats_qs = Category.objects.filter(
            companies=company, is_deleted=False,
            products__offering=selected_offering,
        ).distinct().prefetch_related('schedules', 'company_statuses').order_by('position_order', 'name')
    else:
        cats_qs = Category.objects.filter(
            companies=company, is_deleted=False,
        ).prefetch_related('schedules', 'company_statuses').order_by('position_order', 'name')

    # Filter categories by open_days
    live_categories = [c for c in cats_qs if c.is_active_now(company)]
    selected_category = next(
        (c for c in live_categories if str(c.pk) == selected_category_id), None
    )

    # ── Step 3: Products ──────────────────────────────────────────
    product_qs = Product.objects.filter(
        company=company, is_active=True, is_kiosk_active=True, is_deleted=False,
    ).select_related('category', 'offering').prefetch_related(
        'counter_mappings__counter', 'food_type', 'category__company_statuses'
    ).order_by('category__position_order', 'category__name', 'position_order', 'name')

    if selected_offering:
        product_qs = product_qs.filter(offering=selected_offering)
    if selected_category:
        product_qs = product_qs.filter(category=selected_category)

    if cafe:
        product_qs = product_qs.filter(
            Q(counter_mappings__counter__cafe=cafe) | Q(counter_mappings__isnull=True)
        ).distinct()
    elif building:
        product_qs = product_qs.filter(
            Q(counter_mappings__counter__cafe__building=building) |
            Q(counter_mappings__counter__cafe__isnull=True) |
            Q(counter_mappings__isnull=True)
        ).distinct()

    # Respect full schedule chain (is_available_now handles bypass internally)
    available = [p for p in product_qs if p.is_available_now() and _web_stock_available(p, 1)]

    # ── Veg filter ────────────────────────────────────────────────
    if veg_filter == 'veg':
        filtered = []
        for p in available:
            names = [ft.name.lower() for ft in p.food_type.all()]
            if any('veg' in n and 'non' not in n for n in names):
                filtered.append(p)
        available = filtered
    if kiosk_calorie_max is not None:
        available = [
            p for p in available
            if p.calories is not None and p.calories <= kiosk_calorie_max
        ]
    # Non-veg = show everything (no filter needed)

    for p in available:
        p.display_price = _get_site_price(p, company, building=building, cafe=cafe, pricing_mode=pricing_mode)
        p.effective_web_qty = _get_web_max_qty(p)

    cart = request.session.get('kiosk_cart', {})
    cart_count = sum(v.get('qty', 0) for v in cart.values())
    buildings = Building.objects.filter(company=company, is_deleted=False, is_active=True).order_by('name')
    cafes = Cafe.objects.filter(company=company, is_deleted=False, is_active=True).select_related('building').order_by('building__name', 'name')
    if building:
        cafes = cafes.filter(Q(building=building) | Q(building__isnull=True))

    advert_qs = Advertise.objects.filter(
        is_active=True,
        status=Advertise.STATUS_APPROVED,
    ).filter(companies=company).distinct().select_related('media_asset').prefetch_related('holiday_schedules').order_by('position_order')
    adverts = [ad for ad in advert_qs if ad.is_live]

    # ── Featured extra products (up to 10, no duplicates with current grid) ──
    available_pks = {p.pk for p in available}
    dedupe_with_current_grid = bool(selected_offering or selected_category)
    featured_qs = Product.objects.filter(
        company=company,
        is_active=True,
        is_kiosk_active=True,
        featured_in_kiosk_extra=True,
        is_deleted=False,
    ).select_related('category').prefetch_related('food_type', 'category__company_statuses').order_by(
        'category__position_order', 'category__name', 'position_order', 'name'
    )

    if cafe:
        featured_qs = featured_qs.filter(
            Q(counter_mappings__counter__cafe=cafe) | Q(counter_mappings__isnull=True)
        ).distinct()
    elif building:
        featured_qs = featured_qs.filter(
            Q(counter_mappings__counter__cafe__building=building) |
            Q(counter_mappings__counter__cafe__isnull=True) |
            Q(counter_mappings__isnull=True)
        ).distinct()

    featured_candidates = [
        p for p in featured_qs
        if p.is_available_now()
        and _web_stock_available(p, 1)
        and (not dedupe_with_current_grid or p.pk not in available_pks)
    ]

    if veg_filter == 'veg':
        veg_featured = []
        for p in featured_candidates:
            names = [ft.name.lower() for ft in p.food_type.all()]
            if any('veg' in n and 'non' not in n for n in names):
                veg_featured.append(p)
        featured_candidates = veg_featured
    if kiosk_calorie_max is not None:
        featured_candidates = [
            p for p in featured_candidates
            if p.calories is not None and p.calories <= kiosk_calorie_max
        ]

    featured_products = featured_candidates[:10]
    featured_ids = {p.pk for p in featured_products}
    browse_products = [p for p in available if p.pk not in featured_ids] if featured_ids else available

    for p in featured_products:
        p.display_price = _get_site_price(p, company, building=building, cafe=cafe, pricing_mode=pricing_mode)
        p.effective_web_qty = _get_web_max_qty(p)

    return render(request, 'kiosk/home.html', {
        'company': company,
        'categories': live_categories,
        'selected_category': selected_category,
        'products': available,
        'browse_products': browse_products,
        'featured_products': featured_products,
        'offerings': live_offerings,
        'selected_offering': selected_offering,
        'veg_filter': veg_filter,
        'kiosk_calorie_max': kiosk_calorie_max,
        'kiosk_calorie_presets': kiosk_calorie_presets,
        'cart_count': cart_count,
        'cart': cart,
        'company_id': company_id,
        'buildings': buildings,
        'cafes': cafes,
        'selected_building': building,
        'selected_cafe': cafe,
        'kiosk_cfg': kiosk_cfg,
        'kiosk_slug': kiosk_slug,
        'pricing_mode': pricing_mode,
        'is_room_service_order': pricing_mode == PRICING_MODE_ROOM_SERVICE,
        'adverts': adverts,
        'live_products_count': len(available),
        'live_categories_count': len(live_categories),
        'live_offerings_count': len(live_offerings),
        'page_title': f'{company.name} — Self Order',
    })


def kiosk_cart(request, company_id):
    from apps.core.models import Company as CompanyModel
    company = get_object_or_404(CompanyModel, pk=company_id, is_active=True, is_deleted=False)
    building, cafe = _get_kiosk_scope(request, company)
    kiosk_slug = _kiosk_read_slug(request)
    pricing_mode = _kiosk_pricing_mode(request)
    cart = request.session.get('kiosk_cart', {})
    items = []
    gross_subtotal = Decimal('0')        # pre-offer gross
    effective_subtotal = Decimal('0')    # post-offer net (what customer pays)
    total_offer_discount = Decimal('0')
    for pid, v in list(cart.items()):
        try:
            p = Product.objects.get(pk=int(pid), company=company, is_active=True, is_deleted=False)
            qty = int(v.get('qty', 1))
            site_price = _get_site_price(p, company, building=building, cafe=cafe, pricing_mode=pricing_mode)
            live_offer = _get_live_offer_for_product(company, p, cafe=cafe)
            line, line_saving = _apply_offer_to_line(live_offer, site_price, qty)
            gross_subtotal += site_price * qty
            effective_subtotal += line
            total_offer_discount += line_saving
            items.append({'product': p, 'qty': qty, 'site_price': site_price, 'line_total': line, 'line_saving': line_saving, 'offer': live_offer})
        except (Product.DoesNotExist, ValueError):
            cart.pop(pid, None)
    request.session['kiosk_cart'] = cart
    # Build list of allowed payment modes from company settings.
    # Monthly billing is intentionally excluded from kiosk — it requires an
    # authenticated customer account and cannot be verified at a public terminal.
    kiosk_payment_modes = []
    if getattr(company, 'cod_payment', False):
        kiosk_payment_modes.append(('cash',   'Cash at Counter', '💵'))
    if getattr(company, 'online_payment', True):
        kiosk_payment_modes.append(('online', 'Online / UPI',    '📱'))
    if not kiosk_payment_modes:
        kiosk_payment_modes.append(('online', 'Online / UPI', '📱'))

    return render(request, 'kiosk/cart.html', {
        'company': company,
        'company_id': company_id,
        'items': items,
        'subtotal': gross_subtotal,            # gross pre-offer (for strikethrough display)
        'effective_subtotal': effective_subtotal,  # net post-offer (what customer pays)
        'offer_discount': total_offer_discount,
        'cart_count': len(items),
        'cart': cart,
        'kiosk_payment_modes': kiosk_payment_modes,
        'selected_building': building,
        'selected_cafe': cafe,
        'kiosk_slug': kiosk_slug,
        'pricing_mode': pricing_mode,
        'is_room_service_order': pricing_mode == PRICING_MODE_ROOM_SERVICE,
        'page_title': 'Your Order',
    })


@require_POST
def kiosk_cart_update(request, company_id):
    from apps.core.models import Company as CompanyModel

    company = get_object_or_404(
        CompanyModel, pk=company_id, is_active=True, is_deleted=False
    )

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse(
            {'success': False, 'error': 'Invalid request payload.'},
            status=400,
        )

    pid = str(data.get('product_id', '')).strip()
    if not pid:
        return JsonResponse(
            {'success': False, 'error': 'Missing product_id.'},
            status=400,
        )

    try:
        qty = int(data.get('qty', 0))
    except (TypeError, ValueError):
        return JsonResponse(
            {'success': False, 'error': 'Invalid quantity.'},
            status=400,
        )

    cart = request.session.get('kiosk_cart', {})

    if qty <= 0:
        cart.pop(pid, None)
        qty = 0
    else:
        product = Product.objects.filter(
            pk=pid,
            company=company,
            is_active=True,
            is_kiosk_active=True,
            is_deleted=False,
        ).first()
        if not product or not product.is_available_now():
            return JsonResponse(
                {'success': False, 'error': 'This item is not available right now.'},
                status=400,
            )
        min_qty = _get_order_min_qty(product)
        max_qty = _get_web_max_qty(product)
        if max_qty <= 0:
            return JsonResponse(
                {'success': False, 'error': 'This item is sold out for now.'},
                status=400,
            )
        qty = max(min_qty, min(qty, max_qty))
        cart[pid] = {'qty': qty}

    request.session['kiosk_cart'] = cart
    request.session.modified = True

    total_items = 0
    for value in cart.values():
        try:
            total_items += int(value.get('qty', 0) or 0)
        except (TypeError, ValueError):
            continue

    return JsonResponse({'success': True, 'cart_count': total_items, 'qty': qty})


@require_POST
def kiosk_place_order(request, company_id):
    from apps.core.models import Company as CompanyModel
    from apps.accounts.models import Customer
    company = get_object_or_404(CompanyModel, pk=company_id, is_active=True, is_deleted=False)
    building, cafe = _get_kiosk_scope(request, company)
    kiosk_slug = request.session.get('kiosk_slug', '')
    pricing_mode = _kiosk_pricing_mode(request)
    cart = request.session.get('kiosk_cart', {})
    if not cart:
        messages.error(request, 'Cart is empty.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    if not company.is_store_open:
        messages.error(request, company.ordering_status_message or 'Ordering is currently closed.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    payment_mode = request.POST.get('payment_mode', PaymentModeChoices.CASH)
    if payment_mode not in (PaymentModeChoices.CASH, PaymentModeChoices.ONLINE):
        payment_mode = PaymentModeChoices.CASH
    customer_name  = request.POST.get('customer_name', 'Kiosk Customer').strip() or 'Kiosk Customer'
    if not customer_name:
        messages.error(request, 'Customer name is required.')
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    customer_phone = re.sub(r'\D', '', request.POST.get('customer_phone', '').strip())
    if customer_phone and len(customer_phone) != 10:
        customer_phone = ''

    items = []
    gross_subtotal = Decimal('0')
    effective_subtotal = Decimal('0')
    total_offer_discount = Decimal('0')
    unavailable = []
    for pid, v in list(cart.items()):
        try:
            p = Product.objects.get(pk=int(pid), company=company, is_active=True, is_deleted=False)
            qty = int(v.get('qty', 1))
            if qty <= 0:
                continue
            if not p.is_available_now():
                unavailable.append(f'{p.name} (not available now)')
                continue
            min_qty = _get_order_min_qty(p)
            max_qty = _get_web_max_qty(p)
            if max_qty <= 0:
                unavailable.append(f'{p.name} (sold out)')
                continue
            if qty < min_qty or qty > max_qty:
                unavailable.append(f'{p.name} (qty must be between {min_qty} and {max_qty})')
                continue
            if not _web_stock_available(p, qty):
                unavailable.append(f'{p.name} (insufficient stock)')
                continue
            site_price = _get_site_price(p, company, building=building, cafe=cafe, pricing_mode=pricing_mode)
            live_offer = _get_live_offer_for_product(company, p, cafe=cafe)
            effective_line_total, line_saving = _apply_offer_to_line(live_offer, site_price, qty)
            gross_line = site_price * qty
            gross_subtotal += gross_line
            effective_subtotal += effective_line_total
            total_offer_discount += line_saving
            items.append({'product': p, 'qty': qty, 'site_price': site_price,
                          'line_total': effective_line_total, 'offer': live_offer,
                          'line_saving': line_saving})
        except (Product.DoesNotExist, ValueError):
            pass

    if not items:
        if unavailable:
            messages.error(request, 'All items in your cart are unavailable: ' + ', '.join(unavailable))
        else:
            messages.error(request, 'Cart is empty or products unavailable.')
        return _kiosk_redirect('orders:kiosk_home', company_id, kiosk_slug)

    if unavailable:
        messages.warning(request, 'Some items were removed (unavailable/sold out): ' + ', '.join(unavailable))

    if payment_mode == PaymentModeChoices.ONLINE:
        _clear_last_kiosk_order(request)
        _clear_pending_kiosk_online_checkout(request)
        snapshot = _build_pending_kiosk_online_checkout_snapshot(
            company=company,
            cafe=cafe,
            kiosk_slug=kiosk_slug,
            customer_name=customer_name,
            customer_phone=customer_phone,
            gross_subtotal=gross_subtotal,
            effective_subtotal=effective_subtotal,
            total_offer_discount=total_offer_discount,
            items=items,
        )
        _save_pending_kiosk_online_checkout(request, snapshot)
        return _kiosk_redirect('orders:kiosk_razorpay_initiate', company_id, kiosk_slug)

    payment_status = 'pending'
    initial_status = OrderStatusChoices.PENDING

    kiosk_customer, created = Customer.objects.get_or_create(
        email=f'kiosk@{company.name[:20].replace(" ","").lower()}.kiosk',
        defaults={
            'name': 'Kiosk Orders',
            'company': company,
            'is_active': True,
            'meal_benefit': 'none',
        }
    )
    if not created and kiosk_customer.meal_benefit != 'none':
        Customer.objects.filter(pk=kiosk_customer.pk).update(meal_benefit='none', subsidy_eligible=False)
        kiosk_customer.meal_benefit = 'none'

    try:
        with transaction.atomic():
            order = Order.objects.create(
                company=company,
                customer=kiosk_customer,
                customer_name_snapshot=customer_name,
                customer_phone_snapshot=customer_phone,
                subtotal=gross_subtotal,
                total_amount=effective_subtotal,
                my_pay=effective_subtotal,
                offer_discount=total_offer_discount,
                cafe=cafe,
                payment_mode=payment_mode,
                payment_status=payment_status,
                order_type=1,
                order_status=initial_status,
                order_number=_next_order_number('KIO', company=company),
            )
            for item in items:
                p = item['product']
                OrderItem.objects.create(
                    company=company,
                    order=order,
                    product=p,
                    counter=_resolve_product_counter(p, cafe=cafe),
                    price=(item['line_total'] / item['qty']) if item['qty'] else item['site_price'],
                    unit_price=item['site_price'],
                    item_offer_discount=item.get('line_saving', 0),
                    qty=item['qty'],
                    created_at=timezone.now(),
                )
                if not _deduct_stock(p, item['qty'], 'web', order.pk, company, f'Kiosk {order.order_number}'):
                    raise StockUnavailableError(f'{p.name} is out of stock or has insufficient quantity available.')
            _create_counter_tickets(order)
            OrderStatus.objects.create(
                order=order, status=initial_status,
                details=f'Kiosk order placed by {customer_name}. Payment: {payment_mode}.',
                created_at=timezone.now(),
            )
            try:
                from apps.accounts.models import StaffUser
                from apps.core.models import Notification
                staff_qs = StaffUser.objects.filter(
                    company=company, is_active=True,
                    role__in=[StaffUser.ROLE_ADMIN, StaffUser.ROLE_POS, StaffUser.ROLE_CAFEMAN],
                )
                for staff in staff_qs:
                    Notification.objects.create(
                        company=company, staff_user=staff,
                        notif_type=Notification.TYPE_ORDER,
                        title=f'New Kiosk Order #{order.order_number}',
                        message=f'{order.display_customer_name} placed a kiosk order for Rs. {order.total_amount}',
                        link=f'/dashboard/orders/{order.pk}/',
                    )
            except Exception as _exc:
                logger.warning('Kiosk notification failed for %s: %s', order.order_number, _exc)
    except StockUnavailableError as exc:
        messages.error(request, str(exc))
        return _kiosk_redirect('orders:kiosk_cart', company_id, kiosk_slug)

    request.session['kiosk_cart'] = {}
    request.session.modified = True

    return _kiosk_redirect('orders:kiosk_confirmation', company_id, kiosk_slug, pk=order.pk)


def kiosk_reset(request, company_id):
    """
    True kiosk filter reset: clears all session-backed filter keys, then
    redirects to kiosk_home preserving the active kiosk slug so the config
    theme/layout remains intact.  The cart is intentionally NOT cleared.
    """
    from django.urls import reverse
    kiosk_slug = request.session.get('kiosk_slug', '')
    for key in ('kiosk_building_id', 'kiosk_cafe_id', 'kiosk_veg_filter'):
        request.session.pop(key, None)
    request.session.modified = True
    redirect_url = reverse('orders:kiosk_home', kwargs={'company_id': company_id})
    if kiosk_slug:
        redirect_url = f'{redirect_url}?kiosk={kiosk_slug}'
    return redirect(redirect_url)


def kiosk_confirmation(request, company_id, pk):
    from apps.core.models import Company as CompanyModel
    company = get_object_or_404(CompanyModel, pk=company_id, is_active=True, is_deleted=False)
    order = get_object_or_404(Order.objects.select_related('customer', 'cafe'), pk=pk, company=company)
    kiosk_slug = _kiosk_read_slug(request)
    return render(request, 'kiosk/confirmation.html', {
        'company': company,
        'company_id': company_id,
        'order': order,
        'items': order.items.select_related('product', 'counter').all(),
        'tickets': _ticket_queryset().filter(order=order),
        'selected_building': getattr(order.cafe, 'building', None),
        'selected_cafe': order.cafe,
        'kiosk_slug': kiosk_slug,
        'page_title': 'Order Confirmed',
    })




def kiosk_receipt(request, company_id, pk):
    from apps.core.models import Company as CompanyModel
    company = get_object_or_404(CompanyModel, pk=company_id, is_active=True, is_deleted=False)
    order = get_object_or_404(Order.objects.select_related('customer', 'cafe'), pk=pk, company=company)
    tickets = _ticket_queryset().filter(order=order)
    kiosk_slug = _kiosk_read_slug(request)
    return render(request, 'kiosk/receipt.html', {
        'company': company,
        'company_id': company_id,
        'order': order,
        'tickets': tickets,
        'items': order.items.select_related('product', 'counter').all(),
        'selected_building': getattr(order.cafe, 'building', None),
        'selected_cafe': order.cafe,
        'kiosk_slug': kiosk_slug,
        'page_title': f'Pickup Slip — {order.order_number}',
    })


# ─────────────────────────────────────────────────────────────
#  CUSTOMER SELF-SCAN TERMINAL  (public — mounted at counter kiosk)
#  URL: /orders/self-scan/<company_id>/
#  Optional: /orders/self-scan/<company_id>/?counter=<counter_id>
# ─────────────────────────────────────────────────────────────

def customer_self_scan(request, company_id):
    """
    Public self-service scan page mounted at each counter kiosk.
    Customer types or scans their QR scan code → system marks the
    matching CounterTicket as collected and shows confirmation.
    """
    from apps.core.models import Company as CompanyModel
    from apps.menu.models import Cafe, Counter as CounterModel
    from apps.orders.models import CounterTicket

    company = get_object_or_404(CompanyModel, pk=company_id, is_active=True, is_deleted=False)

    # Optional: counter this terminal is mounted at (for display only)
    counter_id = request.GET.get('counter') or request.POST.get('counter')
    counter = None
    if counter_id:
        counter = CounterModel.objects.filter(pk=counter_id, company=company, is_deleted=False).first()

    result = None
    scan_code = ''

    if request.method == 'POST':
        scan_code = (request.POST.get('scan_code') or '').strip().upper()

        if not scan_code:
            result = {'type': 'error', 'error': 'Please enter or scan a code.'}
        else:
            # Look up by scan_code or ticket_number
            ticket = (
                CounterTicket.objects
                .select_related('order', 'order__customer', 'counter', 'counter__cafe', 'company')
                .prefetch_related('order__items__product')
                .filter(company=company)
                .filter(
                    Q(scan_code__iexact=scan_code) |
                    Q(ticket_number__iexact=scan_code)
                )
                .first()
            )

            if not ticket:
                result = {'type': 'error', 'error': f'No ticket found for code "{scan_code}". Please check the code and try again.'}
            elif _pickup_target_is_expired(ticket):
                result = {'type': 'error', 'error': _pickup_expired_message(ticket)}
            elif getattr(ticket.order.company, 'is_packet_delivery', False):
                # SAFETY: delivery-mode company orders cannot be collected via self-scan QR
                result = {'type': 'error', 'error': 'QR pickup is not enabled for this order.'}
            else:
                from django.utils import timezone as _tz
                now_local = _tz.localtime(_tz.now())
                current_time = now_local.time()
                if company.order_from_time and company.order_to_time:
                    if company.order_from_time <= company.order_to_time:
                        in_window = company.order_from_time <= current_time <= company.order_to_time
                    else:
                        in_window = current_time >= company.order_from_time or current_time <= company.order_to_time
                    if not in_window:
                        result = {
                            'type': 'error',
                            'error': f'This QR code is outside the company pickup window ({company.order_window_label}). T&C Applied.'
                        }
                    elif ticket.status == CounterTicket.STATUS_COLLECTED:
                        result = {'type': 'already', 'ticket': ticket}
                    else:
                        changed = _mark_ticket_collected(ticket)
                        result = {'type': 'success', 'ticket': ticket}
                        scan_code = ''  # clear for next customer
                elif ticket.status == CounterTicket.STATUS_COLLECTED:
                    result = {'type': 'already', 'ticket': ticket}
                else:
                    changed = _mark_ticket_collected(ticket)
                    result = {'type': 'success', 'ticket': ticket}
                    scan_code = ''  # clear for next customer

    return render(request, 'orders/self_scan.html', {
        'company': company,
        'company_id': company_id,
        'counter': counter,
        'scan_code': scan_code,
        'result': result,
        'page_title': f'{company.name} — Counter Scan',
    })

# ─── Delivery-mode: dashboard confirmation & packet label views ───────────────

@staff_role_required('superadmin', 'admin', 'pos', 'cafeman')
def delivery_confirmation_list(request):
    """
    Dashboard page: lists ready/preparing orders for packet-delivery companies.
    Staff can filter and bulk-mark orders as delivered after physical handover.
    """
    from apps.core.models import Company as CompanyModel
    from apps.menu.models import Cafe

    user = request.user
    # Restrict non-superadmin to their own company
    if getattr(user, 'is_superadmin', False):
        delivery_companies = CompanyModel.objects.filter(
            fulfillment_mode='packet_delivery', is_active=True, is_deleted=False
        )
    else:
        user_company = getattr(user, 'company', None)
        if user_company and getattr(user_company, 'is_packet_delivery', False):
            delivery_companies = CompanyModel.objects.filter(pk=user_company.pk)
        else:
            delivery_companies = CompanyModel.objects.none()

    # Filter controls
    company_id = request.GET.get('company', '')
    date_str   = request.GET.get('date', '')
    status_filter = request.GET.get('status', '')

    qs = Order.objects.filter(
        company__in=delivery_companies,
        is_deleted=False,
    ).select_related('company', 'customer', 'cafe').prefetch_related('items__product')

    if company_id:
        qs = qs.filter(company_id=company_id)
    if date_str:
        try:
            from datetime import datetime as _dt
            filter_date = _dt.strptime(date_str, '%Y-%m-%d').date()
            qs = qs.filter(created_at__date=filter_date)
        except (ValueError, TypeError):
            pass
    else:
        # Default: today
        qs = qs.filter(created_at__date=timezone.localdate())
        date_str = timezone.localdate().strftime('%Y-%m-%d')

    if status_filter:
        try:
            qs = qs.filter(order_status=int(status_filter))
        except (ValueError, TypeError):
            pass
    else:
        # Default: show active (not yet delivered/cancelled)
        qs = qs.filter(order_status__in=[
            OrderStatusChoices.CONFIRMED,
            OrderStatusChoices.PREPARING,
            OrderStatusChoices.READY,
        ])

    qs = qs.order_by('created_at')

    return render(request, 'dashboard/orders/delivery_confirmation.html', {
        'orders': qs,
        'delivery_companies': delivery_companies,
        'company_id_filter': company_id,
        'date_filter': date_str,
        'status_filter': status_filter,
        'status_options': [
            ('', 'Active (Confirmed/Preparing/Ready)'),
            (str(OrderStatusChoices.CONFIRMED),  'Confirmed'),
            (str(OrderStatusChoices.PREPARING),  'Preparing'),
            (str(OrderStatusChoices.READY),      'Ready'),
            (str(OrderStatusChoices.DELIVERED),  'Delivered'),
        ],
        'page_title': 'Delivery Confirmation',
    })


@require_POST
@staff_role_required('superadmin', 'admin', 'pos', 'cafeman')
def delivery_mark_delivered(request):
    """
    POST action: mark selected delivery-mode orders as Delivered.
    Expects: order_ids (comma-separated or multiple), delivered_by, received_by, remarks
    """
    from apps.core.models import Company as CompanyModel

    user = request.user
    raw_ids = request.POST.getlist('order_ids')
    if not raw_ids:
        # Also accept comma-separated single value
        raw_ids = [x.strip() for x in (request.POST.get('order_ids', '')).split(',') if x.strip()]

    if not raw_ids:
        messages.error(request, 'No orders selected.')
        return redirect('orders:delivery_confirmation_list')

    delivered_by  = (request.POST.get('delivered_by', '') or '').strip()
    received_by   = (request.POST.get('received_by', '') or '').strip()
    remarks       = (request.POST.get('remarks', '') or '').strip()

    try:
        order_id_ints = [int(x) for x in raw_ids]
    except (ValueError, TypeError):
        messages.error(request, 'Invalid order selection.')
        return redirect('orders:delivery_confirmation_list')

    # Build queryset — only delivery-mode company orders, not already delivered/cancelled
    qs = Order.objects.filter(
        pk__in=order_id_ints,
        company__fulfillment_mode='packet_delivery',
        is_deleted=False,
    ).exclude(order_status__in=[OrderStatusChoices.DELIVERED, OrderStatusChoices.CANCELLED])

    # Non-superadmin can only mark their own company's orders
    if not getattr(user, 'is_superadmin', False):
        user_company = getattr(user, 'company', None)
        if user_company:
            qs = qs.filter(company=user_company)
        else:
            qs = qs.none()

    now = timezone.now()
    detail_parts = ['Delivered by packet delivery.']
    if delivered_by:
        detail_parts.append(f'Staff: {delivered_by}.')
    if received_by:
        detail_parts.append(f'Received by: {received_by}.')
    if remarks:
        detail_parts.append(f'Remarks: {remarks}.')
    detail_text = ' '.join(detail_parts)

    count = 0
    for order in qs.select_related('company'):
        order.order_status = OrderStatusChoices.DELIVERED
        order.save(update_fields=['order_status', 'updated_at'])
        OrderStatus.objects.create(
            order=order,
            status=OrderStatusChoices.DELIVERED,
            details=detail_text,
            created_at=now,
        )
        count += 1

    if count:
        messages.success(request, f'{count} order(s) marked as Delivered.')
    else:
        messages.warning(request, 'No eligible orders were updated. They may already be delivered/cancelled.')

    # Redirect back preserving filters
    redirect_url = request.POST.get('next', '')
    if not redirect_url:
        redirect_url = reverse('orders:delivery_confirmation_list')
    return redirect(redirect_url)


@staff_role_required('superadmin', 'admin', 'pos', 'cafeman')
def delivery_packet_labels(request):
    """
    Thermal-printer-friendly packet slip/label page for delivery-mode orders.
    Shows one label per order (or per item if preferred).
    URL accepts ?order_ids=1,2,3  OR  ?date=YYYY-MM-DD&company=<id>
    """
    from apps.core.models import Company as CompanyModel

    user = request.user

    # Resolve order set — either explicit IDs or date+company filter
    raw_ids = request.GET.get('order_ids', '')
    date_str = request.GET.get('date', '')
    company_id = request.GET.get('company', '')

    if raw_ids:
        try:
            order_id_ints = [int(x.strip()) for x in raw_ids.split(',') if x.strip()]
        except (ValueError, TypeError):
            order_id_ints = []
        qs = Order.objects.filter(
            pk__in=order_id_ints,
            company__fulfillment_mode='packet_delivery',
            is_deleted=False,
        )
    else:
        qs = Order.objects.filter(
            company__fulfillment_mode='packet_delivery',
            is_deleted=False,
        )
        if date_str:
            try:
                from datetime import datetime as _dt
                filter_date = _dt.strptime(date_str, '%Y-%m-%d').date()
                qs = qs.filter(created_at__date=filter_date)
            except (ValueError, TypeError):
                qs = qs.filter(created_at__date=timezone.localdate())
        else:
            qs = qs.filter(created_at__date=timezone.localdate())

        if company_id:
            qs = qs.filter(company_id=company_id)

    # Non-superadmin restricted to their company
    if not getattr(user, 'is_superadmin', False):
        user_company = getattr(user, 'company', None)
        if user_company:
            qs = qs.filter(company=user_company)
        else:
            qs = qs.none()

    orders = qs.select_related(
        'company', 'customer', 'cafe'
    ).prefetch_related(
        'items__product', 'items__product__category', 'items__product__offering'
    ).order_by('created_at')

    return render(request, 'orders/delivery_packet_label.html', {
        'orders': orders,
        'print_date': timezone.localdate(),
        'page_title': 'Packet Labels',
    })


# ─────────────────────────────────────────────────────────────
#  KITCHEN DISPLAY SCREEN  (public — no login — read-only)
#  URL: /orders/kitchen/              (auto-selects if 1 company)
#  URL: /orders/kitchen/<company_id>/ (explicit company)
# ─────────────────────────────────────────────────────────────

def kitchen_display(request, company_id=None):
    """Public kitchen screen — read-only, no login required."""
    companies = Company.objects.filter(is_active=True, is_deleted=False).order_by('name')
    company = None
    requested = company_id or request.GET.get('company')
    if requested:
        company = companies.filter(pk=requested).first()
    if company is None and companies.count() == 1:
        company = companies.first()

    feed_url = reverse('orders:kitchen_display_feed')
    if company:
        feed_url += f'?company={company.pk}'

    return render(request, 'orders/kitchen_display.html', {
        'company': company,
        'companies': companies,
        'page_title': 'Kitchen Display',
        'feed_url': feed_url,
    })


def kitchen_display_feed(request):
    """JSON feed for kitchen display — item-wise aggregation, public, polled every 8s."""
    from collections import defaultdict
    company_id = request.GET.get('company')
    company = None
    if company_id:
        company = Company.objects.filter(
            pk=company_id, is_active=True, is_deleted=False
        ).first()

    pending_items = defaultdict(int)   # status=1
    cooking_items = defaultdict(int)   # status=2,3
    pending_orders = 0
    cooking_orders = 0

    if company:
        qs = (
            Order.objects
            .filter(company=company, is_deleted=False, order_status__in=[1, 2, 3])
            .prefetch_related('items__product')
            .order_by('created_at')
        )
        for order in qs:
            is_pending = order.order_status == 1
            if is_pending:
                pending_orders += 1
            else:
                cooking_orders += 1
            for item in order.items.all():
                if item.is_deleted:
                    continue
                name = (item.product.name if item.product else 'Item').strip()
                if is_pending:
                    pending_items[name] += item.qty
                else:
                    cooking_items[name] += item.qty

    resp = JsonResponse({
        'pending': [{'name': k, 'qty': v} for k, v in sorted(pending_items.items())],
        'cooking': [{'name': k, 'qty': v} for k, v in sorted(cooking_items.items())],
        'pending_orders': pending_orders,
        'cooking_orders': cooking_orders,
        'ts': timezone.now().isoformat(),
    })
    resp['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp['Pragma'] = 'no-cache'
    return resp
