from django.contrib import admin
from .models import POSProduct, POSOrder, POSOrderItem


@admin.register(POSProduct)
class POSProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'price', 'is_active')
    list_filter = ('is_active', 'company')
    search_fields = ('name',)
    list_editable = ('price', 'is_active')


class POSOrderItemInline(admin.TabularInline):
    model = POSOrderItem
    extra = 0
    readonly_fields = ('product_name', 'price', 'qty', 'amount')


@admin.register(POSOrder)
class POSOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer_name', 'company', 'total_amount', 'payment_type', 'created_at')
    list_filter = ('payment_type', 'company', 'created_at')
    search_fields = ('order_number', 'customer_name', 'customer_phone')
    readonly_fields = ('order_number', 'created_at')
    inlines = [POSOrderItemInline]
