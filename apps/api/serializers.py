from rest_framework import serializers
from django.conf import settings
from apps.accounts.models import StaffUser, Customer
from apps.core.models import Company, Building, Coupon, Notification
from apps.menu.models import Category, Product, Offering
from apps.orders.models import Order, OrderItem, OrderStatusChoices
from apps.pos.models import POSProduct, POSOrder, POSOrderItem
from apps.reviews.models import Review
from .models import CartItem, Cart


# ── Helpers ───────────────────────────────────────────────────────────────────

def abs_url(request, relative_url):
    if not relative_url:
        return None
    if str(relative_url).startswith('http'):
        return str(relative_url)
    if request:
        return request.build_absolute_uri(f'{settings.MEDIA_URL}{relative_url}')
    return f'{settings.MEDIA_URL}{relative_url}'


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class FCMTokenSerializer(serializers.Serializer):
    token = serializers.CharField()
    platform = serializers.ChoiceField(choices=['android', 'ios'], default='android')


# ── Company ───────────────────────────────────────────────────────────────────

class CompanySerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    is_store_open = serializers.BooleanField(read_only=True)
    ordering_status_message = serializers.CharField(read_only=True)

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'logo_url', 'store_status', 'is_store_open',
            'ordering_status_message', 'cod_payment', 'online_payment',
            'monthly_payment', 'order_window_label', 'fulfillment_mode',
        ]

    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo:
            return abs_url(request, obj.logo)
        return None


class BuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = ['id', 'name']


# ── Menu ──────────────────────────────────────────────────────────────────────

class OfferingSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Offering
        fields = ['id', 'name', 'image_url', 'is_active']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image:
            return abs_url(request, obj.image)
        return None


class CategorySerializer(serializers.ModelSerializer):
    sort_order = serializers.IntegerField(source='position_order', read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'parent_id', 'sort_order']


class ProductSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    is_veg = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'price', 'description',
            'image_url', 'category_id', 'category_name',
            'is_veg', 'calories', 'is_available',
        ]

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image:
            return abs_url(request, obj.image)
        return None

    def get_is_available(self, obj):
        try:
            return obj.is_available_now()
        except Exception:
            return obj.is_active

    def get_is_veg(self, obj):
        category = getattr(obj, 'category', None)
        if category is not None:
            return bool(getattr(category, 'is_veg', False))
        return obj.food_type.filter(name__icontains='veg').exists()


# ── Cart ──────────────────────────────────────────────────────────────────────

class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True)
    line_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_id', 'qty', 'line_total']


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True, source='items.filter(is_deleted=False)')
    subtotal = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'items', 'subtotal', 'item_count']

    def get_items(self, obj):
        qs = obj.items.filter(is_deleted=False)
        return CartItemSerializer(qs, many=True, context=self.context).data

    def get_subtotal(self, obj):
        total = sum(
            item.line_total
            for item in obj.items.filter(is_deleted=False).select_related('product')
        )
        return str(total)


# ── Orders ────────────────────────────────────────────────────────────────────

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['id', 'product_name', 'qty', 'price', 'line_total', 'image_url']

    def get_product_name(self, obj):
        if obj.product:
            return obj.product.name
        return 'Item'

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.product and obj.product.image:
            return abs_url(request, obj.product.image)
        if obj.image_snapshot:
            return abs_url(request, obj.image_snapshot)
        return None


class OrderListSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(read_only=True)
    status_color = serializers.CharField(read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'order_status', 'status_label', 'status_color',
            'total_amount', 'payment_mode', 'created_at', 'item_count',
        ]

    def get_item_count(self, obj):
        return obj.items.filter(is_deleted=False).count()


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_label = serializers.CharField(read_only=True)
    status_color = serializers.CharField(read_only=True)
    display_customer_name = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'order_status', 'status_label', 'status_color',
            'subtotal', 'coupon_discount', 'wallet_used', 'total_amount',
            'payment_mode', 'payment_status', 'order_type', 'created_at',
            'display_customer_name', 'items',
        ]


# ── Kitchen ───────────────────────────────────────────────────────────────────

class KitchenOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_label = serializers.CharField(read_only=True)
    display_customer_name = serializers.CharField(read_only=True)
    display_customer_phone = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'order_status', 'status_label',
            'total_amount', 'payment_mode', 'created_at',
            'display_customer_name', 'display_customer_phone', 'items',
        ]


# ── POS ───────────────────────────────────────────────────────────────────────

class POSProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = POSProduct
        fields = ['id', 'name', 'price']


class POSOrderItemInputSerializer(serializers.Serializer):
    product_name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    qty = serializers.IntegerField(min_value=1)


class POSOrderCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(default='Walk-in Customer')
    customer_phone = serializers.CharField(required=False, allow_blank=True)
    customer_type = serializers.ChoiceField(
        choices=['staff', 'visitor', 'room_service'], default='visitor'
    )
    payment_type = serializers.ChoiceField(choices=[1, 2, 3])
    items = POSOrderItemInputSerializer(many=True)


class POSOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = POSOrderItem
        fields = ['id', 'product_name', 'price', 'qty', 'amount']


class POSOrderSerializer(serializers.ModelSerializer):
    items = POSOrderItemSerializer(many=True, read_only=True)
    payment_label = serializers.SerializerMethodField()

    class Meta:
        model = POSOrder
        fields = [
            'id', 'order_number', 'customer_name', 'customer_phone',
            'customer_type', 'base_amount', 'card_fee_amount', 'total_amount',
            'payment_type', 'payment_label', 'created_at', 'items',
        ]

    def get_payment_label(self, obj):
        return obj.get_payment_type_display()


# ── Reviews ───────────────────────────────────────────────────────────────────

class ReviewSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'rating', 'details', 'customer_name', 'created_at']
        read_only_fields = ['id', 'customer_name', 'created_at']


# ── Customer Profile ─────────────────────────────────────────────────────────

class CustomerProfileSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'email', 'phone', 'company_id', 'company_name',
            'wallet_balance', 'royalty_points', 'meal_benefit',
        ]
        read_only_fields = ['id', 'email', 'company_id', 'company_name', 'wallet_balance', 'royalty_points']


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'notif_type', 'title', 'message', 'is_read', 'created_at']


# ── Admin Dashboard ───────────────────────────────────────────────────────────

class StaffUserSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    role_label = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = StaffUser
        fields = [
            'id', 'name', 'email', 'phone', 'role', 'role_label',
            'company_id', 'company_name', 'is_active',
        ]
        read_only_fields = ['id']


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'description', 'discount_type', 'discount_value',
            'min_order', 'max_discount', 'usage_limit', 'used_count',
            'valid_from', 'valid_to', 'is_active',
        ]
