from django.contrib import admin
from .models import Location, Business, MenuItem


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'address', 'is_active', 'created_at')
    list_filter = ('city', 'is_active')
    search_fields = ('name', 'city', 'address')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'owner', 'category', 'is_open', 'avg_prep_minutes', 'display_order')
    list_filter = ('location', 'category', 'is_open')
    search_fields = ('name', 'location__name', 'owner__username')


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'price', 'is_veg', 'is_available')
    list_filter = ('business__location', 'business', 'is_veg', 'is_available')
    search_fields = ('name', 'business__name', 'description')
