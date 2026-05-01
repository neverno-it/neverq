from django.urls import path
from . import views

app_name = 'menu'

urlpatterns = [
    # Customer-facing
    path('', views.customer_menu, name='menu'),
    path('category/<slug:slug>/', views.category_detail, name='category_detail'),
    path('offering/<slug:slug>/', views.offering_detail, name='offering_detail'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:product_id>/', views.cart_add, name='cart_add'),
    path('cart/remove/<int:product_id>/', views.cart_remove, name='cart_remove'),
    path('cart/update/<int:product_id>/', views.cart_update_qty, name='cart_update_qty'),
]
