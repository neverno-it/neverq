from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    # Live display board (no login needed - public screen)
    path('display-board/',                views.display_board,        name='display_board'),
    path('display-board/<int:company_id>/', views.display_board,     name='display_board_company'),
    path('display-board/feed/',             views.display_board_feed,  name='display_board_feed'),
    # Customer ordering
    path('menu/',                         views.menu,                 name='menu'),
    path('checkout/',                     views.checkout,             name='checkout'),
    path('place/',                        views.place_order,          name='place_order'),
    path('razorpay/initiate/',            views.razorpay_initiate,    name='razorpay_initiate'),
    path('razorpay/verify/',              views.razorpay_verify,      name='razorpay_verify'),
    path('razorpay/cancel/',              views.razorpay_cancel,      name='razorpay_cancel'),
    path('razorpay/webhook/',             views.razorpay_webhook,     name='razorpay_webhook'),
    path('phonepe/initiate/',             views.phonepe_initiate,     name='phonepe_initiate'),
    path('phonepe/callback/',             views.phonepe_callback,     name='phonepe_callback'),
    path('confirmation/<int:pk>/',        views.order_confirmation,   name='order_confirmation'),
    path('history/',                      views.order_history,        name='order_history'),
    path('history/status-feed/',          views.customer_order_history_feed, name='customer_order_history_feed'),
    path('<int:pk>/status-feed/',         views.customer_order_status_feed, name='customer_order_status_feed'),
    path('<int:pk>/',                     views.order_detail,         name='order_detail'),
    path('<int:pk>/cancel/',              views.cancel_order,         name='cancel_order'),
    path('<int:pk>/edit/',                views.edit_order,           name='edit_order'),
    path('<int:pk>/reorder/',             views.reorder_order,        name='reorder_order'),
    # Customer cafe selection (web orders)
    path('set-cafe/',                     views.set_web_cafe,         name='set_web_cafe'),
    # Coupon
    path('apply-coupon/',                  views.apply_coupon,         name='apply_coupon'),
    # KOT
    path('<int:pk>/kot/',                  views.kot_data,             name='kot_data'),
    path('<int:pk>/kot/print/',            views.kot_print_html,       name='kot_print_html'),
    path('poll/new/',                      views.new_orders_poll,      name='new_orders_poll'),
    path('pickup-scan/',                   views.pickup_scan_terminal, name='pickup_scan_terminal'),
    path('pickup-item/<int:item_id>/collect/', views.pickup_mark_collected, name='pickup_mark_collected'),
    path('pickup-ticket/<int:ticket_id>/collect/', views.pickup_ticket_mark_collected, name='pickup_ticket_mark_collected'),
    # Self-kiosk (company-scoped, no login)
    path('kiosk/<int:company_id>/',                   views.kiosk_home,         name='kiosk_home'),
    path('kiosk/<int:company_id>/reset/',             views.kiosk_reset,        name='kiosk_reset'),
    path('kiosk/<int:company_id>/cart/',              views.kiosk_cart,         name='kiosk_cart'),
    path('kiosk/<int:company_id>/cart/update/',       views.kiosk_cart_update,   name='kiosk_cart_update'),
    path('kiosk/<int:company_id>/place/',             views.kiosk_place_order,   name='kiosk_place_order'),
    path('kiosk/<int:company_id>/razorpay/initiate/', views.kiosk_razorpay_initiate, name='kiosk_razorpay_initiate'),
    path('kiosk/<int:company_id>/razorpay/verify/',   views.kiosk_razorpay_verify,   name='kiosk_razorpay_verify'),
    path('kiosk/<int:company_id>/razorpay/cancel/',   views.kiosk_razorpay_cancel,   name='kiosk_razorpay_cancel'),
    path('kiosk/<int:company_id>/confirm/<int:pk>/',  views.kiosk_confirmation,  name='kiosk_confirmation'),
    path('kiosk/<int:company_id>/receipt/<int:pk>/',  views.kiosk_receipt,       name='kiosk_receipt'),
    # Customer self-scan terminal (mounted at each counter — no login needed)
    path('self-scan/<int:company_id>/',               views.customer_self_scan,  name='customer_self_scan'),
    # Kitchen display screen (public — no login — read-only)
    path('kitchen/',                              views.kitchen_display,       name='kitchen_display'),
    path('kitchen/<int:company_id>/',             views.kitchen_display,       name='kitchen_display_company'),
    path('kitchen/feed/',                         views.kitchen_display_feed,  name='kitchen_display_feed'),
    # Delivery-mode: confirmation dashboard & packet labels
    path('delivery/confirmation/',                    views.delivery_confirmation_list, name='delivery_confirmation_list'),
    path('delivery/mark-delivered/',                  views.delivery_mark_delivered,    name='delivery_mark_delivered'),
    path('delivery/packet-labels/',                   views.delivery_packet_labels,     name='delivery_packet_labels'),
]
