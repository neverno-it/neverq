from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.api.authentication import NeverQJWTAuthentication
from apps.api.permissions import IsPOSStaff
from apps.api.serializers import POSProductSerializer, POSOrderCreateSerializer, POSOrderSerializer
from apps.pos.models import POSProduct, POSOrder, POSOrderItem
from apps.menu.models import Product


class POSProductListView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsPOSStaff]

    def get(self, request):
        company = request.user.company
        # Return both dedicated POS products and menu products marked as POS-active
        pos_products = POSProduct.objects.filter(
            company=company, is_active=True, is_deleted=False
        ).order_by('name')

        menu_products = Product.objects.filter(
            company=company, is_active=True, is_deleted=False, is_pos_active=True
        ).order_by('name')

        pos_data = POSProductSerializer(pos_products, many=True).data
        menu_data = [
            {'id': f'menu_{p.id}', 'name': p.name, 'price': str(p.price)}
            for p in menu_products
        ]

        return Response({'pos_products': pos_data, 'menu_products': menu_data})


class POSOrderCreateView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsPOSStaff]

    def post(self, request):
        ser = POSOrderCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        data = ser.validated_data
        company = request.user.company

        payment_type = data['payment_type']
        items_data = data['items']

        base_amount = sum(
            Decimal(str(i['price'])) * i['qty'] for i in items_data
        )

        # Card fee
        card_fee = Decimal('0')
        if payment_type == POSOrder.PAYMENT_CARD:
            fee_pct = company.pos_card_fee_percent or Decimal('0')
            card_fee = (base_amount * fee_pct / Decimal('100')).quantize(Decimal('0.01'))

        total_amount = base_amount + card_fee

        order = POSOrder.objects.create(
            company=company,
            customer_name=data.get('customer_name', 'Walk-in Customer'),
            customer_phone=data.get('customer_phone', ''),
            customer_type=data.get('customer_type', 'visitor'),
            payment_type=payment_type,
            base_amount=base_amount,
            card_fee_amount=card_fee,
            total_amount=total_amount,
        )

        for item in items_data:
            amt = Decimal(str(item['price'])) * item['qty']
            POSOrderItem.objects.create(
                company=company,
                order=order,
                product_name=item['product_name'],
                price=item['price'],
                qty=item['qty'],
                amount=amt,
            )

        return Response(
            POSOrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class POSOrderListView(APIView):
    authentication_classes = [NeverQJWTAuthentication]
    permission_classes = [IsPOSStaff]

    def get(self, request):
        from django.utils import timezone
        company = request.user.company
        today = timezone.localdate()
        orders = (
            POSOrder.objects
            .filter(company=company, is_deleted=False, created_at__date=today)
            .prefetch_related('items')
            .order_by('-created_at')
        )
        return Response(POSOrderSerializer(orders, many=True).data)
