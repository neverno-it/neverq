from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    path('order/<int:order_pk>/review/', views.leave_review, name='leave_review'),
    path('my/', views.my_reviews, name='my_reviews'),
]
