from django.urls import path
from .dashboard_views import (
    dashboard_home, cashier_dashboard, kitchen, store_toggle, company_store_toggle,
    company_list, company_detail, company_add, company_edit,
    customer_list, customer_add, customer_edit, customer_delete, customer_bulk_delete, customer_search_ajax,
    customer_toggle_subsidy, customer_set_meal_benefit,
    order_list, order_detail, order_update_status,
    staff_list, reviews_list, building_add, building_list, building_edit, building_toggle, building_delete, building_bulk_delete,
    city_list, city_add, city_edit, city_toggle, city_delete, city_bulk_delete,
    state_list, state_add, state_edit, state_delete, state_bulk_delete,
    cafe_list, cafe_add, cafe_edit, cafe_toggle, cafe_delete, cafe_bulk_delete,
    reports, flash_order,
    coupon_list, coupon_add, coupon_edit, coupon_delete, coupon_bulk_delete,
    static_page_list, static_page_edit,
    user_access, user_access_edit, no_access,
    product_update_qty,
    product_gallery, product_gallery_delete, product_gallery_bulk_delete, product_gallery_api, product_gallery_rename,
    offering_gallery, offering_gallery_delete, offering_gallery_bulk_delete, offering_gallery_api, offering_gallery_rename,
    customer_approve, customer_wallet, wallet_recharge,
    location_list, location_add, location_edit, location_delete, location_bulk_delete,
    hierarchy_overview,
    royalty_leaderboard, display_board_select,
    kiosk_config_list, kiosk_config_add, kiosk_config_edit, kiosk_config_delete, kiosk_config_bulk_delete,
    web_config_list, web_config_add, web_config_edit, web_config_delete, web_config_bulk_delete,
    display_config_list, display_config_add, display_config_edit, display_config_delete, display_config_bulk_delete,
    category_gallery, category_gallery_delete, category_gallery_bulk_delete, category_gallery_rename, category_gallery_api,
    broadcast_notification_list, broadcast_notification_send, broadcast_notification_delete, broadcast_notification_bulk_delete,
    permission_matrix, pending_changes_list, pending_change_review,
)
from apps.orders.views import (
    delivery_confirmation_list, delivery_mark_delivered, delivery_packet_labels,
)
from apps.menu.views import (
    dashboard_product_list, dashboard_product_add,
    dashboard_product_edit, dashboard_product_toggle, dashboard_product_kiosk_toggle, dashboard_product_pos_toggle,
    dashboard_product_schedule_bypass_toggle, dashboard_product_delete, dashboard_product_bulk_delete,
    dashboard_product_featured_toggle,
    dashboard_product_web_featured_toggle,
    dashboard_product_bulk_upload,
    dashboard_category_list, dashboard_category_add,
    dashboard_category_edit, dashboard_category_toggle, dashboard_category_delete, dashboard_category_bulk_delete,
    dashboard_offering_list, dashboard_offering_add, dashboard_offering_edit,
    dashboard_offering_toggle, dashboard_offering_delete, dashboard_offering_bulk_delete,
    dashboard_counter_list, dashboard_counter_add, dashboard_counter_edit,
    dashboard_counter_toggle, dashboard_counter_delete, dashboard_counter_bulk_delete,
    dashboard_offer_list, dashboard_offer_add, dashboard_offer_edit,
    dashboard_offer_toggle, dashboard_offer_delete, dashboard_offer_bulk_delete, dashboard_offer_reset_usage,
    offer_cafe_options,
    counter_ticket_board, counter_ticket_update, counter_ticket_kot,
    category_bulk_copy,
    stock_management,
    dashboard_product_copy, product_bulk_sample_download, product_excel_download,
    product_reorder, category_reorder, offering_reorder, counter_reorder, advertise_reorder,
    product_bulk_copy,
    dashboard_product_cashier_edit,
    product_bulk_image_upload,
    dashboard_advertise_list, dashboard_advertise_add,
    dashboard_advertise_edit, dashboard_advertise_delete, dashboard_advertise_bulk_delete,
    dashboard_advertise_approve,
    media_library, media_library_rename, media_library_delete, media_library_bulk_delete,
    holiday_list, holiday_edit,
)

app_name = 'dashboard'

urlpatterns = [
    path('',                                   dashboard_home,            name='home'),
    path('no-access/',                         no_access,                 name='no_access'),
    path('cashier/',                            cashier_dashboard,         name='cashier'),
    path('kitchen/',                            kitchen,                   name='kitchen'),
    path('store-toggle/',                       store_toggle,              name='store_toggle'),
    path('reports/',                            reports,                   name='reports'),
    path('flash-order/',                        flash_order,               name='flash_order'),

    # Companies
    path('companies/',                          company_list,              name='company_list'),
    path('companies/add/',                      company_add,               name='company_add'),
    path('companies/<int:pk>/',                 company_detail,            name='company_detail'),
    path('companies/<int:pk>/edit/',            company_edit,              name='company_edit'),
    path('companies/<int:pk>/store-toggle/',    company_store_toggle,      name='company_store_toggle'),
    path('buildings/add/',                      building_add,              name='building_add'),
    path('buildings/',                          building_list,             name='building_list'),
    path('buildings/<int:pk>/edit/',             building_edit,             name='building_edit'),
    path('buildings/<int:pk>/toggle/',           building_toggle,           name='building_toggle'),
    path('buildings/<int:pk>/delete/',           building_delete,           name='building_delete'),
    path('buildings/bulk-delete/',                building_bulk_delete,      name='building_bulk_delete'),

    # Locations
    path('locations/',                          location_list,             name='location_list'),
    path('locations/add/',                      location_add,              name='location_add'),
    path('locations/<int:pk>/edit/',             location_edit,             name='location_edit'),
    path('locations/<int:pk>/delete/',           location_delete,           name='location_delete'),
    path('locations/bulk-delete/',                location_bulk_delete,      name='location_bulk_delete'),

    # Hierarchy overview
    path('hierarchy/',                          hierarchy_overview,        name='hierarchy'),

    # Royalty leaderboard
    path('royalty/leaderboard/',               royalty_leaderboard,        name='royalty_leaderboard'),
    path('display-board/',                     display_board_select,       name='display_board_select'),

    # Kiosk configurations
    path('kiosk-configs/',                      kiosk_config_list,         name='kiosk_config_list'),
    path('kiosk-configs/add/',                  kiosk_config_add,          name='kiosk_config_add'),
    path('kiosk-configs/<int:pk>/edit/',         kiosk_config_edit,         name='kiosk_config_edit'),
    path('kiosk-configs/<int:pk>/delete/',       kiosk_config_delete,       name='kiosk_config_delete'),
    path('kiosk-configs/bulk-delete/',            kiosk_config_bulk_delete,  name='kiosk_config_bulk_delete'),
    path('web-configs/',                        web_config_list,           name='web_config_list'),
    path('web-configs/add/',                    web_config_add,            name='web_config_add'),
    path('web-configs/<int:pk>/edit/',          web_config_edit,           name='web_config_edit'),
    path('web-configs/<int:pk>/delete/',        web_config_delete,         name='web_config_delete'),
    path('web-configs/bulk-delete/',            web_config_bulk_delete,    name='web_config_bulk_delete'),
    path('display-configs/',                    display_config_list,       name='display_config_list'),
    path('display-configs/add/',                display_config_add,        name='display_config_add'),
    path('display-configs/<int:pk>/edit/',      display_config_edit,       name='display_config_edit'),
    path('display-configs/<int:pk>/delete/',    display_config_delete,     name='display_config_delete'),
    path('display-configs/bulk-delete/',        display_config_bulk_delete, name='display_config_bulk_delete'),
    path('states/',                             state_list,                name='state_list'),
    path('states/add/',                         state_add,                 name='state_add'),
    path('states/<int:pk>/edit/',               state_edit,                name='state_edit'),
    path('states/<int:pk>/delete/',             state_delete,              name='state_delete'),
    path('states/bulk-delete/',                  state_bulk_delete,         name='state_bulk_delete'),
    path('cities/',                             city_list,                 name='city_list'),
    path('cities/add/',                         city_add,                  name='city_add'),
    path('cities/<int:pk>/edit/',               city_edit,                 name='city_edit'),
    path('cities/<int:pk>/toggle/',             city_toggle,               name='city_toggle'),
    path('cities/<int:pk>/delete/',             city_delete,               name='city_delete'),
    path('cities/bulk-delete/',                  city_bulk_delete,          name='city_bulk_delete'),
    path('cafes/',                              cafe_list,                 name='cafe_list'),
    path('cafes/add/',                          cafe_add,                  name='cafe_add'),
    path('cafes/<int:pk>/edit/',                cafe_edit,                 name='cafe_edit'),
    path('cafes/<int:pk>/toggle/',              cafe_toggle,               name='cafe_toggle'),
    path('cafes/<int:pk>/delete/',              cafe_delete,               name='cafe_delete'),
    path('cafes/bulk-delete/',                   cafe_bulk_delete,          name='cafe_bulk_delete'),

    # Customers
    path('customers/',                          customer_list,             name='customer_list'),
    path('customers/add/',                      customer_add,              name='customer_add'),
    path('customers/<int:pk>/edit/',            customer_edit,             name='customer_edit'),
    path('customers/<int:pk>/toggle-subsidy/',  customer_toggle_subsidy,   name='customer_toggle_subsidy'),
    path('customers/<int:pk>/set-benefit/',     customer_set_meal_benefit,  name='customer_set_meal_benefit'),
    path('customers/<int:pk>/delete/',           customer_delete,           name='customer_delete'),
    path('customers/bulk-delete/',               customer_bulk_delete,      name='customer_bulk_delete'),
    path('customers/search/',                   customer_search_ajax,      name='customer_search'),

    # Orders
    path('orders/',                             order_list,                name='order_list'),
    path('orders/<int:pk>/',                    order_detail,              name='order_detail'),
    path('orders/<int:pk>/status/',             order_update_status,       name='order_update_status'),
    path('orders/delivery/confirmation/',       delivery_confirmation_list, name='delivery_confirmation_list'),
    path('orders/delivery/mark-delivered/',     delivery_mark_delivered,   name='delivery_mark_delivered'),
    path('orders/delivery/packet-labels/',      delivery_packet_labels,    name='delivery_packet_labels'),

    # Products
    path('menu/products/',                      dashboard_product_list,    name='product_list'),
    path('menu/products/add/',                  dashboard_product_add,     name='product_add'),
    path('menu/products/bulk-upload/',          dashboard_product_bulk_upload, name='product_bulk_upload'),
    path('menu/products/bulk-upload/sample/',   product_bulk_sample_download, name='product_bulk_sample_download'),
    path('menu/products/bulk-upload/images/',   product_bulk_image_upload,    name='product_bulk_image_upload'),
    path('menu/products/export/',               product_excel_download,        name='product_excel_download'),
    path('menu/products/<int:pk>/copy/',        dashboard_product_copy, name='product_copy'),
    path('menu/products/<int:pk>/edit/',        dashboard_product_edit,    name='product_edit'),
    path('menu/products/<int:pk>/toggle/',       dashboard_product_toggle,       name='product_toggle'),
    path('menu/products/<int:pk>/kiosk-toggle/',   dashboard_product_kiosk_toggle,         name='product_kiosk_toggle'),
    path('menu/products/<int:pk>/pos-toggle/',     dashboard_product_pos_toggle,           name='product_pos_toggle'),
    path('menu/products/<int:pk>/bypass-toggle/',    dashboard_product_schedule_bypass_toggle, name='product_bypass_toggle'),
    path('menu/products/<int:pk>/featured-toggle/',  dashboard_product_featured_toggle,        name='product_featured_toggle'),
    path('menu/products/<int:pk>/web-featured-toggle/', dashboard_product_web_featured_toggle,    name='product_web_featured_toggle'),
    path('menu/products/<int:pk>/qty/',          product_update_qty,        name='product_update_qty'),
    path('menu/products/<int:pk>/delete/',      dashboard_product_delete,  name='product_delete'),
    path('menu/products/bulk-delete/',           dashboard_product_bulk_delete, name='product_bulk_delete'),

    # Phase 1 — Reorder + Bulk Copy
    path('menu/products/reorder/',              product_reorder,           name='product_reorder'),
    path('menu/products/<int:pk>/cashier-edit/', dashboard_product_cashier_edit, name='product_cashier_edit'),
    path('menu/products/bulk-copy/',            product_bulk_copy,         name='product_bulk_copy'),
    path('menu/categories/reorder/',            category_reorder,          name='category_reorder'),
    path('menu/offerings/reorder/',             offering_reorder,          name='offering_reorder'),
    path('menu/counters/reorder/',              counter_reorder,           name='counter_reorder'),
    path('advertise/reorder/',                  advertise_reorder,         name='advertise_reorder'),

    # Offerings / Counters / Offers
    path('menu/offerings/',                     dashboard_offering_list,   name='offering_list'),
    path('menu/offerings/add/',                 dashboard_offering_add,    name='offering_add'),
    path('menu/offerings/<int:pk>/edit/',       dashboard_offering_edit,   name='offering_edit'),
    path('menu/offerings/<int:pk>/toggle/',     dashboard_offering_toggle, name='offering_toggle'),
    path('menu/offerings/<int:pk>/delete/',     dashboard_offering_delete, name='offering_delete'),
    path('menu/offerings/bulk-delete/',          dashboard_offering_bulk_delete, name='offering_bulk_delete'),
    path('menu/counters/',                      dashboard_counter_list,    name='counter_list'),
    path('menu/counters/add/',                  dashboard_counter_add,     name='counter_add'),
    path('menu/counters/<int:pk>/edit/',        dashboard_counter_edit,    name='counter_edit'),
    path('menu/counters/<int:pk>/toggle/',      dashboard_counter_toggle,  name='counter_toggle'),
    path('menu/counters/<int:pk>/delete/',      dashboard_counter_delete,  name='counter_delete'),
    path('menu/counters/bulk-delete/',           dashboard_counter_bulk_delete, name='counter_bulk_delete'),
    path('menu/offers/',                        dashboard_offer_list,      name='offer_list'),
    path('menu/offers/add/',                    dashboard_offer_add,       name='offer_add'),
    path('menu/offers/<int:pk>/edit/',          dashboard_offer_edit,      name='offer_edit'),
    path('menu/offers/<int:pk>/toggle/',        dashboard_offer_toggle,    name='offer_toggle'),
    path('menu/offers/<int:pk>/delete/',        dashboard_offer_delete,    name='offer_delete'),
    path('menu/offers/bulk-delete/',             dashboard_offer_bulk_delete, name='offer_bulk_delete'),
    path('menu/offers/<int:pk>/reset-usage/',   dashboard_offer_reset_usage, name='offer_reset_usage'),
    path('menu/offers/cafe-options/',           offer_cafe_options,          name='offer_cafe_options'),

    # Categories
    path('menu/categories/',                    dashboard_category_list,   name='category_list'),
    path('menu/categories/add/',                dashboard_category_add,    name='category_add'),
    path('menu/categories/<int:pk>/edit/',      dashboard_category_edit,   name='category_edit'),
    path('menu/categories/<int:pk>/toggle/',    dashboard_category_toggle, name='category_toggle'),
    path('menu/categories/<int:pk>/delete/',    dashboard_category_delete, name='category_delete'),
    path('menu/categories/bulk-delete/',         dashboard_category_bulk_delete, name='category_bulk_delete'),

    # Banners / Advertisements
    path('advertise/',                          dashboard_advertise_list,  name='advertise_list'),
    path('advertise/add/',                      dashboard_advertise_add,   name='advertise_add'),
    path('advertise/<int:pk>/edit/',            dashboard_advertise_edit,  name='advertise_edit'),
    path('advertise/<int:pk>/delete/',          dashboard_advertise_delete,name='advertise_delete'),
    path('advertise/bulk-delete/',               dashboard_advertise_bulk_delete, name='advertise_bulk_delete'),
    path('advertise/<int:pk>/approve/',         dashboard_advertise_approve, name='advertise_approve'),

    # Media Library
    path('media-library/',                      media_library,             name='media_library'),
    path('media-library/<int:pk>/rename/',      media_library_rename,      name='media_library_rename'),
    path('media-library/<int:pk>/delete/',      media_library_delete,      name='media_library_delete'),
    path('media-library/bulk-delete/',           media_library_bulk_delete, name='media_library_bulk_delete'),

    # Holiday Schedules
    path('holidays/',                           holiday_list,              name='holiday_list'),
    path('holidays/<int:pk>/edit/',             holiday_edit,              name='holiday_edit'),

    # Reviews + Staff
    path('reviews/',                            reviews_list,              name='reviews_list'),
    path('staff/',                              staff_list,                name='staff_list'),

    # Coupons
    path('coupons/',                            coupon_list,               name='coupon_list'),
    path('coupons/add/',                        coupon_add,                name='coupon_add'),
    path('coupons/<int:pk>/edit/',              coupon_edit,               name='coupon_edit'),
    path('coupons/<int:pk>/delete/',            coupon_delete,             name='coupon_delete'),
    path('coupons/bulk-delete/',                 coupon_bulk_delete,        name='coupon_bulk_delete'),

    # Static Pages
    path('pages/',                              static_page_list,          name='static_page_list'),
    path('pages/<int:pk>/edit/',                static_page_edit,          name='static_page_edit'),
    path('user-access/',                        user_access,               name='user_access'),
    path('user-access/<int:pk>/',                user_access_edit,          name='user_access_edit'),

    # Counter Ticket Board
    path('counter-tickets/',                    counter_ticket_board,      name='counter_ticket_board'),
    path('counter-tickets/<int:pk>/update/',    counter_ticket_update,     name='counter_ticket_update'),
    path('counter-tickets/<int:pk>/kot/',       counter_ticket_kot,        name='counter_ticket_kot'),

    path('menu/categories/bulk-copy/',           category_bulk_copy,        name='category_bulk_copy'),

    # Stock Management
    path('menu/stock/',                         stock_management,          name='stock_management'),

    # Product Gallery
    path('menu/product-gallery/',               product_gallery,           name='product_gallery'),
    path('menu/product-gallery/<int:pk>/delete/', product_gallery_delete,  name='product_gallery_delete'),
    path('menu/product-gallery/bulk-delete/',    product_gallery_bulk_delete, name='product_gallery_bulk_delete'),
    path('menu/product-gallery/<int:pk>/rename/', product_gallery_rename,  name='product_gallery_rename'),
    path('menu/product-gallery/api/',           product_gallery_api,       name='product_gallery_api'),
    path('menu/offering-gallery/',              offering_gallery,          name='offering_gallery'),
    path('menu/offering-gallery/<int:pk>/delete/', offering_gallery_delete,name='offering_gallery_delete'),
    path('menu/offering-gallery/bulk-delete/',   offering_gallery_bulk_delete, name='offering_gallery_bulk_delete'),
    path('menu/offering-gallery/<int:pk>/rename/', offering_gallery_rename,name='offering_gallery_rename'),
    path('menu/offering-gallery/api/',          offering_gallery_api,      name='offering_gallery_api'),
    path('menu/category-gallery/',               category_gallery,           name='category_gallery'),
    path('menu/category-gallery/<int:pk>/delete/', category_gallery_delete,  name='category_gallery_delete'),
    path('menu/category-gallery/bulk-delete/',    category_gallery_bulk_delete, name='category_gallery_bulk_delete'),
    path('menu/category-gallery/<int:pk>/rename/', category_gallery_rename,  name='category_gallery_rename'),
    path('menu/category-gallery/api/',           category_gallery_api,       name='category_gallery_api'),

    # Customer approval & wallet
    path('customers/<int:pk>/approve/',         customer_approve,          name='customer_approve'),
    path('customers/<int:pk>/wallet/',          customer_wallet,           name='customer_wallet'),
    path('wallet/recharge/',                    wallet_recharge,           name='wallet_recharge'),

    # Broadcast Notifications
    path('notifications/',       broadcast_notification_list, name='broadcast_notification_list'),
    path('notifications/send/',  broadcast_notification_send, name='broadcast_notification_send'),
    path('notifications/<int:pk>/delete/', broadcast_notification_delete, name='broadcast_notification_delete'),
    path('notifications/bulk-delete/',    broadcast_notification_bulk_delete, name='broadcast_notification_bulk_delete'),

    # ── Granular Permission Matrix ────────────────────────────────────────
    path('staff/<int:pk>/permissions/',      permission_matrix,      name='permission_matrix'),
    path('pending-changes/',                 pending_changes_list,   name='pending_changes'),
    path('pending-changes/<int:pk>/review/', pending_change_review,  name='pending_change_review'),
]
