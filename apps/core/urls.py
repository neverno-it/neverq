from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('select-company/', views.select_company, name='select_company'),

    # Static pages
    path('about-us/', views.about_us, name='about_us'),
    path('terms-and-conditions/', views.terms, name='terms'),
    path('privacy-policy/', views.privacy, name='privacy'),
    path('refund-policy/', views.refund, name='refund'),
    path('contact-us/', views.contact_us, name='contact_us'),

    # Notifications
    path('notifications/poll/', views.notifications_poll, name='notifications_poll'),
    path('notifications/mark-read/', views.notification_mark_read, name='notification_mark_read'),
]
