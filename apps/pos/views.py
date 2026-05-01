from apps.accounts.decorators import staff_role_required
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Sum
from django.utils import timezone
from .models import POSProduct, POSOrder, POSOrderItem
from apps.orders.views import _deduct_stock
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError


def _company_pos_payment_choices(company):
    choices = []
    if getattr(company, 'pos_cash_enabled', True):
        choices.append((POSOrder.PAYMENT_CASH, 'Cash'))
    if getattr(company, 'pos_card_enabled', True):
        choices.append((POSOrder.PAYMENT_CARD, 'Card'))
    if getattr(company, 'pos_upi_enabled', True):
        choices.append((POSOrder.PAYMENT_UPI, 'UPI'))
    return choices


def _pos_card_fee(company, amount):
    amount = Decimal(str(amount or 0))
    if amount <= 0:
        return Decimal('0.00')
    percent = Decimal(str(getattr(company, 'pos_card_fee_percent', Decimal('3.50')) or 0))
    return (amount * percent / Decimal('100')).quantize(Decimal('0.01'))


def _menu_order_min_qty(product):
    try:
        return max(1, int(getattr(product, 'min_qty', 1) or 1))
    except (TypeError, ValueError):
        return 1


def _menu_order_max_qty(product):
    try:
        return max(1, int(getattr(product, 'max_qty', 999999) or 999999))
    except (TypeError, ValueError):
        return 999999


def _menu_pos_max_qty(product):
    min_qty = _menu_order_min_qty(product)
    cap = _menu_order_max_qty(product)
    try:
        pos_qty = max(0, int(getattr(product, 'pos_qty', 0) or 0))
    except (TypeError, ValueError):
        pos_qty = 0
    cap = min(cap, pos_qty)
    return cap if cap >= min_qty else 0


POS_CUSTOMER_TYPE_META = (
    {'key': POSOrder.CUSTOMER_STAFF, 'price_key': 's', 'label': 'Staff', 'icon': 'bi-person-badge'},
    {'key': POSOrder.CUSTOMER_VISITOR, 'price_key': 'v', 'label': 'Visitor', 'icon': 'bi-person'},
    {'key': POSOrder.CUSTOMER_ROOM_SERVICE, 'price_key': 'r', 'label': 'Room Svc', 'icon': 'bi-house-door'},
)


@staff_role_required('superadmin','admin','pos')
def pos_terminal(request):
    from apps.core.access import get_staff_site_companies, user_can_access_company
    user = request.user

    # Multi-site: allow switching via ?company=<pk>
    accessible = get_staff_site_companies(user)
    company_pk = request.GET.get('company', '')
    if company_pk and user_can_access_company(user, company_pk):
        from apps.core.models import Company as Co
        company = Co.objects.filter(pk=company_pk, is_active=True, is_deleted=False).first()
    else:
        company = user.company or accessible.first()

    if not company:
        messages.error(request, 'No company assigned to your account. Ask a Super Admin.')
        return redirect('dashboard:home')

    # Show BOTH: Menu products (with kiosk/POS qty) AND legacy POS-only products
    from apps.menu.models import Product as MenuProduct
    from apps.menu.pricing import (
        get_available_pricing_modes,
        get_effective_price,
        PRICING_MODE_STAFF, PRICING_MODE_VISITOR, PRICING_MODE_ROOM_SERVICE,
    )
    raw_menu_products = list(MenuProduct.objects.filter(
        company=company, is_active=True, is_pos_active=True, is_deleted=False, pos_qty__gt=0
    ).select_related('category').prefetch_related('category__company_statuses').order_by(
        'category__position_order', 'category__name', 'position_order', 'name'
    ))
    menu_products = []
    available_customer_types = set()

    # Build a pk-keyed price dict serialised as JSON so the template never
    # has to bridge dynamic model attributes → HTML data-attributes → JS.
    pos_prices = {}
    for _mp in raw_menu_products:
        if _menu_pos_max_qty(_mp) <= 0 or not _mp.is_available_now():
            continue
        available_modes = get_available_pricing_modes(_mp, company=company)
        if not available_modes:
            continue
        menu_products.append(_mp)
        _mp.pos_order_min_qty = _menu_order_min_qty(_mp)
        _mp.pos_order_max_qty = _menu_pos_max_qty(_mp)
        available_customer_types.update(available_modes)
        pos_prices[_mp.pk] = {
            'available': available_modes,
            'v': float(get_effective_price(_mp, company, pricing_mode=PRICING_MODE_VISITOR)) if PRICING_MODE_VISITOR in available_modes else 0,
            's': float(get_effective_price(_mp, company, pricing_mode=PRICING_MODE_STAFF)) if PRICING_MODE_STAFF in available_modes else 0,
            'r': float(get_effective_price(_mp, company, pricing_mode=PRICING_MODE_ROOM_SERVICE)) if PRICING_MODE_ROOM_SERVICE in available_modes else 0,
        }

    products = list(menu_products)
    pos_customer_types = [
        meta for meta in POS_CUSTOMER_TYPE_META
        if meta['key'] in available_customer_types
    ]
    default_customer_type = pos_customer_types[0]['key'] if pos_customer_types else POSOrder.CUSTOMER_STAFF

    today = timezone.localdate()
    today_qs = POSOrder.objects.filter(
        company=company, is_deleted=False
    ).exclude(created_at__isnull=True).filter(created_at__date=today)

    payment_choices = _company_pos_payment_choices(company)
    if not payment_choices:
        messages.error(request, 'No POS payment mode is enabled for this company.')
        return redirect('dashboard:home')

    context = {
        'products':           products,
        'pos_prices':         pos_prices,
        'company':            company,
        'companies':          accessible,
        'today_orders':       today_qs.count(),
        'today_revenue':      today_qs.aggregate(t=Sum('total_amount'))['t'] or 0,
        'payment_choices':    payment_choices,
        'pos_customer_types':  pos_customer_types,
        'default_customer_type': default_customer_type,
        'card_fee_percent':   getattr(company, 'pos_card_fee_percent', Decimal('3.50')) or Decimal('0.00'),
        'page_title':         'POS Terminal',
    }
    return render(request, 'pos/terminal.html', context)


@require_POST
@staff_role_required('superadmin','admin','pos')
def pos_place_order(request):
    from apps.core.access import get_staff_site_companies, user_can_access_company
    from apps.core.models import Company as Co
    user = request.user

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request format. Please try again.'})

    company_id = data.get('company_id')
    if company_id and user_can_access_company(user, company_id):
        company = Co.objects.filter(pk=company_id, is_active=True, is_deleted=False).first()
    else:
        company = user.company or get_staff_site_companies(user).first()

    if not company:
        return JsonResponse({
            'success': False,
            'error': 'Your account has no company assigned. Ask a Super Admin to assign one.'
        })

    customer_name  = data.get('customer_name', 'Walk-in Customer') or 'Walk-in Customer'
    customer_email = data.get('customer_email', '')
    customer_phone = data.get('customer_phone', '')
    try:
        payment_type = int(data.get('payment_type', POSOrder.PAYMENT_CASH))
    except (TypeError, ValueError):
        payment_type = POSOrder.PAYMENT_CASH
    raw_ctype = str(data.get('customer_type', POSOrder.CUSTOMER_VISITOR)).strip()
    _valid_ctypes = {POSOrder.CUSTOMER_STAFF, POSOrder.CUSTOMER_VISITOR, POSOrder.CUSTOMER_ROOM_SERVICE}
    customer_type = raw_ctype if raw_ctype in _valid_ctypes else POSOrder.CUSTOMER_VISITOR
    cart_items     = data.get('items', [])

    if not cart_items:
        return JsonResponse({'success': False, 'error': 'Cart is empty'})
    allowed_payment_types = [value for value, _ in _company_pos_payment_choices(company)]
    if payment_type not in allowed_payment_types:
        return JsonResponse({'success': False, 'error': 'This payment mode is not enabled for this company.'}, status=400)

    total = Decimal('0')
    order_items_data = []
    from apps.menu.models import Product as MenuProduct
    from apps.menu.pricing import get_effective_price, is_pricing_mode_available
    for item in cart_items:
        try:
            src = item.get('src', 'pos')
            qty = max(1, int(item.get('qty', 1)))
            if src == 'menu':
                mp = MenuProduct.objects.get(pk=item['id'], company=company, is_deleted=False)
                if not mp.is_active or not mp.is_available_now():
                    return JsonResponse({'success': False, 'error': f'{mp.name} is not available right now.'}, status=400)
                if not is_pricing_mode_available(mp, customer_type, company=company):
                    return JsonResponse({'success': False, 'error': f'{mp.name} is not available for this customer type.'}, status=400)
                min_qty = _menu_order_min_qty(mp)
                max_qty = _menu_pos_max_qty(mp)
                if max_qty <= 0:
                    return JsonResponse({'success': False, 'error': f'{mp.name} is out of stock or has insufficient quantity available.'}, status=400)
                if qty < min_qty or qty > max_qty:
                    return JsonResponse({'success': False, 'error': f'{mp.name} quantity must be between {min_qty} and {max_qty}.'}, status=400)
                price = get_effective_price(mp, company, pricing_mode=customer_type)
                amount = price * qty
                total += amount
                order_items_data.append({
                    'product_name': mp.name, 'menu_product': mp,
                    'qty': qty, 'price': price, 'amount': amount,
                })
                continue

        except (KeyError, ValueError, MenuProduct.DoesNotExist):
            return JsonResponse({'success': False, 'error': f"Product {item.get('id')} not found"}, status=400)

    try:
        with transaction.atomic():
            card_fee = _pos_card_fee(company, total) if payment_type == POSOrder.PAYMENT_CARD else Decimal('0.00')
            total_collected = total + card_fee
            order = POSOrder.objects.create(
                company=company,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                customer_type=customer_type,
                base_amount=total,
                card_fee_amount=card_fee,
                total_amount=total_collected,
                payment_type=payment_type,
            )

            for d in order_items_data:
                pname = d.get('product_name') or (d['product'].name if 'product' in d else 'Item')
                POSOrderItem.objects.create(
                    company=company, order=order,
                    product_name=pname,
                    price=d['price'], qty=d['qty'], amount=d['amount'],
                    created_at=timezone.now(),
                )
                mp = d.get('menu_product')
                if not mp:
                    try:
                        mp = MenuProduct.objects.get(company=company, name=pname, is_deleted=False)
                    except MenuProduct.DoesNotExist:
                        mp = None
                if mp and not _deduct_stock(mp, d['qty'], 'pos', order.pk, company, f'POS {order.order_number}'):
                    raise ValueError(f'{mp.name} is out of stock or has insufficient quantity available.')
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    return JsonResponse({
        'success':      True,
        'order_number': order.order_number,
        'total':        str(order.total_amount),
        'base_total':   str(order.base_amount),
        'card_fee':     str(order.card_fee_amount),
        'order_id':     order.pk,
    })

@staff_role_required('superadmin','admin','pos','cafeman')
def pos_receipt(request, pk):
    user = request.user
    # Scope: non-superadmin can only view their own company's POS orders
    qs = POSOrder.objects.filter(pk=pk)
    if not user.is_superadmin and user.company:
        qs = qs.filter(company=user.company)
    order = get_object_or_404(qs)
    return render(request, 'pos/receipt.html', {
        'order':   order,
        'items':   order.items.all(),
        'company': order.company,
        'page_title': f'Receipt — {order.order_number}',
    })


@staff_role_required('superadmin','admin','pos')
def pos_order_list(request):
    user    = request.user
    company = user.company

    # Superadmin has no company — show all
    today       = str(timezone.localdate())
    date_filter = request.GET.get('date', today)

    qs = POSOrder.objects.filter(is_deleted=False).exclude(
        created_at__isnull=True
    ).filter(created_at__date=date_filter).prefetch_related('items').order_by('-created_at')

    if company:
        qs = qs.filter(company=company)

    total_revenue = qs.aggregate(t=Sum('total_amount'))['t'] or 0

    # Company filter for superadmin
    company_filter = request.GET.get('company', '')
    if not company and company_filter:
        qs = qs.filter(company_id=company_filter)

    from apps.core.models import Company as CompanyModel
    from apps.accounts.models import StaffUser
    companies = []
    if user.is_superadmin:
        companies = CompanyModel.objects.filter(is_active=True, is_deleted=False).order_by('name')
        # Recompute revenue after company filter
        if company_filter:
            qs = POSOrder.objects.filter(
                is_deleted=False, company_id=company_filter
            ).exclude(created_at__isnull=True).filter(
                created_at__date=date_filter
            ).prefetch_related('items').order_by('-created_at')
            total_revenue = qs.aggregate(t=Sum('total_amount'))['t'] or 0

    return render(request, 'pos/order_list.html', {
        'orders':         qs,
        'total_revenue':  total_revenue,
        'date_filter':    date_filter,
        'company':        company,
        'company_filter': company_filter,
        'companies':      companies,
        'page_title':     'POS Orders',
    })




# ─────────────────────────────────────────────────────────────
#  POS KOT DATA  — for direct iframe print from POS order list
# ─────────────────────────────────────────────────────────────

@staff_role_required('superadmin','admin','pos','cafeman')
def pos_kot_data(request, pk):
    """Returns POS order data as JSON for direct iframe printing."""
    user = request.user
    qs   = POSOrder.objects.filter(pk=pk)
    if not user.is_superadmin and user.company:
        qs = qs.filter(company=user.company)
    try:
        order = qs.get()
    except POSOrder.DoesNotExist:
        return JsonResponse({'error': f'POS order #{pk} not found.'}, status=404)

    items = []
    for item in order.items.all():
        items.append({
            'name':  item.product_name,
            'qty':   item.qty,
            'price': str(item.price),
            'amount': str(item.amount),
        })

    pt_map = {1: 'Cash', 2: 'Card', 3: 'UPI'}
    return JsonResponse({
        'order_number':  order.order_number,
        'customer_name': order.customer_name,
        'customer_phone':order.customer_phone,
        'receipt_brand': 'NEVERNO',
        'company_name':  order.company.name,
        'company_phone': getattr(order.company, 'phone', '') or '',
        'company_gst':   getattr(order.company, 'company_gst', '') or '',
        'company_fssai': getattr(order.company, 'fssai_number', '') or '',
        'items':         items,
        'total':         str(order.total_amount),
        'base_total':    str(getattr(order, 'base_amount', None) or order.total_amount),
        'card_fee':      str(getattr(order, 'card_fee_amount', 0) or 0),
        'payment_mode':  pt_map.get(order.payment_type, 'Cash'),
        'created_at':    order.created_at.strftime('%d-%m-%Y %H:%M') if order.created_at else '',
        'scheduled_date':'',
    })


# Legacy POS-only product handlers are still referenced by the live VPS URL config.
@staff_role_required('superadmin','admin','pos')
def pos_products(request):
    user = request.user
    company = user.company
    if not company:
        messages.error(request, 'No company assigned to your account. Ask a Super Admin.')
        return redirect('dashboard:home')

    products = POSProduct.objects.filter(company=company, is_deleted=False).order_by('name')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delete':
            ids = request.POST.getlist('ids')
            POSProduct.objects.filter(pk__in=ids, company=company).update(is_deleted=True)
            messages.success(request, f'{len(ids)} product(s) deleted.')
        elif action == 'add':
            name = (request.POST.get('name') or '').strip()
            price = request.POST.get('price') or '0'
            if name:
                POSProduct.objects.create(
                    company=company,
                    name=name,
                    price=price,
                    is_active=request.POST.get('is_active') == 'on',
                )
                messages.success(request, 'POS product added.')
        return redirect('pos:products')

    return render(request, 'pos/products.html', {
        'products': products,
        'company': company,
        'page_title': 'POS Products',
    })


@require_POST
@staff_role_required('superadmin','admin','pos')
def pos_product_toggle(request, pk):
    user = request.user
    qs = POSProduct.objects.filter(pk=pk)
    if user.company:
        qs = qs.filter(company=user.company)
    product = get_object_or_404(qs, is_deleted=False)
    product.is_active = not product.is_active
    product.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'is_active': product.is_active})


@require_POST
@staff_role_required('superadmin','admin','pos')
def pos_product_edit(request, pk):
    user = request.user
    qs = POSProduct.objects.filter(pk=pk)
    if user.company:
        qs = qs.filter(company=user.company)
    product = get_object_or_404(qs, is_deleted=False)

    name = (request.POST.get('name') or '').strip()
    price = request.POST.get('price')
    if name:
        product.name = name
    if price not in (None, ''):
        product.price = price
    product.is_active = request.POST.get('is_active') == 'on'
    product.save(update_fields=['name', 'price', 'is_active'])
    return JsonResponse({'success': True})
