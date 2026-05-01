from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from apps.accounts.decorators import customer_login_required
from apps.orders.models import Order, OrderStatusChoices
from .models import Review


@customer_login_required
def leave_review(request, order_pk):
    customer = request.current_customer
    order = get_object_or_404(Order, pk=order_pk, customer=customer, is_deleted=False)

    # Only allow review after delivery
    if order.order_status != OrderStatusChoices.DELIVERED:
        messages.warning(request, 'You can only review delivered orders.')
        return redirect('orders:order_detail', pk=order_pk)

    if hasattr(order, 'review'):
        messages.info(request, 'You have already reviewed this order.')
        return redirect('orders:order_detail', pk=order_pk)

    if request.method == 'POST':
        try:
            rating = max(1.0, min(5.0, float(request.POST.get('rating', '5'))))
        except (TypeError, ValueError):
            rating = 5.0
        details = request.POST.get('details', '').strip()
        Review.objects.create(
            customer=customer,
            order=order,
            rating=rating,
            details=details,
        )
        order.review_given = True
        order.save()
        messages.success(request, 'Thank you for your review!')
        return redirect('orders:order_detail', pk=order_pk)

    return render(request, 'reviews/leave_review.html', {
        'order': order,
        'customer': customer,
        'page_title': 'Leave a Review',
    })


@customer_login_required
def my_reviews(request):
    customer = request.current_customer
    reviews = Review.objects.filter(customer=customer, is_deleted=False)
    return render(request, 'reviews/my_reviews.html', {
        'reviews': reviews,
        'customer': customer,
        'page_title': 'My Reviews',
    })
