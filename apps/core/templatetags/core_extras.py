import re
from django import template
from django.urls import reverse, NoReverseMatch

register = template.Library()


@register.filter
def get_item(value, key):
    """Get item from dict: {{ mydict|get_item:key }}"""
    try:
        return value.get(key, [])
    except Exception:  # template filter — never raise, always return safe default
        return []


@register.simple_tag
def menu_url(url_name):
    """Safely resolve a URL name string. Returns '#' on failure."""
    try:
        return reverse(url_name)
    except (NoReverseMatch, Exception):
        return '#'


@register.simple_tag(takes_context=True)
def menu_active(context, active_match):
    """Return 'active' if current URL name contains match string."""
    try:
        request = context['request']
        current = request.resolver_match.url_name or ''
        if active_match and active_match in current:
            return 'active'
    except Exception:
        pass
    return ''


@register.simple_tag(takes_context=True)
def section_has_items(context, *keys):
    """Return True if ANY of the given keys are in visible_menus."""
    try:
        vis = context.get('visible_menus', set())
        if not vis:
            return True  # no restrictions = show all
        return any(k in vis for k in keys)
    except Exception:
        return True

@register.filter
def short_order_no(value):
    """Display-only order number shortening."""
    try:
        value = str(value or '').strip()
        match = re.match(r'^([A-Za-z]+)-(\d{6}|\d{8})-(.+)$', value)
        return f"{match.group(1)}-{match.group(3)}" if match else value
    except Exception:
        return value



# ── Granular Permission Template Tags ─────────────────────────────────────────

@register.simple_tag
def module_level(user, module_key):
    """Return access level for user+module: 'full_edit'|'part_edit'|'view'|None"""
    try:
        from apps.core.access import get_module_level
        return get_module_level(user, module_key)
    except Exception:
        return None


@register.simple_tag
def can_action(user, module_key, action_key):
    """Return True if user can perform the given action in the module."""
    try:
        from apps.core.access import user_can_action
        return user_can_action(user, module_key, action_key)
    except Exception:
        return False


@register.simple_tag
def pending_changes_count():
    """Return count of pending changes awaiting superadmin review."""
    try:
        from apps.core.access import get_pending_count
        return get_pending_count()
    except Exception:
        return 0
