from django.urls import path
from . import views

app_name = 'pos'

urlpatterns = [
    path('', views.pos_terminal, name='terminal'),
    path('place-order/', views.pos_place_order, name='place_order'),
    path('receipt/<int:pk>/', views.pos_receipt, name='receipt'),
    path('orders/', views.pos_order_list, name='order_list'),
    path('kot/<int:pk>/',             views.pos_kot_data,        name='kot_data'),
    path('terminal-kot/<int:pk>/',    views.pos_kot_data,        name='terminal_kot_data'),
]