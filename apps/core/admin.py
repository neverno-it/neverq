from django.contrib import admin
from .models import State, City, Location, Company, Building, Coupon, Notification, StaticPage, RoleMenuConfig


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ['name', 'state', 'is_active', 'is_deleted']
    list_filter = ['state', 'is_active', 'is_deleted']
    search_fields = ['name', 'state__name']
    ordering = ['state__name', 'name']


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    list_filter = ['is_active']


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'store_status', 'bill_company', 'is_active']
    list_filter = ['is_active', 'store_status', 'bill_company']
    search_fields = ['name', 'phone']


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'location', 'is_active']
    list_filter = ['company', 'is_active']
    search_fields = ['name']


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ['code', 'discount_type', 'discount_value', 'company',
                    'used_count', 'usage_limit', 'is_active']
    list_filter = ['discount_type', 'is_active', 'company']
    search_fields = ['code', 'description']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'notif_type', 'company', 'is_read', 'created_at']
    list_filter = ['notif_type', 'is_read', 'company']
    search_fields = ['title', 'message']


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    list_display = ['title', 'slug', 'is_active', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['title', 'slug']
    prepopulated_fields = {'slug': ('title',)}


@admin.register(RoleMenuConfig)
class RoleMenuConfigAdmin(admin.ModelAdmin):
    list_display = ['role', 'visible_keys']