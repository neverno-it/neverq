from collections import OrderedDict

MENU_REGISTRY = [
    {
        "key": "overview.dashboard",
        "label": "Dashboard",
        "section": "Overview",
        "roles": ["admin", "reports"],
        "view_names": ["dashboard:home"],
    },
    {
        "key": "overview.cashier",
        "label": "Cashier Dashboard",
        "section": "Overview",
        "roles": ["admin", "pos"],
        "view_names": ["dashboard:cashier"],
    },
    {
        "key": "overview.kitchen",
        "label": "Kitchen Orders",
        "section": "Overview",
        "roles": ["admin", "cafeman"],
        "view_names": ["dashboard:kitchen"],
    },
    {
        "key": "operations.orders",
        "label": "Orders",
        "section": "Operations",
        "roles": ["admin", "reports", "pos", "cafeman"],
        "view_names": ["dashboard:order_list", "dashboard:order_detail", "dashboard:order_update_status"],
    },
    {
        "key": "operations.pos_terminal",
        "label": "POS Terminal",
        "section": "Operations",
        "roles": ["admin", "pos"],
        "view_names": ["pos:terminal", "pos:place_order", "pos:receipt"],
    },
    {
        "key": "operations.display_board",
        "label": "Display Board",
        "section": "Operations",
        "roles": ["admin", "pos", "cafeman"],
        "view_names": ["dashboard:display_board_select", "orders:display_board", "orders:display_board_company"],
    },
    {
        "key": "operations.pos_sales",
        "label": "POS Sales",
        "section": "Operations",
        "roles": ["admin", "pos", "reports"],
        "view_names": ["pos:order_list", "pos:kot_data"],
    },
    {
        "key": "operations.delivery_confirmation",
        "label": "Delivery Confirmation",
        "section": "Operations",
        "roles": ["admin", "pos", "cafeman"],
        "view_names": [
            "orders:delivery_confirmation_list",
            "orders:delivery_mark_delivered",
            "orders:delivery_packet_labels",
        ],
    },
    {
        "key": "menu.products",
        "label": "Products / Web Menu Items",
        "section": "Menu",
        "roles": ["admin", "cafeman", "reports", "pos"],
        "view_names": [
            "dashboard:product_list", "dashboard:product_add", "dashboard:product_bulk_upload",
            "dashboard:product_edit", "dashboard:product_toggle", "dashboard:product_delete",
            "pos:products", "pos:product_toggle", "pos:product_edit"
        ],
    },
    {
        "key": "menu.categories",
        "label": "Categories / Subcategory",
        "section": "Menu",
        "roles": [],  # superadmin-only; not assigned via menu registry
        "view_names": [
            "dashboard:category_list", "dashboard:category_add", "dashboard:category_edit",
            "dashboard:category_toggle", "dashboard:category_delete"
        ],
    },
    {
        "key": "menu.banners",
        "label": "Banners",
        "section": "Menu",
        "roles": ["admin", "pos"],
        "view_names": [
            "dashboard:advertise_list", "dashboard:advertise_add", "dashboard:advertise_edit",
            "dashboard:advertise_delete", "dashboard:advertise_approve"
        ],
    },
    {
        "key": "menu.media_library",
        "label": "Media Library",
        "section": "Menu",
        "roles": ["admin", "pos"],
        "view_names": ["dashboard:media_library", "dashboard:media_library_delete"],
    },
    {
        "key": "menu.holidays",
        "label": "Holiday Schedules",
        "section": "Menu",
        "roles": ["admin"],
        "view_names": ["dashboard:holiday_list", "dashboard:holiday_edit"],
    },
    {
        "key": "users.customers",
        "label": "Customers",
        "section": "Users",
        "roles": ["admin"],
        "view_names": ["dashboard:customer_list", "dashboard:customer_add", "dashboard:customer_edit"],
    },
    {
        "key": "users.reviews",
        "label": "Reviews",
        "section": "Users",
        "roles": ["admin"],
        "view_names": ["dashboard:reviews_list"],
    },
    {
        "key": "users.reports",
        "label": "Reports",
        "section": "Users",
        "roles": ["admin", "reports", "pos"],
        "view_names": ["dashboard:reports"],
    },
    {
        "key": "users.flash_order",
        "label": "Flash Order",
        "section": "Users",
        "roles": ["admin", "pos"],
        "view_names": ["dashboard:flash_order", "dashboard:customer_search"],
    },
    {
        "key": "users.coupons",
        "label": "Coupons",
        "section": "Users",
        "roles": ["admin"],
        "view_names": ["dashboard:coupon_list", "dashboard:coupon_add", "dashboard:coupon_edit", "dashboard:coupon_delete"],
    },
    {
        "key": "admin.companies",
        "label": "Companies",
        "section": "Administration",
        "roles": [],  # superadmin-only
        "view_names": ["dashboard:company_list", "dashboard:company_add", "dashboard:company_detail", "dashboard:company_edit", "dashboard:building_add", "dashboard:building_list", "dashboard:building_edit", "dashboard:building_toggle", "dashboard:building_delete", "dashboard:city_list", "dashboard:city_add", "dashboard:city_edit", "dashboard:city_toggle", "dashboard:city_delete", "dashboard:cafe_list", "dashboard:cafe_add", "dashboard:cafe_edit", "dashboard:cafe_toggle", "dashboard:cafe_delete", "dashboard:state_list", "dashboard:state_add", "dashboard:state_edit", "dashboard:state_delete"],
    },
    {
        "key": "admin.master_locations",
        "label": "Locations / Buildings / Cafeterias",
        "section": "Administration",
        "roles": [],  # superadmin-only
        "view_names": [
            "dashboard:state_list", "dashboard:state_add", "dashboard:state_edit", "dashboard:state_delete",
            "dashboard:city_list", "dashboard:city_add", "dashboard:city_edit", "dashboard:city_toggle", "dashboard:city_delete",
            "dashboard:building_list", "dashboard:building_add", "dashboard:building_edit", "dashboard:building_toggle", "dashboard:building_delete",
            "dashboard:cafe_list", "dashboard:cafe_add", "dashboard:cafe_edit", "dashboard:cafe_toggle", "dashboard:cafe_delete"
        ],
    },
    {
        "key": "admin.staff",
        "label": "Staff Users",
        "section": "Administration",
        "roles": ["admin"],
        "view_names": ["dashboard:staff_list"],
    },
    {
        "key": "admin.menu_access",
        "label": "Menu Access Control",
        "section": "Administration",
        "roles": ["admin"],
        "view_names": ["dashboard:menu_access"],
    },
    {
        "key": "admin.static_pages",
        "label": "Static Pages",
        "section": "Administration",
        "roles": ["admin"],
        "view_names": ["dashboard:static_page_list", "dashboard:static_page_edit"],
    },
]


def get_all_menu_keys():
    return [item["key"] for item in MENU_REGISTRY]


def get_assignable_menu_items(role):
    if role == "superadmin":
        return MENU_REGISTRY
    return [item for item in MENU_REGISTRY if role in item["roles"]]


def get_default_menu_keys(role):
    if role == "superadmin":
        return get_all_menu_keys()
    return [item["key"] for item in get_assignable_menu_items(role)]


def get_view_to_menu_map():
    mapping = {}
    for item in MENU_REGISTRY:
        for view_name in item["view_names"]:
            mapping[view_name] = item["key"]
    return mapping


def group_menu_items(items):
    grouped = OrderedDict()
    for item in items:
        grouped.setdefault(item["section"], []).append(item)
    return grouped


def get_allowed_menu_keys(user):
    if not getattr(user, 'is_authenticated', False) or not hasattr(user, 'role'):
        return []
    if user.role == 'superadmin':
        return get_all_menu_keys()

    default_keys = set(get_default_menu_keys(user.role))
    access = getattr(user, 'dashboard_menu_access', None)
    if access is None:
        return list(default_keys)

    saved = []
    for key in (access.allowed_keys or []):
        if key in default_keys:
            saved.append(key)
    return saved
