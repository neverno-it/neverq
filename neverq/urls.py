from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.accounts import views as account_views

urlpatterns = [
    path('admin/', admin.site.urls),
    # Mobile REST API
    path('api/v1/', include('apps.api.urls', namespace='api')),
    # Legacy Google app-login (kept for backward compat)
    path('api/auth/google/app-login/', account_views.google_app_login, name='api_google_app_login'),
    path('', include('apps.core.urls', namespace='core')),
    path('auth/', include('apps.accounts.urls', namespace='accounts')),
    path('dashboard/', include('apps.accounts.dashboard_urls', namespace='dashboard')),
    path('menu/', include('apps.menu.urls', namespace='menu')),
    path('orders/', include('apps.orders.urls', namespace='orders')),
    path('pos/', include('apps.pos.urls', namespace='pos')),
    path('reviews/', include('apps.reviews.urls', namespace='reviews')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

admin.site.site_header = 'NeverQ Admin'
admin.site.site_title = 'NeverQ'
admin.site.index_title = 'Corporate Cafeteria Management'
