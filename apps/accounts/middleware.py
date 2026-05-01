from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

from .models import StaffUser
from .dashboard_menu import get_allowed_menu_keys, get_view_to_menu_map


class DashboardMenuAccessMiddleware:
    """
    DEPRECATED — not registered in settings.py MIDDLEWARE.
    The active implementation is apps.core.middleware.MenuAccessMiddleware.
    This class is kept to avoid import errors in case anything references it,
    but it is not in the middleware chain and has no effect.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.view_to_menu = get_view_to_menu_map()

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return None
        if not isinstance(user, StaffUser) or not getattr(user, 'is_active', False):
            return None
        if user.role == StaffUser.ROLE_SUPERADMIN:
            return None

        resolver = getattr(request, 'resolver_match', None)
        view_name = getattr(resolver, 'view_name', '') if resolver else ''
        menu_key = self.view_to_menu.get(view_name)
        if not menu_key:
            return None

        allowed = set(get_allowed_menu_keys(user))
        if menu_key in allowed:
            return None

        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.content_type == 'application/json'
            or request.headers.get('Accept', '').startswith('application/json')
        )
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'This page is disabled for your account.'}, status=403)

        messages.error(request, 'This page is disabled for your account.')
        if user.role == StaffUser.ROLE_POS:
            return redirect('dashboard:cashier')
        if user.role == StaffUser.ROLE_CAFEMAN:
            return redirect('dashboard:kitchen')
        return redirect('dashboard:home')
