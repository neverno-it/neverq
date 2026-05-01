from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Staff / admin auth
    path('login/', views.staff_login, name='login'),
    path('logout/', views.staff_logout, name='logout'),

    # Customer auth
    path('customer/login/', views.customer_login, name='customer_login'),
    path('google/login/', views.google_login_redirect, name='google_login'),
    path('google/callback/', views.google_callback, name='google_callback'),
    path('customer/login/select-account/', views.customer_select_account, name='customer_select_account'),
    path('customer/register/', views.customer_register, name='customer_register'),
    path('customer/register/verify/', views.customer_verify_registration, name='customer_verify_registration'),
    path('customer/register/otp/',    views.customer_otp_verify,           name='customer_otp_verify'),
    path('customer/logout/', views.customer_logout, name='customer_logout'),
    path('customer/profile/', views.customer_profile, name='profile'),
    path('customer/wallet/', views.customer_wallet, name='customer_wallet'),
    path('customer/forgot-password/', views.customer_forgot_password, name='customer_forgot_password'),
    path('customer/change-password/', views.customer_change_password, name='customer_change_password'),

    # AJAX helpers
    path('ajax/buildings/', views.get_buildings, name='get_buildings'),
    # Customer notifications
    path('customer/notifications/', views.customer_notifications, name='customer_notifications'),
    path('customer/notifications/mark-read/', views.customer_notifications_mark_read, name='customer_notifications_mark_read'),
    path('customer/notifications/poll/', views.customer_notifications_poll, name='customer_notifications_poll'),
]
