from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from .models import Customer, StaffUser


def enforce_customer_active_state(customer):
    if not customer or getattr(customer, 'is_deleted', False):
        return False
    if hasattr(customer, 'deactivate_if_stale'):
        customer.deactivate_if_stale()
    return bool(getattr(customer, 'is_active', False))


def customer_login_required(view_func):
    """Checks for customer session — not Django auth."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        customer_id = request.session.get('customer_id')
        if not customer_id:
            messages.warning(request, 'Please log in to order.')
            return redirect('accounts:customer_login')
        try:
            customer = Customer.objects.get(pk=customer_id, is_deleted=False)
            if not enforce_customer_active_state(customer):
                request.session.flush()
                messages.warning(request, 'Your customer account is inactive. Please contact the admin team.')
                return redirect('accounts:customer_login')
            request.current_customer = customer
        except Customer.DoesNotExist:
            request.session.flush()
            return redirect('accounts:customer_login')
        # Block ordering if customer is not yet approved
        if not getattr(customer, 'is_approved', True):
            messages.warning(request, 'Your account is pending admin approval. You will be able to order once approved.')
            # Only block actual ordering pages, not profile/history viewing
            ordering_paths = ['/menu/', '/orders/checkout/', '/orders/place/']
            if any(request.path.startswith(p) for p in ordering_paths):
                return redirect('orders:order_history')
        return view_func(request, *args, **kwargs)
    return wrapper


def staff_role_required(*roles):
    """
    Role guard — superadmin always passes.
    All other roles must be in the `roles` list.
    Also enforces that non-superadmin users have a company assigned.

    IMPORTANT: Does NOT use @login_required internally because that decorator
    blindly issues an HTML 302 redirect even for AJAX/fetch requests, causing
    the browser to follow the redirect and return an HTML login page.
    fetch() callers then get "Unexpected token < ... is not valid JSON" because
    resp.json() fails on the HTML body. Instead we detect unauthenticated AJAX
    calls here and return a JSON 401 so the frontend can show a clear message.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            is_ajax = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                or request.content_type == 'application/json'
                or request.headers.get('Accept', '').startswith('application/json')
            )

            # ── Step 1: authentication ────────────────────────────────
            # Must come before any user.role checks (AnonymousUser has no role).
            if not request.user.is_authenticated:
                if is_ajax:
                    return JsonResponse(
                        {'success': False,
                         'error': 'Session expired. Please refresh the page and log in again.'},
                        status=401
                    )
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())

            if not isinstance(user, StaffUser) or not user.is_active:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'Authentication required.'}, status=403)
                messages.error(request, 'Please sign in with a staff account.')
                return redirect('accounts:login')
            # Superadmin bypasses all role checks
            if user.role == StaffUser.ROLE_SUPERADMIN:
                return view_func(request, *args, **kwargs)

            menu_key = None
            allowed_keys = None
            try:
                from apps.core.access import get_allowed_keys, get_route_to_key_map
                match = request.resolver_match
                full_name = (
                    f'{match.namespace}:{match.url_name}'
                    if match and match.namespace
                    else getattr(match, 'url_name', '')
                )
                menu_key = get_route_to_key_map().get(full_name)
                if menu_key:
                    allowed_keys = get_allowed_keys(user)
                    if menu_key not in allowed_keys:
                        if is_ajax:
                            return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
                        messages.error(request, 'You do not have access to this section.')
                        return redirect('dashboard:no_access')
            except Exception:
                menu_key = None
                allowed_keys = None
            # Role check — bypass if user has granular permission rows configured
            # Only routes explicitly granted by the matrix can bypass roles.
            if roles and user.role not in roles:
                if menu_key and allowed_keys is not None and menu_key in allowed_keys:
                    return view_func(request, *args, **kwargs)
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('dashboard:no_access')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def staff_login_required(view_func):
    return staff_role_required()(view_func)


def _role_home(user):
    """Redirect to the correct home for a role."""
    if user.role == StaffUser.ROLE_POS:
        return redirect('dashboard:cashier')
    if user.role == StaffUser.ROLE_CAFEMAN:
        return redirect('dashboard:kitchen')
    return redirect('dashboard:home')


def company_required(view_func):
    """
    Ensures a non-superadmin user has a company assigned.
    If not, redirects to home with an error.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if isinstance(user, StaffUser) and not user.is_superadmin and not user.company:
            messages.error(request, 'Your account has no company assigned. Contact Super Admin.')
            return redirect('accounts:login')
        return view_func(request, *args, **kwargs)
    return wrapper
