from decimal import Decimal
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.api.authentication import NeverQJWTAuthentication
from apps.api.permissions import IsCustomer
from apps.api.models import Cart, CartItem
from apps.api.serializers import (
    CustomerProfileSerializer, ProductSerializer, CategorySerializer,
    CartItemSerializer, OrderListSerializer, OrderDetailSerializer,
    ReviewSerializer, NotificationSerializer, CompanySerializer,
)
from apps.menu.models import Category, Product
from apps.orders.models import Order, OrderItem, OrderStatusChoices, PaymentModeChoices
from apps.core.models import Coupon, Notification
from apps.reviews.models import Review


class CustomerProfileView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def get(self, request):
        return Response(CustomerProfileSerializer(request.user, context={'request': request}).data)

    def patch(self, request):
        ser = CustomerProfileSerializer(
            request.user, data=request.data, partial=True, context={'request': request}
        )
        if ser.is_valid():
            ser.save()
            return Response(ser.data)
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)


class StoreInfoView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def get(self, request):
        company = request.user.company
        return Response(CompanySerializer(company, context={'request': request}).data)


class MenuView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def get(self, request):
        customer = request.user
        company = customer.company

        categories = (
            Category.objects
            .filter(company=company, is_active=True, is_deleted=False)
            .order_by('sort_order', 'name')
        )

        products = (
            Product.objects
            .filter(company=company, is_active=True, is_deleted=False, is_web_active=True)
            .select_related('category')
            .order_by('category__sort_order', 'sort_order', 'name')
        )

        return Response({
            'categories': CategorySerializer(categories, many=True).data,
            'products': ProductSerializer(products, many=True, context={'request': request}).data,
            'is_store_open': company.is_store_open,
            'ordering_status_message': company.ordering_status_message,
        })


class CartView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def _get_cart(self, customer):
        cart, _ = Cart.objects.get_or_create(
            customer=customer,
            defaults={'company': customer.company},
        )
        return cart

    def get(self, request):
        cart = self._get_cart(request.user)
        items = cart.items.filter(is_deleted=False).select_related('product')
        subtotal = sum(i.line_total for i in items)
        return Response({
            'items': CartItemSerializer(items, many=True, context={'request': request}).data,
            'subtotal': str(subtotal),
            'item_count': items.count(),
        })

    def post(self, request):
        product_id = request.data.get('product_id')
        qty = int(request.data.get('qty', 1))
        if qty < 1:
            return Response({'detail': 'qty must be >= 1.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            product = Product.objects.get(
                pk=product_id,
                company=request.user.company,
                is_active=True,
                is_deleted=False,
            )
        except Product.DoesNotExist:
            return Response({'detail': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)

        cart = self._get_cart(request.user)
        item, created = CartItem.objects.get_or_create(
            cart=cart, product=product,
            defaults={'qty': qty, 'is_deleted': False},
        )
        if not created:
            item.qty = qty
            item.is_deleted = False
            item.save()

        return Response({'detail': 'Cart updated.', 'item_id': item.id})

    def delete(self, request):
        item_id = request.data.get('item_id')
        cart = self._get_cart(request.user)
        CartItem.objects.filter(pk=item_id, cart=cart).delete()
        return Response({'detail': 'Item removed.'})


class CartClearView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def post(self, request):
        try:
            cart = Cart.objects.get(customer=request.user)
            cart.clear()
        except Cart.DoesNotExist:
            pass
        return Response({'detail': 'Cart cleared.'})


class CouponApplyView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def post(self, request):
        code = (request.data.get('code') or '').strip().upper()
        subtotal = Decimal(str(request.data.get('subtotal', 0)))

        try:
            coupon = Coupon.objects.get(
                code__iexact=code,
                is_active=True,
            )
        except Coupon.DoesNotExist:
            return Response({'detail': 'Invalid coupon code.'}, status=status.HTTP_404_NOT_FOUND)

        if not coupon.is_valid:
            return Response({'detail': 'Coupon has expired or is inactive.'}, status=status.HTTP_400_BAD_REQUEST)

        if coupon.company and coupon.company != request.user.company:
            return Response({'detail': 'Coupon not valid for your company.'}, status=status.HTTP_400_BAD_REQUEST)

        discount = coupon.calculate_discount(subtotal)
        return Response({
            'coupon_id': coupon.id,
            'code': coupon.code,
            'discount': str(discount),
            'description': coupon.description,
        })


class CheckoutView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def post(self, request):
        customer = request.user
        company = customer.company

        if not company.is_store_open:
            return Response(
                {'detail': company.ordering_status_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            cart = Cart.objects.get(customer=customer)
        except Cart.DoesNotExist:
            return Response({'detail': 'Cart is empty.'}, status=status.HTTP_400_BAD_REQUEST)

        cart_items = list(cart.items.filter(is_deleted=False).select_related('product'))
        if not cart_items:
            return Response({'detail': 'Cart is empty.'}, status=status.HTTP_400_BAD_REQUEST)

        payment_mode = request.data.get('payment_mode', PaymentModeChoices.ONLINE)
        coupon_id = request.data.get('coupon_id')
        wallet_use = Decimal(str(request.data.get('wallet_use', 0)))

        subtotal = sum(i.line_total for i in cart_items)

        # Coupon
        coupon_discount = Decimal('0')
        if coupon_id:
            try:
                coupon = Coupon.objects.get(pk=coupon_id, is_active=True)
                coupon_discount = coupon.calculate_discount(subtotal)
                coupon.used_count += 1
                coupon.save(update_fields=['used_count'])
            except Coupon.DoesNotExist:
                pass

        # Wallet
        wallet_use = min(wallet_use, customer.wallet_balance, subtotal - coupon_discount)
        wallet_use = max(Decimal('0'), wallet_use)

        total = max(Decimal('0'), subtotal - coupon_discount - wallet_use)

        order = Order.objects.create(
            company=company,
            customer=customer,
            customer_name_snapshot=customer.name,
            customer_phone_snapshot=customer.phone,
            subtotal=subtotal,
            coupon_discount=coupon_discount,
            coupon_id=coupon_id or 0,
            wallet_used=wallet_use,
            total_amount=total,
            my_pay=total,
            payment_mode=payment_mode,
            order_status=OrderStatusChoices.PENDING,
            order_type=0,
        )

        for ci in cart_items:
            OrderItem.objects.create(
                company=company,
                order=order,
                product=ci.product,
                price=ci.product.price,
                unit_price=ci.product.price,
                qty=ci.qty,
            )

        # Deduct wallet
        if wallet_use > 0:
            customer.wallet_balance -= wallet_use
            customer.save(update_fields=['wallet_balance'])

        cart.clear()

        # Send FCM push to kitchen staff
        from apps.api.fcm import notify_kitchen_new_order
        notify_kitchen_new_order(order)

        return Response({
            'order_id': order.id,
            'order_number': order.order_number,
            'total_amount': str(order.total_amount),
        }, status=status.HTTP_201_CREATED)


class OrderListView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def get(self, request):
        orders = (
            Order.objects
            .filter(customer=request.user, is_deleted=False)
            .order_by('-created_at')[:50]
        )
        return Response(OrderListSerializer(orders, many=True).data)


class OrderDetailView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        try:
            order = Order.objects.prefetch_related('items__product').get(
                pk=pk, customer=request.user, is_deleted=False
            )
        except Order.DoesNotExist:
            return Response({'detail': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrderDetailSerializer(order, context={'request': request}).data)


class ReviewCreateView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def post(self, request):
        order_id = request.data.get('order_id')
        try:
            order = Order.objects.get(pk=order_id, customer=request.user, is_deleted=False)
        except Order.DoesNotExist:
            return Response({'detail': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        if order.review_given:
            return Response({'detail': 'Review already submitted.'}, status=status.HTTP_400_BAD_REQUEST)

        ser = ReviewSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        Review.objects.create(
            customer=request.user,
            order=order,
            rating=ser.validated_data['rating'],
            details=ser.validated_data.get('details', ''),
        )
        order.review_given = True
        order.save(update_fields=['review_given'])

        return Response({'detail': 'Review submitted.'}, status=status.HTTP_201_CREATED)


class NotificationsView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def get(self, request):
        notifs = Notification.objects.filter(
            customer=request.user, company=request.user.company
        ).order_by('-created_at')[:30]
        Notification.objects.filter(
            customer=request.user, is_read=False
        ).update(is_read=True)
        return Response(NotificationSerializer(notifs, many=True).data)
