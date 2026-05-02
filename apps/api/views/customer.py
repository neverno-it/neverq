from decimal import Decimal
from django.utils import timezone
from django.db.models import Count, Q
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
    BannerSerializer, OfferingSerializer, OfferSerializer, CafeSerializer,
)
from apps.menu.models import Category, Product, Advertise, Offering, Offer, OfferUsage, Cafe
from apps.menu.views import (
    _attach_display_prices,
    _mark_free_meal_products,
    _product_is_visible_for_customer,
    _resolve_customer_cafe,
)
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
        building = getattr(customer, 'building', None)

        query = (request.query_params.get('q') or '').strip()
        food_pref = (request.query_params.get('food') or '').strip().lower()
        offering_filter = (request.query_params.get('offering') or '').strip()
        calorie_max = None
        try:
            calorie_max_raw = (request.query_params.get('calorie_max') or '').strip()
            calorie_max = int(calorie_max_raw) if calorie_max_raw else None
        except (TypeError, ValueError):
            calorie_max = None

        categories = (
            Category.objects
            .filter(companies=company, is_deleted=False)
            .prefetch_related('schedules', 'company_statuses')
            .distinct()
            .order_by('position_order', 'name')
        )
        visible_categories = [category for category in categories if category.is_active_now(company)]

        adverts = [
            ad for ad in Advertise.objects.filter(
                is_active=True,
                status=Advertise.STATUS_APPROVED,
            ).filter(companies=company).distinct().prefetch_related('holiday_schedules').order_by('position_order')
            if ad.is_live
        ]

        offerings_qs = (
            Offering.objects
            .filter(company=company, is_deleted=False, is_active=True)
            .prefetch_related('schedules')
            .order_by('position_order', 'name')
        )
        offerings = [offering for offering in offerings_qs if offering.is_active_now()]
        selected_offering = None
        if offering_filter:
            selected_offering = next(
                (offering for offering in offerings if str(offering.pk) == offering_filter or offering.slug == offering_filter),
                None,
            )

        offer_qs = (
            Offer.objects
            .filter(company=company, is_deleted=False)
            .select_related('product', 'cafe')
            .prefetch_related('products')
            .order_by('-created_at')
        )
        all_live_offers = [offer for offer in offer_qs if offer.is_live]
        one_use_offer_types = {
            Offer.TYPE_BOGO,
            Offer.TYPE_FREE,
            Offer.TYPE_PERCENT,
            Offer.TYPE_FLAT,
            Offer.TYPE_CART,
        }
        used_offer_ids = set(
            OfferUsage.objects.filter(
                customer=customer,
                offer__in=all_live_offers,
                used_on=timezone.localdate(),
            ).values_list('offer_id', flat=True)
        )
        live_offers = [
            offer for offer in all_live_offers
            if offer.offer_type not in one_use_offer_types or offer.pk not in used_offer_ids
        ]

        base_products = (
            Product.objects
            .filter(company=company, is_active=True, is_deleted=False)
            .select_related('category', 'offering')
            .prefetch_related('food_type', 'category__company_statuses')
        )
        if query:
            base_products = base_products.filter(
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(code__icontains=query)
                | Q(category__name__icontains=query)
                | Q(offering__name__icontains=query)
            )
        if selected_offering:
            base_products = base_products.filter(offering=selected_offering)

        products = []
        for product in base_products.order_by('category__position_order', 'category__name', 'position_order', 'name'):
            if _product_is_visible_for_customer(product, company, food_pref):
                if calorie_max is None or (product.calories is not None and product.calories <= calorie_max):
                    products.append(product)

        pinned_featured_products = []
        fallback_featured_products = []
        featured_qs = (
            base_products
            .annotate(order_count=Count('orderitem'))
            .order_by('-rating', '-order_count', 'category__position_order', 'category__name', 'position_order', 'name')
        )
        for product in featured_qs:
            if len(pinned_featured_products) >= 8 and len(fallback_featured_products) >= 8:
                break
            if _product_is_visible_for_customer(product, company, food_pref):
                if calorie_max is None or (product.calories is not None and product.calories <= calorie_max):
                    if product.featured_in_web:
                        pinned_featured_products.append(product)
                    if len(fallback_featured_products) < 8:
                        fallback_featured_products.append(product)
        featured_products = pinned_featured_products[:8] if pinned_featured_products else fallback_featured_products

        selected_cafe = _resolve_customer_cafe(customer, company, request=None)
        _attach_display_prices(products, company, building=building, cafe=selected_cafe, used_offer_ids=used_offer_ids)
        _attach_display_prices(featured_products, company, building=building, cafe=selected_cafe, used_offer_ids=used_offer_ids)
        _mark_free_meal_products(products, company)
        _mark_free_meal_products(featured_products, company)

        recent_orders = (
            customer.orders
            .filter(is_deleted=False)
            .prefetch_related('items__product')
            .order_by('-created_at')[:3]
        )

        cafes = (
            Cafe.objects
            .filter(company=company, is_active=True, is_deleted=False)
            .select_related('building')
            .order_by('name')
        )

        return Response({
            'categories': CategorySerializer(visible_categories, many=True, context={'request': request}).data,
            'products': ProductSerializer(products, many=True, context={'request': request}).data,
            'featured_products': ProductSerializer(featured_products, many=True, context={'request': request}).data,
            'banners': BannerSerializer(adverts, many=True, context={'request': request}).data,
            'offerings': OfferingSerializer(offerings, many=True, context={'request': request}).data,
            'offers': OfferSerializer(live_offers[:6], many=True, context={'request': request}).data,
            'recent_orders': OrderListSerializer(recent_orders, many=True).data,
            'cafes': CafeSerializer(cafes, many=True).data,
            'selected_cafe_id': selected_cafe.pk if selected_cafe else None,
            'is_store_open': company.is_store_open,
            'ordering_status_message': company.ordering_status_message,
            'store_name': company.name,
            'order_window_label': company.order_window_label,
        })


class ProductDetailView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsCustomer]

    def get(self, request, pk):
        customer = request.user
        company = customer.company
        try:
            product = (
                Product.objects
                .select_related('category', 'offering')
                .prefetch_related('food_type', 'category__company_statuses')
                .get(pk=pk, company=company, is_active=True, is_deleted=False)
            )
        except Product.DoesNotExist:
            return Response({'detail': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)

        used_offer_ids = set(
            OfferUsage.objects.filter(customer=customer, used_on=timezone.localdate())
            .values_list('offer_id', flat=True)
        )
        selected_cafe = _resolve_customer_cafe(customer, company, request=None)
        _attach_display_prices(
            [product],
            company,
            building=getattr(customer, 'building', None),
            cafe=selected_cafe,
            used_offer_ids=used_offer_ids,
        )
        _mark_free_meal_products([product], company)

        similar = [
            candidate for candidate in (
                Product.objects
                .filter(company=company, category=product.category, is_active=True, is_deleted=False)
                .exclude(pk=product.pk)
                .select_related('category', 'offering')
                .prefetch_related('food_type', 'category__company_statuses')
                .order_by('position_order', 'name')[:8]
            )
            if _product_is_visible_for_customer(candidate, company)
        ]
        _attach_display_prices(
            similar,
            company,
            building=getattr(customer, 'building', None),
            cafe=selected_cafe,
            used_offer_ids=used_offer_ids,
        )
        _mark_free_meal_products(similar, company)

        return Response({
            'product': ProductSerializer(product, context={'request': request}).data,
            'similar_products': ProductSerializer(similar, many=True, context={'request': request}).data,
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
