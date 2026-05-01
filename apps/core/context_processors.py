from django.conf import settings

def site_context(request):
    cfg = getattr(settings, 'NEVERQ', {})
    ctx = {
        'APP_NAME': cfg.get('APP_NAME', 'NeverQ'),
        'APP_TAGLINE': cfg.get('TAGLINE', 'Corporate Cafeteria Management'),
        'APP_VERSION': cfg.get('VERSION', '1.0.0'),
    }

    user = request.user
    if hasattr(user, 'role') and user.is_authenticated:
        ctx['role'] = user.role

        # Build visible_menus from per-user → role → defaults
        try:
            from apps.core.access import get_allowed_keys
            ctx['visible_menus'] = get_allowed_keys(user)
        except Exception:
            ctx['visible_menus'] = set()

        try:
            from apps.core.models import Notification
            ctx['unread_notifs'] = Notification.objects.filter(
                staff_user=user, is_read=False).count()
        except Exception:
            ctx['unread_notifs'] = 0

        # Pending customer approvals badge
        try:
            from apps.accounts.models import Customer
            company_filter = {} if user.role == 'superadmin' else {'company': user.company}
            ctx['pending_approvals'] = Customer.objects.filter(
                is_approved=False, is_active=True, is_deleted=False, **company_filter
            ).count()
        except Exception:
            ctx['pending_approvals'] = 0

    cid = request.session.get('customer_id')
    if cid:
        try:
            from apps.accounts.models import Customer
            customer = Customer.objects.select_related('company', 'building').get(
                pk=cid, is_active=True, is_deleted=False)
            # FIX: was 'current_customer' — customer_base.html uses 'customer'
            ctx['customer'] = customer
            ctx['current_customer'] = customer   # keep alias for any other references
            ctx['current_company'] = customer.company
            try:
                from apps.core.models import resolve_web_view_config
                ctx['web_cfg'] = resolve_web_view_config(
                    customer.company,
                    building=getattr(customer, 'building', None),
                    slug=request.GET.get('web', ''),
                )
            except Exception:
                ctx['web_cfg'] = None
            cart = request.session.get('cart', {})
            ctx['cart_count'] = sum(v.get('qty', 0) for v in cart.values())
        except Exception:
            pass

    return ctx
