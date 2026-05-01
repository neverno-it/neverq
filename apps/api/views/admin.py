from django.db.models import Sum, Count, Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.api.authentication import NeverQJWTAuthentication
from apps.api.permissions import IsAdminStaff, IsSuperAdmin
from apps.api.serializers import (
    OrderListSerializer, OrderDetailSerializer,
    ProductSerializer, CategorySerializer,
    StaffUserSerializer, CouponSerializer,
)
from apps.orders.models import Order, OrderStatus, OrderStatusChoices
from apps.menu.models import Category, Product
from apps.accounts.models import StaffUser, Customer
from apps.core.models import Coupon, Company
from apps.pos.models import POSOrder


class AdminDashboardView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsAdminStaff]

    def get(self, request):
        user = request.user
        company = user.company
        today = timezone.localdate()

        web_qs = Order.objects.filter(is_deleted=False)
        pos_qs = POSOrder.objects.filter(is_deleted=False)

        if company:
            web_qs = web_qs.filter(company=company)
            pos_qs = pos_qs.filter(company=company)

        today_web = web_qs.filter(created_at__date=today)
        today_pos = pos_qs.filter(created_at__date=today)

        stats = {
            'today_web_orders': today_web.count(),
            'today_web_revenue': str(today_web.aggregate(t=Sum('total_amount'))['t'] or 0),
            'today_pos_orders': today_pos.count(),
            'today_pos_revenue': str(today_pos.aggregate(t=Sum('total_amount'))['t'] or 0),
            'total_web_orders': web_qs.count(),
            'total_web_revenue': str(web_qs.aggregate(t=Sum('total_amount'))['t'] or 0),
            'pending_orders': web_qs.filter(order_status=OrderStatusChoices.PENDING).count(),
            'active_customers': Customer.objects.filter(
                company=company, is_active=True, is_deleted=False
            ).count() if company else Customer.objects.filter(is_active=True, is_deleted=False).count(),
        }

        # Weekly revenue (last 7 days)
        from datetime import timedelta
        weekly = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            rev = web_qs.filter(created_at__date=day).aggregate(t=Sum('total_amount'))['t'] or 0
            weekly.append({'date': str(day), 'revenue': float(rev)})

        return Response({'stats': stats, 'weekly_revenue': weekly})


class AdminOrderListView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsAdminStaff]

    def get(self, request):
        company = request.user.company
        qs = Order.objects.filter(is_deleted=False).order_by('-created_at')
        if company:
            qs = qs.filter(company=company)

        order_status = request.query_params.get('status')
        if order_status:
            qs = qs.filter(order_status=int(order_status))

        date = request.query_params.get('date')
        if date:
            qs = qs.filter(created_at__date=date)

        return Response(OrderListSerializer(qs[:100], many=True).data)


class AdminOrderDetailView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsAdminStaff]

    def get(self, request, pk):
        company = request.user.company
        qs = Order.objects.prefetch_related('items__product')
        if company:
            qs = qs.filter(company=company)
        try:
            order = qs.get(pk=pk, is_deleted=False)
        except Order.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrderDetailSerializer(order, context={'request': request}).data)


class AdminOrderStatusView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsAdminStaff]

    def patch(self, request, pk):
        company = request.user.company
        qs = Order.objects.filter(is_deleted=False)
        if company:
            qs = qs.filter(company=company)
        try:
            order = qs.get(pk=pk)
        except Order.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('order_status')
        if new_status is None:
            return Response({'detail': 'order_status required.'}, status=status.HTTP_400_BAD_REQUEST)

        order.order_status = int(new_status)
        order.save(update_fields=['order_status', 'updated_at'])
        OrderStatus.objects.create(order=order, status=int(new_status), details='Admin update via app')

        return Response({'order_status': order.order_status, 'status_label': order.status_label})


class AdminCategoryListView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsAdminStaff]

    def get(self, request):
        company = request.user.company
        qs = Category.objects.filter(is_active=True, is_deleted=False)
        if company:
            qs = qs.filter(company=company)
        return Response(CategorySerializer(qs.order_by('sort_order', 'name'), many=True).data)


class AdminProductListView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsAdminStaff]

    def get(self, request):
        company = request.user.company
        qs = Product.objects.filter(is_deleted=False).select_related('category')
        if company:
            qs = qs.filter(company=company)
        category_id = request.query_params.get('category')
        if category_id:
            qs = qs.filter(category_id=category_id)
        return Response(ProductSerializer(qs.order_by('name'), many=True, context={'request': request}).data)


class AdminProductToggleView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsAdminStaff]

    def patch(self, request, pk):
        company = request.user.company
        qs = Product.objects.filter(is_deleted=False)
        if company:
            qs = qs.filter(company=company)
        try:
            product = qs.get(pk=pk)
        except Product.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        product.is_active = not product.is_active
        product.save(update_fields=['is_active'])
        return Response({'id': product.id, 'is_active': product.is_active})


class AdminStaffListView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsAdminStaff]

    def get(self, request):
        company = request.user.company
        qs = StaffUser.objects.filter(is_active=True)
        if company and not request.user.is_superadmin:
            qs = qs.filter(company=company)
        return Response(StaffUserSerializer(qs.order_by('name'), many=True).data)


class AdminCouponListView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsAdminStaff]

    def get(self, request):
        company = request.user.company
        qs = Coupon.objects.filter(is_active=True)
        if company:
            qs = qs.filter(Q(company=company) | Q(company__isnull=True))
        return Response(CouponSerializer(qs.order_by('-created_at'), many=True).data)
