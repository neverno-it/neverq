from django.contrib import admin
from .models import (
    FoodType, Category, CategoryCompanyStatus, Schedule, Cafe, Product, Advertise, MediaAsset, HolidaySchedule,
    Counter, ProductCounter, Offering, Offer,
)


@admin.register(FoodType)
class FoodTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_active')


class ScheduleInline(admin.TabularInline):
    model = Schedule
    extra = 1
    fields = ('company', 'offering', 'display_day', 'start_time', 'end_time')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'parent', 'cat_type', 'position_order', 'is_active')
    list_filter = ('cat_type', 'is_active', 'icon_type')
    search_fields = ('name', 'slug')
    inlines = [ScheduleInline]
    filter_horizontal = ('companies',)


@admin.register(CategoryCompanyStatus)
class CategoryCompanyStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'category', 'company', 'is_active', 'use_custom_availability')
    list_filter = ('is_active', 'use_custom_availability', 'company')
    search_fields = ('category__name', 'company__name')


@admin.register(Cafe)
class CafeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'company', 'is_active')
    list_filter = ('is_active', 'company')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category', 'company', 'price', 'company_price', 'room_service_extra_percent', 'preparation_time_minutes', 'is_active', 'position_order')
    list_filter = ('is_active', 'company', 'category')
    search_fields = ('name', 'slug', 'code')
    filter_horizontal = ('food_type',)
    list_editable = ('price', 'company_price', 'room_service_extra_percent', 'preparation_time_minutes', 'is_active', 'position_order')


@admin.register(HolidaySchedule)
class HolidayScheduleAdmin(admin.ModelAdmin):
    list_display  = ('id', 'name', 'day', 'month', 'is_active', 'next_occurrence', 'advert_count')
    list_filter   = ('is_active',)
    search_fields = ('name',)
    list_editable = ('is_active',)
    readonly_fields = ('created_at', 'created_by')

    def advert_count(self, obj):
        return obj.adverts.count()
    advert_count.short_description = 'Banners'

    def next_occurrence(self, obj):
        return obj.next_occurrence
    next_occurrence.short_description = 'Next Date'


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display   = ('id', 'name', 'company', 'uploaded_by', 'created_at')
    list_filter    = ('company',)
    search_fields  = ('name',)
    readonly_fields = ('created_at', 'uploaded_by')
    filter_horizontal = ('companies',)


@admin.register(Advertise)
class AdvertiseAdmin(admin.ModelAdmin):
    list_display   = ('id', 'company', 'name', 'status', 'start_date', 'end_date',
                      'position_order', 'is_active', 'created_by')
    list_filter    = ('status', 'is_active', 'company')
    list_editable  = ('position_order', 'is_active', 'status')
    search_fields  = ('name',)
    readonly_fields = ('created_at', 'created_by', 'reviewed_by')
    filter_horizontal = ('companies', 'holiday_schedules')


class ProductCounterInline(admin.TabularInline):
    model = ProductCounter
    extra = 0
    autocomplete_fields = []


@admin.register(Counter)
class CounterAdmin(admin.ModelAdmin):
    list_display   = ('id', 'name', 'code', 'company', 'cafe', 'position_order', 'is_active')
    list_filter    = ('company', 'is_active')
    search_fields  = ('name', 'code')
    list_editable  = ('position_order', 'is_active')


@admin.register(Offering)
class OfferingAdmin(admin.ModelAdmin):
    list_display   = ('id', 'name', 'company', 'available_from', 'available_to', 'position_order', 'is_active')
    list_filter    = ('company', 'is_active')
    search_fields  = ('name',)
    list_editable  = ('position_order', 'is_active')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display   = ('id', 'title', 'company', 'offer_type', 'value', 'product', 'is_active', 'is_deleted', 'created_at')
    list_filter    = ('company', 'offer_type', 'is_active')
    search_fields  = ('title',)
    list_editable  = ('is_active',)
    readonly_fields = ('created_at',)
