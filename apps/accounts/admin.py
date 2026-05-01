from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import StaffUser, Customer, WebCookie, StaffAccess


@admin.register(StaffUser)
class StaffUserAdmin(BaseUserAdmin):
    list_display = ['email', 'name', 'role', 'company', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active', 'company']
    search_fields = ['email', 'name', 'phone']
    ordering = ['name']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal', {'fields': ('name', 'phone', 'avatar')}),
        ('Role', {'fields': ('role', 'company')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'name', 'password1', 'password2', 'role', 'company')}),
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'phone', 'company', 'building', 'is_active', 'created_at']
    list_filter = ['company', 'is_active', 'is_deleted']
    search_fields = ['name', 'email', 'phone']
    raw_id_fields = ['company', 'building']


@admin.register(WebCookie)
class WebCookieAdmin(admin.ModelAdmin):
    list_display = ['cookie_id', 'customer', 'delivery_type', 'created_at']
    search_fields = ['cookie_id']


@admin.register(StaffAccess)
class StaffAccessAdmin(admin.ModelAdmin):
    list_display = ['user', 'landing_page', 'visible_keys']
    raw_id_fields = ['user']
