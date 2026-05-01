from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.api.authentication import NeverQJWTAuthentication
from apps.api.permissions import IsKitchenStaff
from apps.api.serializers import KitchenOrderSerializer
from apps.api.fcm import notify_customer_order_ready
from apps.orders.models import Order, OrderStatus, OrderStatusChoices
from apps.accounts.models import StaffUser
from django.utils import timezone


ALLOWED_TRANSITIONS = {
    OrderStatusChoices.PENDING:   [OrderStatusChoices.CONFIRMED, OrderStatusChoices.CANCELLED],
    OrderStatusChoices.CONFIRMED: [OrderStatusChoices.PREPARING],
    OrderStatusChoices.PREPARING: [OrderStatusChoices.READY],
    OrderStatusChoices.READY:     [OrderStatusChoices.DELIVERED],
}


def _staff_company(staff_user):
    return staff_user.company


class KitchenOrderListView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsKitchenStaff]

    def get(self, request):
        company = _staff_company(request.user)
        active_statuses = [
            OrderStatusChoices.PENDING,
            OrderStatusChoices.CONFIRMED,
            OrderStatusChoices.PREPARING,
            OrderStatusChoices.READY,
        ]
        orders = (
            Order.objects
            .filter(company=company, order_status__in=active_statuses, is_deleted=False)
            .prefetch_related('items__product')
            .order_by('created_at')
        )
        return Response(KitchenOrderSerializer(orders, many=True, context={'request': request}).data)


class KitchenOrderStatusView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsKitchenStaff]

    def patch(self, request, pk):
        company = _staff_company(request.user)
        try:
            order = Order.objects.get(pk=pk, company=company, is_deleted=False)
        except Order.DoesNotExist:
            return Response({'detail': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('order_status')
        if new_status is None:
            return Response({'detail': 'order_status required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_status = int(new_status)
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid status value.'}, status=status.HTTP_400_BAD_REQUEST)

        allowed = ALLOWED_TRANSITIONS.get(order.order_status, [])
        if new_status not in allowed:
            return Response(
                {'detail': f'Cannot transition from {order.status_label} to status {new_status}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = order.order_status
        order.order_status = new_status
        order.save(update_fields=['order_status', 'updated_at'])

        OrderStatus.objects.create(
            order=order,
            status=new_status,
            details=f'Updated via mobile app by {request.user.name}',
        )

        # Notify customer when order is ready
        if new_status == OrderStatusChoices.READY:
            notify_customer_order_ready(order)

        return Response({
            'order_id': order.id,
            'order_number': order.order_number,
            'order_status': order.order_status,
            'status_label': order.status_label,
        })
