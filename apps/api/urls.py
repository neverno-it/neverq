from django.urls import path
from apps.api.views.auth import LoginView, TokenRefreshView, LogoutView, FCMTokenView, GoogleLoginView
from apps.api.views.customer import (
    CustomerProfileView, StoreInfoView, MenuView, ProductDetailView,
    CartView, CartClearView, CouponApplyView, CheckoutView,
    OrderListView, OrderDetailView, ReviewCreateView, NotificationsView,
)
from apps.api.views.kitchen import KitchenOrderListView, KitchenOrderStatusView
from apps.api.views.pos import POSProductListView, POSOrderCreateView, POSOrderListView
from apps.api.views.admin import (
    AdminDashboardView, AdminOrderListView, AdminOrderDetailView, AdminOrderStatusView,
    AdminCategoryListView, AdminProductListView, AdminProductToggleView,
    AdminStaffListView, AdminCouponListView,
)

app_name = 'api'

urlpatterns = [
    # ── Auth ─────────────────────────────────────────────────────────────────
    path('auth/login/',         LoginView.as_view(),        name='login'),
    path('auth/google/',        GoogleLoginView.as_view(),  name='google_login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/logout/',        LogoutView.as_view(),       name='logout'),
    path('auth/fcm-token/',     FCMTokenView.as_view(),     name='fcm_token'),

    # ── Customer ──────────────────────────────────────────────────────────────
    path('customer/profile/',         CustomerProfileView.as_view(), name='customer_profile'),
    path('customer/store/',           StoreInfoView.as_view(),       name='store_info'),
    path('customer/menu/',            MenuView.as_view(),            name='menu'),
    path('customer/products/<int:pk>/', ProductDetailView.as_view(), name='customer_product_detail'),
    path('customer/cart/',            CartView.as_view(),            name='cart'),
    path('customer/cart/clear/',      CartClearView.as_view(),       name='cart_clear'),
    path('customer/coupon/apply/',    CouponApplyView.as_view(),     name='coupon_apply'),
    path('customer/checkout/',        CheckoutView.as_view(),        name='checkout'),
    path('customer/orders/',          OrderListView.as_view(),       name='order_list'),
    path('customer/orders/<int:pk>/', OrderDetailView.as_view(),     name='order_detail'),
    path('customer/reviews/',         ReviewCreateView.as_view(),    name='review_create'),
    path('customer/notifications/',   NotificationsView.as_view(),   name='notifications'),

    # ── Kitchen ───────────────────────────────────────────────────────────────
    path('kitchen/orders/',                     KitchenOrderListView.as_view(),   name='kitchen_orders'),
    path('kitchen/orders/<int:pk>/status/',     KitchenOrderStatusView.as_view(), name='kitchen_order_status'),

    # ── POS ───────────────────────────────────────────────────────────────────
    path('pos/products/',  POSProductListView.as_view(),  name='pos_products'),
    path('pos/orders/',    POSOrderCreateView.as_view(),  name='pos_order_create'),
    path('pos/orders/list/', POSOrderListView.as_view(),  name='pos_order_list'),

    # ── Admin ─────────────────────────────────────────────────────────────────
    path('admin/dashboard/',                    AdminDashboardView.as_view(),     name='admin_dashboard'),
    path('admin/orders/',                       AdminOrderListView.as_view(),     name='admin_orders'),
    path('admin/orders/<int:pk>/',              AdminOrderDetailView.as_view(),   name='admin_order_detail'),
    path('admin/orders/<int:pk>/status/',       AdminOrderStatusView.as_view(),   name='admin_order_status'),
    path('admin/categories/',                   AdminCategoryListView.as_view(),  name='admin_categories'),
    path('admin/products/',                     AdminProductListView.as_view(),   name='admin_products'),
    path('admin/products/<int:pk>/toggle/',     AdminProductToggleView.as_view(), name='admin_product_toggle'),
    path('admin/staff/',                        AdminStaffListView.as_view(),     name='admin_staff'),
    path('admin/coupons/',                      AdminCouponListView.as_view(),    name='admin_coupons'),
]
