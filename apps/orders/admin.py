from django.contrib import admin
from .models import Order, OrderItem, OrderStatus


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'price', 'qty', 'line_total')


class OrderStatusInline(admin.TabularInline):
    model = OrderStatus
    extra = 0
    readonly_fields = ('status', 'details', 'created_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'company', 'total_amount', 'order_status', 'payment_mode', 'auto_ready_at', 'created_at')
    list_filter = ('order_status', 'payment_mode', 'company', 'created_at')
    search_fields = ('order_number', 'customer__name', 'customer__email')
    readonly_fields = ('order_number', 'created_at', 'updated_at', 'auto_ready_at')
    inlines = [OrderItemInline, OrderStatusInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'counter', 'price', 'qty', 'pickup_code', 'picked_up_at')
    list_filter = ('company', 'counter')
