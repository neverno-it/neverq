"""
MenuAccessMiddleware — server-side enforcement via process_view.

Does NOT gate on path prefix. Instead checks whether the resolved
route name exists in the access registry. If yes → enforce. If no → pass.
This correctly protects orders:kot_data (staff) without blocking
orders:checkout (customer), because only staff routes are in the registry.
"""
from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib import messages


class MenuAccessMiddleware:
    EXEMPT_EXACT = {'/', '/dashboard/store-toggle/', '/dashboard/no-access/'}

    def __init__(self, get_response):
        self.get_response = get_response
        self._route_map = None

    def _get_route_map(self):
        if self._route_map is None:
            try:
                from apps.core.access import get_route_to_key_map
                self._route_map = get_route_to_key_map()
            except Exception:  # middleware init must never raise
                self._route_map = {}
        return self._route_map

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user

        # Skip: anonymous, non-staff, superadmin, exempt paths
        if not hasattr(user, 'role') or not user.is_authenticated:
            return None
        if user.role == 'superadmin':
            return None
        if request.path in self.EXEMPT_EXACT:
            return None

        # Resolve the fully-qualified route name
        match = request.resolver_match
        if not match or not match.url_name:
            return None
        full_name = f'{match.namespace}:{match.url_name}' if match.namespace else match.url_name

        # The route map IS the gate — if this route isn't in it, it's
        # not a protected staff page (e.g. orders:checkout) → pass through.
        route_map = self._get_route_map()
        menu_key = route_map.get(full_name)
        if not menu_key:
            return None

        # Route is protected — check if user has the key
        try:
            from apps.core.access import get_allowed_keys
            allowed = get_allowed_keys(user)
        except Exception:
            return None

        if menu_key in allowed:
            return None

        # BLOCKED
        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.content_type == 'application/json'
            or request.headers.get('Accept', '').startswith('application/json')
        )
        if is_ajax:
            return JsonResponse(
                {'success': False, 'error': 'You do not have access to this page.'},
                status=403
            )
        messages.error(request, 'You do not have access to this page.')
        return redirect('dashboard:no_access')
