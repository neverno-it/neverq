from django.contrib import admin
from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('customer', 'rating', 'order', 'is_active', 'created_at')
    list_filter = ('is_active', 'rating')
    search_fields = ('customer__name', 'details')
    readonly_fields = ('created_at',)
