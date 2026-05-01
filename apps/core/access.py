"""
NeverQ menu/page access registry — single source of truth.
Every sidebar link and every protected route is listed here ONCE.
"""

SA  = 'superadmin'
ADM = 'admin'
POS = 'pos'
CHF = 'cafeman'
RPT = 'reports'

ALL_STAFF = [SA, ADM, POS, CHF, RPT]

LANDING_CHOICES = [
    ('dashboard:home',    'Admin Dashboard',          [SA, ADM, RPT]),
    ('dashboard:cashier', 'Cashier / Today Orders',   [SA, ADM, POS]),
    ('dashboard:kitchen', 'Kitchen Orders',           [SA, ADM, CHF]),
    ('dashboard:reports', 'Reports',                  [SA, ADM, POS, RPT]),
]

# key → (label, section, [route_names], [default_roles])
MENU_REGISTRY = {
    # Overview
    'dashboard':     ('Dashboard',         'Overview',        ['dashboard:home'],       [SA, ADM, RPT]),
    'cashier_dash':  ('Cashier Dashboard', 'Overview',        ['dashboard:cashier'],    [SA, ADM, POS]),
    'kitchen':       ('Kitchen Orders',    'Overview',        ['dashboard:kitchen'],    [SA, ADM, CHF]),
    # Operations
    'orders':        ('Orders',            'Operations', [
        'dashboard:order_list', 'dashboard:order_detail', 'dashboard:order_update_status',
        'orders:kot_data', 'orders:new_orders_poll',
        'dashboard:store_toggle',
        'dashboard:delivery_confirmation_list', 'dashboard:delivery_mark_delivered',
        'dashboard:delivery_packet_labels',
        'orders:delivery_confirmation_list', 'orders:delivery_mark_delivered',
        'orders:delivery_packet_labels',
    ], [SA, ADM, POS, CHF]),
    'pos_terminal':  ('POS Terminal',      'Operations', [
        'pos:terminal', 'pos:place_order',
        'pos:products', 'pos:product_toggle', 'pos:product_edit',
        'pos:terminal_kot_data',
    ], [SA, ADM, POS]),
    'display_board': ('Display Board',     'Operations', [
        'dashboard:display_board_select',
        'orders:display_board', 'orders:display_board_company',
    ], [SA, ADM, POS, CHF]),
    'pos_orders':    ('POS Orders',        'Operations', [
        'pos:order_list', 'pos:receipt', 'pos:kot_data',
    ], [SA, ADM, POS]),
    'flash_order':   ('Flash Order',       'Operations', [
        'dashboard:flash_order', 'dashboard:customer_search',
    ], [SA, ADM, POS]),
    # Menu Catalog
    'products':      ('Products',          'Menu Catalog', [
        'dashboard:product_list', 'dashboard:product_edit',
        'dashboard:product_toggle', 'dashboard:product_delete',
        'dashboard:product_bulk_delete',
        'dashboard:product_copy', 'dashboard:product_update_qty',
        'dashboard:product_cashier_edit',
        'dashboard:product_reorder',
        'dashboard:product_excel_download',
        'dashboard:product_bypass_toggle', 'dashboard:product_featured_toggle',
        'dashboard:product_kiosk_toggle', 'dashboard:product_web_featured_toggle',
        'dashboard:product_pos_toggle',
    ], [SA, ADM, POS]),
    'offerings':     ('Offerings',         'Menu Catalog', [
        'dashboard:offering_list', 'dashboard:offering_reorder',
    ], [SA, ADM]),
    'manage_offerings': ('Manage Offerings', 'Menu Catalog', [
        'dashboard:offering_add', 'dashboard:offering_edit',
        'dashboard:offering_toggle', 'dashboard:offering_delete',
        'dashboard:offering_bulk_delete',
        'dashboard:offering_gallery', 'dashboard:offering_gallery_api',
        'dashboard:offering_gallery_delete', 'dashboard:offering_gallery_bulk_delete',
        'dashboard:offering_gallery_rename',
    ], [SA, ADM]),
    'counters':      ('Counters',          'Menu Catalog', [
        'dashboard:counter_list', 'dashboard:counter_reorder',
    ], [SA, ADM]),
    'manage_counters': ('Manage Counters', 'Menu Catalog', [
        'dashboard:counter_add', 'dashboard:counter_edit',
        'dashboard:counter_toggle', 'dashboard:counter_delete',
        'dashboard:counter_bulk_delete',
    ], [SA, ADM]),
    'offers':        ('Offers',            'Pricing & Promotions', [
        'dashboard:offer_list',
    ], [SA, ADM]),
    'manage_offers': ('Manage Offers',     'Pricing & Promotions', [
        'dashboard:offer_add', 'dashboard:offer_edit',
        'dashboard:offer_toggle', 'dashboard:offer_delete',
        'dashboard:offer_bulk_delete', 'dashboard:offer_cafe_options',
        'dashboard:offer_reset_usage',
    ], [SA, ADM]),
    'add_product':   ('Add Product',       'Menu Catalog', [
        'dashboard:product_add',
        'dashboard:product_bulk_copy',
        'dashboard:product_gallery', 'dashboard:product_gallery_api',
        'dashboard:product_gallery_delete', 'dashboard:product_gallery_bulk_delete',
        'dashboard:product_gallery_rename',
    ], [SA, ADM]),
    'bulk_upload':   ('Bulk Upload',       'Menu Catalog', [
        'dashboard:product_bulk_upload',
        'dashboard:product_bulk_sample_download',
        'dashboard:product_bulk_image_upload',
    ], [SA, ADM]),
    'categories':    ('Categories',        'Menu Catalog', [
        'dashboard:category_list', 'dashboard:category_toggle',
        'dashboard:category_edit', 'dashboard:category_delete',
        'dashboard:category_bulk_delete', 'dashboard:category_reorder',
        'dashboard:category_gallery', 'dashboard:category_gallery_api',
        'dashboard:category_gallery_delete', 'dashboard:category_gallery_bulk_delete',
        'dashboard:category_gallery_rename',
    ], [SA, ADM, POS]),
    'add_category':  ('Add Category',      'Menu Catalog', [
        'dashboard:category_add',
        'dashboard:category_bulk_copy',
    ], [SA, ADM]),
    'banners':       ('Banners',           'Media & Scheduling', [
        'dashboard:advertise_list', 'dashboard:advertise_add',
        'dashboard:advertise_edit', 'dashboard:advertise_delete',
        'dashboard:advertise_approve', 'dashboard:advertise_reorder',
        'dashboard:advertise_bulk_delete',
    ], [SA, ADM]),
    'media_library': ('Media Library',     'Media & Scheduling', [
        'dashboard:media_library', 'dashboard:media_library_rename',
        'dashboard:media_library_delete', 'dashboard:media_library_bulk_delete',
    ], [SA, ADM]),
    'holidays':      ('Holiday Schedules', 'Media & Scheduling', [
        'dashboard:holiday_list', 'dashboard:holiday_edit',
    ], [SA]),
    'pickup_scan':   ('Counter Pickup Scan', 'Operations', [
        'orders:pickup_scan_terminal', 'orders:pickup_mark_collected',
    ], [SA, ADM, POS, CHF]),
    'counter_tickets': ('Counter Ticket Board', 'Operations', [
        'dashboard:counter_ticket_board', 'dashboard:counter_ticket_update',
        'dashboard:counter_ticket_kot',
    ], [SA, ADM, POS, CHF]),
    'stock_mgmt':    ('Stock Management',    'Menu Catalog', [
        'dashboard:stock_management',
    ], [SA, ADM]),
    # Customers
    'customers':     ('Customers',         'Customers', [
        'dashboard:customer_list', 'dashboard:customer_edit',
        'dashboard:customer_toggle_subsidy', 'dashboard:customer_set_meal_benefit',
        'dashboard:customer_approve', 'dashboard:customer_wallet',
        'dashboard:customer_delete', 'dashboard:customer_bulk_delete',
    ], [SA, ADM]),
    'add_customer':  ('Add Customer',      'Customers', [
        'dashboard:customer_add',
    ], [SA, ADM]),
    'wallet_recharge': ('Recharge Wallet', 'Customers', [
        'dashboard:wallet_recharge',
    ], [SA, ADM, POS]),
    'reviews':       ('Reviews',           'Customers', [
        'dashboard:reviews_list',
    ], [SA, ADM, RPT]),
    'broadcast_notifications': ('Broadcast Notifications', 'Customers', [
        'dashboard:broadcast_notification_list',
        'dashboard:broadcast_notification_send',
        'dashboard:broadcast_notification_delete',
        'dashboard:broadcast_notification_bulk_delete',
    ], [SA, ADM]),
    # Reports
    'reports':       ('Reports',           'Reports', [
        'dashboard:reports',
    ], [SA, ADM, POS, RPT]),
    'royalty_leaderboard': ('Royalty Leaderboard', 'Reports', [
        'dashboard:royalty_leaderboard',
    ], [SA, ADM]),
    'coupons':       ('Coupons',           'Pricing & Promotions', [
        'dashboard:coupon_list', 'dashboard:coupon_add',
        'dashboard:coupon_edit', 'dashboard:coupon_delete',
        'dashboard:coupon_bulk_delete',
    ], [SA, ADM]),
    # Administration
    'companies':     ('Companies',         'Administration', [
        'dashboard:company_list', 'dashboard:company_detail',
        'dashboard:company_edit', 'dashboard:company_store_toggle',
        'dashboard:kiosk_config_list', 'dashboard:kiosk_config_add',
        'dashboard:kiosk_config_edit', 'dashboard:kiosk_config_delete',
        'dashboard:kiosk_config_bulk_delete',
        'dashboard:web_config_list', 'dashboard:web_config_add',
        'dashboard:web_config_edit', 'dashboard:web_config_delete',
        'dashboard:web_config_bulk_delete',
        'dashboard:display_config_list', 'dashboard:display_config_add',
        'dashboard:display_config_edit', 'dashboard:display_config_delete',
        'dashboard:display_config_bulk_delete',
        'dashboard:hierarchy',
    ], [SA]),
    'add_company':   ('Add Company',       'Administration', [
        'dashboard:company_add',
    ], [SA]),
    'add_building':  ('Add Building',      'Administration', [
        'dashboard:building_add', 'dashboard:building_edit',
        'dashboard:building_delete', 'dashboard:building_bulk_delete', 'dashboard:building_list',
        'dashboard:building_toggle',
        'dashboard:cafe_add', 'dashboard:cafe_edit',
        'dashboard:cafe_delete', 'dashboard:cafe_bulk_delete', 'dashboard:cafe_list', 'dashboard:cafe_toggle',
        'dashboard:city_add', 'dashboard:city_edit', 'dashboard:city_delete',
        'dashboard:city_bulk_delete', 'dashboard:city_list', 'dashboard:city_toggle',
        'dashboard:state_add', 'dashboard:state_edit', 'dashboard:state_delete',
        'dashboard:state_bulk_delete',
        'dashboard:state_list',
        'dashboard:location_add', 'dashboard:location_edit',
        'dashboard:location_delete', 'dashboard:location_bulk_delete', 'dashboard:location_list',
    ], [SA]),
    'staff':         ('Staff Users',       'Administration', [
        'dashboard:staff_list',
    ], [SA]),
    'static_pages':  ('Static Pages',      'Administration', [
        'dashboard:static_page_list', 'dashboard:static_page_edit',
    ], [SA]),
}

SECTION_ORDER = ['Overview', 'Operations', 'Menu Catalog', 'Pricing & Promotions', 'Media & Scheduling', 'Customers', 'Reports', 'Administration']


def get_default_keys(role):
    """Return set of menu keys a role sees by default."""
    return {k for k, (_, _, _, roles) in MENU_REGISTRY.items() if role in roles}


def get_route_to_key_map():
    """Return dict: route_name → menu_key."""
    m = {}
    for key, (_, _, routes, _) in MENU_REGISTRY.items():
        for r in routes:
            m[r] = key
    return m

GRANULAR_MENU_KEY_MAP = {
    'perm_dashboard': {'dashboard'},
    'perm_cashier_dash': {'cashier_dash'},
    'perm_kitchen': {'kitchen'},

    'perm_orders': {'orders'},
    'perm_pos_terminal': {'pos_terminal'},
    'perm_display_board': {'display_board'},
    'perm_pos_orders': {'pos_orders'},
    'perm_flash_order': {'flash_order'},
    'perm_pickup_scan': {'pickup_scan'},
    'perm_counter_tickets': {'counter_tickets'},
    'perm_wallet_recharge': {'wallet_recharge'},

    'perm_products': {'products'},
    'perm_categories': {'categories'},
    'perm_offerings': {'offerings', 'manage_offerings'},
    'perm_counters': {'counters', 'manage_counters'},
    'perm_offers': {'offers', 'manage_offers'},

    'perm_coupons': {'coupons'},
    'perm_banners': {'banners'},
    'perm_media_library': {'media_library'},
    'perm_stock': {'stock_mgmt'},

    'perm_customers': {'customers'},
    'perm_reviews': {'reviews'},
    'perm_broadcast_notifications': {'broadcast_notifications'},

    'perm_reports': {'reports'},
    'perm_royalty_lb': {'royalty_leaderboard'},

    'perm_geography': {'add_building'},
    'perm_staff': {'staff'},
    'perm_static_pages': {'static_pages'},
}


def get_granular_menu_keys(user):
    """Map StaffModulePermission rows to sidebar/menu keys."""
    try:
        from apps.accounts.models import StaffModulePermission
        perms = list(StaffModulePermission.objects.filter(staff_user=user))
    except Exception:
        return set()

    if not perms:
        return set()

    out = set()
    for perm in perms:
        mk = perm.module_key
        out.update(GRANULAR_MENU_KEY_MAP.get(mk, set()))
        actions = set(perm.allowed_actions or [])
        if mk == 'perm_products':
            if perm.level == 'full_edit' or actions.intersection({'add', 'copy', 'bulk_copy'}):
                out.add('add_product')
            if perm.level == 'full_edit' or 'bulk_upload' in actions:
                out.add('bulk_upload')
        if mk == 'perm_categories':
            if perm.level == 'full_edit' or 'add' in actions:
                out.add('add_category')
        if mk == 'perm_customers':
            if perm.level == 'full_edit' or 'add' in actions:
                out.add('add_customer')
    return out

def get_allowed_keys(user):
    """
    Return the set of menu keys this user can access.
    Non-superadmin staff are governed only by the granular permission matrix.
    Superadmin always gets everything.
    """
    if user.role == SA:
        return set(MENU_REGISTRY.keys())

    return get_granular_menu_keys(user)

def get_landing_url(user):
    """Return the URL name for this user's landing page."""
    if user.role == SA:
        return 'dashboard:home'
    defaults = {
        ADM: 'dashboard:home',
        POS: 'dashboard:cashier',
        CHF: 'dashboard:kitchen',
        RPT: 'dashboard:reports',
    }
    return defaults.get(user.role, 'dashboard:home')


def get_valid_landings(role):
    """Return landing choices that the role's decorator actually allows."""
    return [(url, label) for url, label, roles in LANDING_CHOICES if role in roles]


LANDING_KEY_PRIORITY = [
    ('dashboard:home', 'dashboard'),
    ('dashboard:cashier', 'cashier_dash'),
    ('dashboard:kitchen', 'kitchen'),
    ('dashboard:reports', 'reports'),
]


def get_safe_landing_url(user):
    """
    Return a landing URL name that is both role-valid and accessible to the user.
    Falls back to the first allowed landing, otherwise to dashboard:no_access.
    """
    if user.role == SA:
        return 'dashboard:home'

    allowed = get_allowed_keys(user)
    configured = get_landing_url(user)
    route_map = get_route_to_key_map()
    configured_key = route_map.get(configured)

    if configured and configured_key and configured_key in allowed:
        return configured

    for url_name, key in LANDING_KEY_PRIORITY:
        if key in allowed:
            for allowed_url, _label, roles in LANDING_CHOICES:
                if allowed_url == url_name and user.role in roles:
                    return url_name

    for key, (_label, _section, route_names, _roles) in MENU_REGISTRY.items():
        if key in allowed and route_names:
            return route_names[0]

    return 'dashboard:no_access'


def get_staff_site_company_ids(user):
    """Company IDs this staff member may control."""
    if getattr(user, 'role', None) == SA:
        return None
    ids = set()
    company_id = getattr(user, 'company_id', None)
    if company_id:
        ids.add(company_id)
    if getattr(user, 'pk', None):
        try:
            ids.update(user.site_access.values_list('pk', flat=True))
        except Exception:
            pass
    return sorted(ids)


def get_staff_site_companies(user):
    """Active, non-deleted companies this staff member may control."""
    from apps.core.models import Company
    qs = Company.objects.filter(is_active=True, is_deleted=False).order_by('name')
    ids = get_staff_site_company_ids(user)
    if ids is None:
        return qs
    if not ids:
        return Company.objects.none()
    return qs.filter(pk__in=ids)


def user_can_access_company(user, company_or_id):
    if getattr(user, 'role', None) == SA:
        return True
    company_id = getattr(company_or_id, 'pk', company_or_id)
    try:
        company_id = int(company_id)
    except (TypeError, ValueError):
        return False
    return company_id in set(get_staff_site_company_ids(user) or [])


def get_primary_staff_company(user):
    """Best single-company fallback for screens that still operate one site at a time."""
    if getattr(user, 'role', None) == SA:
        return None
    if getattr(user, 'company_id', None) and user_can_access_company(user, user.company_id):
        return user.company
    return get_staff_site_companies(user).first()


# ═══════════════════════════════════════════════════════════════════════════════
# GRANULAR PERMISSION ACTION REGISTRY
# Completely separate from MENU_REGISTRY.
# Controls WHAT a staff member can DO within a module.
# Structure: module_key → {label, section, actions:{action_key: label}}
# ═══════════════════════════════════════════════════════════════════════════════

PERM_SECTION_ORDER = [
    'Overview',
    'Operations',
    'Menu Catalog',
    'Pricing & Promotions',
    'Media & Scheduling',
    'Customers',
    'Reports & Reviews',
    'Administration',
]

ACTION_REGISTRY = {

    # ── Overview ─────────────────────────────────────────────────────────────
    'perm_dashboard':    {'label': 'Dashboard Home',      'section': 'Overview', 'actions': {}},
    'perm_cashier_dash': {'label': 'Cashier Dashboard',   'section': 'Overview', 'actions': {}},
    'perm_kitchen':      {'label': 'Kitchen Orders View', 'section': 'Overview', 'actions': {}},
    'perm_flash_order':  {'label': 'Flash Order',         'section': 'Overview', 'actions': {}},

    # ── Operations ────────────────────────────────────────────────────────────
    'perm_orders': {
        'label': 'Orders', 'section': 'Operations',
        'actions': {
            'status_update':    'Update Order Status',
            'delivery_confirm': 'Delivery Confirmation',
            'delivery_mark':    'Mark as Delivered',
        },
    },
    'perm_pos_terminal':    {'label': 'POS Terminal',               'section': 'Operations', 'actions': {}},
    'perm_display_board':   {'label': 'Display Board',              'section': 'Operations', 'actions': {}},
    'perm_pos_orders':      {'label': 'POS Orders',                 'section': 'Operations', 'actions': {}},
    'perm_pickup_scan':     {'label': 'Counter Pickup Scan',        'section': 'Operations', 'actions': {}},
    'perm_counter_tickets': {'label': 'Counter Ticket Board (KOT)', 'section': 'Operations', 'actions': {}},

    # ── Menu Catalog ──────────────────────────────────────────────────────────
    'perm_products': {
        'label': 'Products', 'section': 'Menu Catalog',
        'actions': {
            # List-page standalone actions
            'add':                   'Action: Add Product',
            'toggle':                'On/Off: Web Active',
            'kiosk_toggle':          'On/Off: Kiosk Active',
            'pos_toggle':            'On/Off: POS Active',
            'featured_toggle':       'On/Off: Featured in Kiosk',
            'web_featured_toggle':   'On/Off: Featured on Web',
            'qty_update':            'Action: Quick Qty Update',
            'cashier_edit':          'Action: Cashier Edit Screen',
            'reorder':               'Action: Drag Reorder',
            'copy':                  'Action: Copy Product',
            'bulk_copy':             'Action: Bulk Copy',
            'bulk_upload':           'Action: Excel Bulk Upload',
            'export':                'Action: Excel Export',
            # Edit form — Identity
            'field_name':            'Edit: Product Name',
            'field_code':            'Edit: Code / SKU',
            'field_company':         'Edit: Company / Site',
            'field_category':        'Edit: Category',
            'field_offering':        'Edit: Offering',
            'field_menu_date':       'Edit: Menu Date',
            'field_description':     'Edit: Description',
            # Edit form — Pricing
            'field_price':           'Edit: Staff/Base Price (₹)',
            'field_company_price':   'Edit: Visitor Price (₹)',
            'field_room_service_extra_percent': 'Edit: Room Service Extra (%)',
            'field_packing_price':   'Edit: Packing Price (₹)',
            'field_free_meal':       'Edit: Free Meal / Subsidy Toggle',
            # Edit form — Stock & Ordering
            'field_min_qty':         'Edit: Min Qty per Order',
            'field_max_qty':         'Edit: Max Qty per Order',
            'field_web_qty':         'Edit: Web Stock (web_qty)',
            'field_pos_qty':         'Edit: POS Stock (pos_qty)',
            'field_prep_time':       'Edit: Prep Time (minutes)',
            'field_calories':        'Edit: Calories (kcal)',
            'field_position_order':  'Edit: Sort / Position Order',
            'field_counters':        'Edit: Counters (Pickup Points)',
            # Edit form — Visibility & Status
            'field_food_types':      'Edit: Food Type (Veg / Non-Veg)',
            'field_is_active':       'Edit: Web Ordering Active switch',
            'field_is_kiosk_active': 'Edit: Kiosk Ordering Active switch',
            'field_is_pos_active':   'Edit: POS Ordering Active switch',
            'field_featured_web':    'Edit: Featured on Web Home switch',
            'field_featured_kiosk':  'Edit: Featured in Kiosk switch',
            # Edit form — Schedule
            'field_available_from':  'Edit: Available From (time)',
            'field_available_to':    'Edit: Available To (time)',
            'field_start_date':      'Edit: Start Date',
            'field_end_date':        'Edit: End Date',
            # Edit form — Image
            'field_image':           'Edit: Product Image',
        },
    },

    'perm_categories': {
        'label': 'Categories', 'section': 'Menu Catalog',
        'actions': {
            'add':                    'Action: Add Category',
            'toggle':                 'On/Off: Active',
            'reorder':                'Action: Drag Reorder',
            'bulk_copy':              'Action: Bulk Copy',
            'field_name':             'Edit: Category Name',
            'field_parent':           'Edit: Parent Category',
            'field_icon_type':        'Edit: Icon Type (Veg / Non-Veg)',
            'field_position_order':   'Edit: Sort Order',
            'field_prep_time':        'Edit: Preparation Time (minutes)',
            'field_is_active':        'Edit: Active Status',
            'field_schedule_windows': 'Edit: Availability Time Windows',
            'field_open_days':        'Edit: Available Days',
            'field_tagline':          'Edit: Tagline / Description',
            'field_companies':        'Edit: Company Visibility',
        },
    },

    'perm_offerings': {
        'label': 'Offerings', 'section': 'Menu Catalog',
        'actions': {
            'add':                    'Action: Add Offering',
            'toggle':                 'On/Off: Active',
            'reorder':                'Action: Drag Reorder',
            'field_name':             'Edit: Offering Name',
            'field_schedule_windows': 'Edit: Availability Time Windows',
            'field_available_from':   'Edit: Available From',
            'field_available_to':     'Edit: Available To',
            'field_prep_start_time':  'Edit: Prep Start Gate',
            'field_position_order':   'Edit: Sort Order',
            'field_open_days':        'Edit: Available Days',
            'field_image':            'Edit: Offering Image',
            'field_is_active':        'Edit: Active Status',
        },
    },

    'perm_counters': {
        'label': 'Counters', 'section': 'Menu Catalog',
        'actions': {
            'add':                    'Action: Add Counter',
            'toggle':                 'On/Off: Active',
            'reorder':                'Action: Drag Reorder',
            'field_cafe':             'Edit: Cafe Assignment',
            'field_name':             'Edit: Counter Name',
            'field_code':             'Edit: Code',
            'field_position_order':   'Edit: Sort Order',
            'field_printer_label':    'Edit: Printer Label',
            'field_auto_print_ready': 'Edit: Auto Print When Ready',
            'field_auto_print_scan':  'Edit: Auto Print When Scanned',
            'field_is_active':        'Edit: Active Status',
        },
    },

    'perm_stock': {
        'label': 'Stock Management', 'section': 'Menu Catalog',
        'actions': {
            'update_stock': 'Action: Update Stock Levels',
        },
    },

    # ── Pricing & Promotions ──────────────────────────────────────────────────
    'perm_offers': {
        'label': 'Offers / Discounts', 'section': 'Pricing & Promotions',
        'actions': {
            'add':                    'Action: Add Offer',
            'toggle':                 'On/Off: Active',
            'reset_usage':            'Action: Reset Usage Count',
            'field_title':            'Edit: Offer Title',
            'field_cafe':             'Edit: Cafe',
            'field_offer_type':       'Edit: Offer Type',
            'field_value':            'Edit: Discount Value',
            'field_min_order_value':  'Edit: Min Order Value',
            'field_max_discount':     'Edit: Max Discount Cap',
            'field_product_scope':    'Edit: Product Scope',
            'field_product':          'Edit: Single Product',
            'field_product_ids':      'Edit: Multiple Products',
            'field_start_datetime':   'Edit: Start Date & Time',
            'field_end_datetime':     'Edit: End Date & Time',
            'field_popup_image':      'Edit: Popup Image',
            'field_is_popup_enabled': 'Edit: Show as Popup',
            'field_is_active':        'Edit: Active Status',
        },
    },

    'perm_coupons': {
        'label': 'Coupons', 'section': 'Pricing & Promotions',
        'actions': {
            'add':                  'Action: Add Coupon',
            'toggle':               'On/Off: Active',
            'field_code':           'Edit: Coupon Code',
            'field_discount_type':  'Edit: Discount Type',
            'field_discount_value': 'Edit: Discount Value',
            'field_min_order':      'Edit: Min Order Amount',
            'field_max_discount':   'Edit: Max Discount Cap',
            'field_usage_limit':    'Edit: Usage Limit',
            'field_valid_from':     'Edit: Valid From',
            'field_valid_to':       'Edit: Valid To',
            'field_description':    'Edit: Description',
            'field_is_active':      'Edit: Active Status',
        },
    },
    'perm_site_prices': {
        'label': 'Site-wise Product Prices', 'section': 'Pricing & Promotions',
        'actions': {
            'field_company':   'Edit: Company / Site',
            'field_product':   'Edit: Product',
            'field_building':  'Edit: Building',
            'field_cafe':      'Edit: Cafe',
            'field_price':     'Edit: Price',
            'field_is_active': 'Edit: Active Status',
        },
    },

    # ── Media & Scheduling ────────────────────────────────────────────────────
    'perm_banners': {
        'label': 'Banners / Advertisements & Holidays', 'section': 'Media & Scheduling',
        'actions': {
            'approve':      'Action: Approve Banner',
            'reorder':      'Action: Reorder Banners',
            'holiday_edit': 'Action: Edit Holiday Schedules',
        },
    },
    'perm_media_library': {
        'label': 'Media Library', 'section': 'Media & Scheduling',
        'actions': {
            'rename': 'Action: Rename Files',
        },
    },

    # ── Customers ─────────────────────────────────────────────────────────────
    'perm_customers': {
        'label': 'Customers', 'section': 'Customers',
        'actions': {
            'add':                    'Action: Add Customer',
            'approve':                'Action: Approve Customer',
            'subsidy_toggle':         'Action: Toggle Subsidy',
            'wallet_view':            'Action: View Wallet',
            'wallet_recharge':        'Action: Recharge Wallet',
            'field_name':             'Edit: Full Name',
            'field_phone':            'Edit: Phone',
            'field_date_of_birth':    'Edit: Birth Date',
            'field_building':         'Edit: Building / Floor',
            'field_address':          'Edit: Address',
            'field_password':         'Edit: Set / Reset Password',
            'field_is_active':        'Edit: Account Active',
            'field_is_approved':      'Edit: Approved (Can Order)',
            'field_cod_payment':      'Edit: COD Payment',
            'field_monthly_payment':  'Edit: Monthly Billing',
            'field_meal_benefit':     'Edit: Meal Benefit Type',
            'field_subsidy_override': 'Edit: Custom Subsidy Amount',
            'field_royalty_adjust':   'Edit: Adjust Royalty Points',
        },
    },
    'perm_wallet_recharge': {
        'label': 'Wallet Recharge (standalone)', 'section': 'Customers', 'actions': {},
    },
    'perm_broadcast_notifications': {
        'label': 'Broadcast Notifications', 'section': 'Customers',
        'actions': {
            'send': 'Action: Send Broadcast',
        },
    },

    # ── Reports & Reviews ─────────────────────────────────────────────────────
    'perm_reports':    {'label': 'Reports',             'section': 'Reports & Reviews', 'actions': {}},
    'perm_reviews':    {'label': 'Reviews',             'section': 'Reports & Reviews', 'actions': {}},
    'perm_royalty_lb': {'label': 'Royalty Leaderboard', 'section': 'Reports & Reviews', 'actions': {}},

    # ── Administration ────────────────────────────────────────────────────────
    'perm_geography': {
        'label': 'Geography (States / Cities / Buildings / Locations / Cafes)',
        'section': 'Administration',
        'actions': {
            'building_manage': 'Buildings: Add / Edit / Toggle',
            'cafe_manage':     'Cafes: Add / Edit / Toggle',
            'city_manage':     'Cities: Add / Edit / Toggle',
            'state_manage':    'States: Add / Edit',
            'location_manage': 'Locations: Add / Edit',
        },
    },
    'perm_staff':        {'label': 'Staff Users (View Only)', 'section': 'Administration', 'actions': {}},
    'perm_static_pages': {'label': 'Static Pages',           'section': 'Administration', 'actions': {}},
}


# ── Helper functions for the granular permission system ───────────────────────

def get_staff_module_perm(user, module_key):
    """Return StaffModulePermission for (user, module_key) or None."""
    if user.role == SA:
        return None  # superadmin always full — no DB lookup needed
    try:
        from apps.accounts.models import StaffModulePermission
        return StaffModulePermission.objects.filter(
            staff_user=user, module_key=module_key
        ).first()
    except Exception:
        return None


def get_module_level(user, module_key):
    """Return 'full_edit'|'part_edit'|'view'|None."""
    if user.role == SA:
        return 'full_edit'
    perm = get_staff_module_perm(user, module_key)
    return perm.level if perm else None


def get_module_actions(user, module_key):
    """Return set of allowed action keys for (user, module_key)."""
    if user.role == SA:
        return set(ACTION_REGISTRY.get(module_key, {}).get('actions', {}).keys())
    perm = get_staff_module_perm(user, module_key)
    if not perm:
        return set()
    if perm.level == 'full_edit':
        return set(ACTION_REGISTRY.get(module_key, {}).get('actions', {}).keys())
    if perm.level == 'part_edit':
        actions = set(perm.allowed_actions or [])
        if module_key == 'perm_products':
            if 'toggle' in actions:
                actions.add('field_is_active')
            if 'field_is_active' in actions:
                actions.add('toggle')
            if 'kiosk_toggle' in actions:
                actions.add('field_is_kiosk_active')
            if 'field_is_kiosk_active' in actions:
                actions.add('kiosk_toggle')
            if 'pos_toggle' in actions:
                actions.add('field_is_pos_active')
            if 'field_is_pos_active' in actions:
                actions.add('pos_toggle')
            if 'web_featured_toggle' in actions:
                actions.add('field_featured_web')
            if 'field_featured_web' in actions:
                actions.add('web_featured_toggle')
            if 'featured_toggle' in actions:
                actions.add('field_featured_kiosk')
            if 'field_featured_kiosk' in actions:
                actions.add('featured_toggle')
            if 'qty_update' in actions:
                actions.update({'field_web_qty', 'field_pos_qty'})
        return actions
    return set()  # view only


def user_can_action(user, module_key, action_key):
    """Return True if user can perform action_key in module_key."""
    if user.role == SA:
        return True
    return action_key in get_module_actions(user, module_key)


def get_pending_count():
    """Return count of pending changes awaiting superadmin review."""
    try:
        from apps.accounts.models import PendingChange
        return PendingChange.objects.filter(status='pending').count()
    except Exception:
        return 0


def has_any_granular_perms(user):
    """Return True if this user has ANY StaffModulePermission rows.
    Gate: existing staff with no granular setup are completely unaffected."""
    try:
        from apps.accounts.models import StaffModulePermission
        return StaffModulePermission.objects.filter(staff_user=user).exists()
    except Exception:
        return False


def create_pending_change(request, module_key, instance, field_diffs):
    """
    Create a PendingChange record for a full_edit staff submission.
    field_diffs: {model_field_name: {'label': str, 'before': val, 'after': val}}
    Only fields where before != after are stored.
    Returns the PendingChange or None if nothing changed.
    """
    try:
        from apps.accounts.models import PendingChange
        changed = {
            k: v for k, v in field_diffs.items()
            if str(v.get('before', '')) != str(v.get('after', ''))
        }
        if not changed:
            return None
        return PendingChange.objects.create(
            staff_user=request.user,
            module_key=module_key,
            object_id=instance.pk,
            object_label=str(instance),
            field_diffs=changed,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error('create_pending_change failed: %s', e)
        return None


def get_list_perms(user, module_key):
    """
    Return dict {action_key: bool} for list-page button visibility.
    Superadmin -> all True. Staff -> action-based granular matrix only.
    """
    all_actions = set(ACTION_REGISTRY.get(module_key, {}).get('actions', {}).keys())

    def _all_true():
        d = {a: True for a in all_actions}
        d.update({'edit': True, 'delete': True})
        return d

    def _all_false():
        d = {a: False for a in all_actions}
        d.update({'edit': False, 'delete': False})
        return d

    if user.role == 'superadmin':
        return _all_true()

    if has_any_granular_perms(user):
        level = get_module_level(user, module_key)
        if not level:
            return _all_false()
        allowed = get_module_actions(user, module_key)
        d = {a: (a in allowed) for a in all_actions}
        d['edit']   = level in ('part_edit', 'full_edit')
        d['delete'] = level == 'full_edit'
        if user.role == 'pos':
            d.setdefault('cashier_edit', True)
        return d

    return _all_false()


def check_module_permission(request, module_key):
    """Call at the top of any edit view to enforce granular permissions.
    Returns HttpResponseRedirect if denied, or None to proceed.

    Rules:
      - superadmin              -> None (always proceed)
      - no granular row      -> redirect no_access
      - no row for this module  -> redirect no_access
      - level == view + POST    -> redirect no_access
      - part_edit / full_edit   -> None (field locking in Phase 2-A/B)
    """
    from django.shortcuts import redirect
    from django.contrib import messages as _msg
    user = request.user
    if user.role == 'superadmin':
        return None
    level = get_module_level(user, module_key)
    if level is None:
        _msg.error(request, 'You do not have access to this section.')
        return redirect('dashboard:no_access')
    if level == 'view' and request.method == 'POST':
        _msg.error(request, 'You have view-only access and cannot save changes.')
        return redirect('dashboard:no_access')
    return None


# ── Field-to-HTML-name map for Phase 2-A visual field locking ────────────────
# Maps module_key -> {action_key -> [html input name(s)]}
# __schedule_windows__ is a special marker handled by JS regex matching.

FIELD_HTML_NAMES = {
    'perm_products': {
        'field_name': ['name'], 'field_code': ['code'],
        'field_category': ['category'], 'field_company': ['company'],
        'field_offering': ['offering'],
        'field_menu_date': ['menu_date'], 'field_description': ['description'],
        'field_price': ['price'], 'field_company_price': ['company_price'],
        'field_room_service_extra_percent': ['room_service_extra_percent'],
        'field_packing_price': ['packing_price'], 'field_free_meal': ['is_free_meal_product'],
        'field_min_qty': ['min_qty'], 'field_max_qty': ['max_qty'],
        'field_web_qty': ['web_qty'], 'field_pos_qty': ['pos_qty'],
        'field_prep_time': ['preparation_time_minutes'], 'field_calories': ['calories'],
        'field_position_order': ['position_order'], 'field_counters': ['counter_ids'],
        'field_food_types': ['food_types'], 'field_is_active': ['is_active'],
        'field_is_kiosk_active': ['is_kiosk_active'], 'field_is_pos_active': ['is_pos_active'],
        'field_featured_web': ['featured_in_web'],
        'field_featured_kiosk': ['featured_in_kiosk_extra'],
        'field_available_from': ['available_from'], 'field_available_to': ['available_to'],
        'field_start_date': ['start_date'], 'field_end_date': ['end_date'],
        'field_image': ['image', 'gallery_image_url'],
    },
    'perm_categories': {
        'field_name': ['name'], 'field_parent': ['parent_id'],
        'field_icon_type': ['icon_type'], 'field_position_order': ['position_order'],
        'field_prep_time': ['preparation_time_minutes'], 'field_is_active': ['is_active'],
        'field_schedule_windows': ['__schedule_windows__'],
        'field_open_days': ['open_days'], 'field_tagline': ['tagline'],
        'field_companies': ['companies'],
    },
    'perm_offerings': {
        'field_name': ['name'], 'field_schedule_windows': ['__schedule_windows__'],
        'field_available_from': ['available_from'], 'field_available_to': ['available_to'],
        'field_prep_start_time': ['prep_start_time'], 'field_position_order': ['position_order'],
        'field_open_days': ['open_days'], 'field_image': ['image', 'gallery_image_url'],
        'field_is_active': ['is_active'],
    },
    'perm_counters': {
        'field_cafe': ['cafe'], 'field_name': ['name'], 'field_code': ['code'],
        'field_position_order': ['position_order'], 'field_printer_label': ['printer_label'],
        'field_auto_print_ready': ['auto_print_on_ready'],
        'field_auto_print_scan': ['auto_print_on_scan'], 'field_is_active': ['is_active'],
    },
    'perm_offers': {
        'field_title': ['title'], 'field_cafe': ['cafe'],
        'field_offer_type': ['offer_type'], 'field_value': ['value'],
        'field_min_order_value': ['min_order_value'], 'field_max_discount': ['max_discount'],
        'field_product_scope': ['product_scope'], 'field_product': ['product'],
        'field_product_ids': ['product_ids'], 'field_start_datetime': ['start_datetime'],
        'field_end_datetime': ['end_datetime'], 'field_popup_image': ['popup_image'],
        'field_is_popup_enabled': ['is_popup_enabled'], 'field_is_active': ['is_active'],
    },
    'perm_coupons': {
        'field_code': ['code'], 'field_discount_type': ['discount_type'],
        'field_discount_value': ['discount_value'], 'field_min_order': ['min_order'],
        'field_max_discount': ['max_discount'], 'field_usage_limit': ['usage_limit'],
        'field_valid_from': ['valid_from'], 'field_valid_to': ['valid_to'],
        'field_description': ['description'], 'field_is_active': ['is_active'],
    },
    'perm_site_prices': {
        'field_company': ['company'], 'field_product': ['product'],
        'field_building': ['building'], 'field_cafe': ['cafe'],
        'field_price': ['price'], 'field_is_active': ['is_active'],
    },
    'perm_customers': {
        'field_name': ['name'], 'field_phone': ['phone'],
        'field_date_of_birth': ['date_of_birth'], 'field_building': ['building'],
        'field_address': ['address'], 'field_password': ['new_password'],
        'field_is_active': ['is_active'], 'field_is_approved': ['is_approved'],
        'field_cod_payment': ['cod_payment'], 'field_monthly_payment': ['monthly_payment'],
        'field_meal_benefit': ['meal_benefit'],
        'field_subsidy_override': ['subsidy_amount_override'],
        'field_royalty_adjust': ['royalty_adjust'],
    },
}


def get_locked_html_names(user, module_key):
    """Return (locked_names_json_str, level_str) for template field locking.
    locked_names_json_str is a JSON array of HTML input name attributes to disable.
    Special value '__schedule_windows__' triggers regex-based locking in JS.
    """
    import json
    level = get_module_level(user, module_key)
    if user.role == 'superadmin':
        return '[]', 'full_edit'
    if not level:
        return '[]', None
    allowed = get_module_actions(user, module_key)
    field_map = FIELD_HTML_NAMES.get(module_key, {})
    if level == 'view':
        locked_keys = set(field_map.keys())
    elif level == 'part_edit':
        locked_keys = {k for k in field_map if k not in allowed}
    else:
        locked_keys = set()
    result = []
    for k in locked_keys:
        result.extend(field_map.get(k, []))
    return json.dumps(result), level
