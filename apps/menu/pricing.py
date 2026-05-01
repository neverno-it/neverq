from decimal import Decimal, InvalidOperation


PRICING_MODE_STAFF = 'staff'
PRICING_MODE_VISITOR = 'visitor'
PRICING_MODE_ROOM_SERVICE = 'room_service'

PRICE_MODE_CHOICES = {
    PRICING_MODE_STAFF,
    PRICING_MODE_VISITOR,
    PRICING_MODE_ROOM_SERVICE,
}


def _decimal(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


def _money(value):
    return _decimal(value).quantize(Decimal('0.01'))


def _positive(value):
    return max(Decimal('0.00'), _decimal(value))


def normalize_pricing_mode(value, default=PRICING_MODE_STAFF):
    raw = str(value or '').strip().lower().replace('-', '_')
    aliases = {
        'employee': PRICING_MODE_STAFF,
        'registered': PRICING_MODE_STAFF,
        'customer': PRICING_MODE_STAFF,
        'public': PRICING_MODE_VISITOR,
        'guest': PRICING_MODE_VISITOR,
        'room': PRICING_MODE_ROOM_SERVICE,
        'roomservice': PRICING_MODE_ROOM_SERVICE,
        'room_service': PRICING_MODE_ROOM_SERVICE,
    }
    mode = aliases.get(raw, raw)
    return mode if mode in PRICE_MODE_CHOICES else default


def get_staff_price(product, company=None, building=None, cafe=None):
    """Staff/base price: site override first, then Product.price."""
    from apps.menu.models import ProductCompanyPrice

    if company and cafe:
        override = ProductCompanyPrice.objects.filter(
            product=product,
            cafe=cafe,
            company=company,
            is_active=True,
        ).first()
        if override:
            return _money(override.price)
        if getattr(cafe, 'building_id', None) and building is None:
            building = cafe.building

    if company and building:
        override = ProductCompanyPrice.objects.filter(
            product=product,
            building=building,
            company=company,
            cafe__isnull=True,
            is_active=True,
        ).first()
        if override:
            return _money(override.price)

    if company:
        override = ProductCompanyPrice.objects.filter(
            product=product,
            company=company,
            building__isnull=True,
            cafe__isnull=True,
            is_active=True,
        ).first()
        if override:
            return _money(override.price)

    return _money(product.price)


def get_visitor_price(product, company=None, building=None, cafe=None, staff_price=None):
    """Visitor price: Product.company_price when set, otherwise staff/base price."""
    base = _positive(
        staff_price if staff_price is not None
        else get_staff_price(product, company=company, building=building, cafe=cafe)
    )
    visitor = _positive(getattr(product, 'company_price', 0))
    return _money(visitor if visitor > Decimal('0.00') else base)


def get_room_service_price(product, visitor_price):
    """Room service price: visitor price plus item-wise percentage extra."""
    visitor = _positive(visitor_price)
    pct = _positive(getattr(product, 'room_service_extra_percent', 0))
    if pct <= Decimal('0.00'):
        return _money(visitor)
    return _money(visitor + (visitor * pct / Decimal('100')))


def is_pricing_mode_available(product, pricing_mode, company=None, building=None, cafe=None):
    """
    Whether the POS should expose a customer price mode for this product.

    Existing price calculation still keeps its historical fallbacks, but POS
    visibility should reflect what was explicitly configured on the product.
    """
    mode = normalize_pricing_mode(pricing_mode)
    if mode == PRICING_MODE_STAFF:
        return get_staff_price(product, company=company, building=building, cafe=cafe) > Decimal('0.00')
    if mode == PRICING_MODE_VISITOR:
        return _positive(getattr(product, 'company_price', 0)) > Decimal('0.00')
    if mode == PRICING_MODE_ROOM_SERVICE:
        has_base_price = (
            _positive(getattr(product, 'company_price', 0)) > Decimal('0.00')
            or get_staff_price(product, company=company, building=building, cafe=cafe) > Decimal('0.00')
        )
        return has_base_price and _positive(getattr(product, 'room_service_extra_percent', 0)) > Decimal('0.00')
    return False


def get_available_pricing_modes(product, company=None, building=None, cafe=None):
    return [
        mode for mode in (
            PRICING_MODE_STAFF,
            PRICING_MODE_VISITOR,
            PRICING_MODE_ROOM_SERVICE,
        )
        if is_pricing_mode_available(product, mode, company=company, building=building, cafe=cafe)
    ]


def get_effective_price(product, company, building=None, cafe=None, pricing_mode=PRICING_MODE_STAFF):
    staff = get_staff_price(product, company=company, building=building, cafe=cafe)
    mode = normalize_pricing_mode(pricing_mode)
    if mode == PRICING_MODE_STAFF:
        return staff
    visitor = get_visitor_price(
        product,
        company=company,
        building=building,
        cafe=cafe,
        staff_price=staff,
    )
    if mode == PRICING_MODE_VISITOR:
        return visitor
    if mode == PRICING_MODE_ROOM_SERVICE:
        return get_room_service_price(product, visitor)
    return staff
