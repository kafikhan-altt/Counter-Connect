from django.contrib import admin
from .models import Order, VendorOrder, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('item_name', 'unit_price', 'quantity', 'line_total')


class VendorOrderInline(admin.TabularInline):
    model = VendorOrder
    extra = 0
    readonly_fields = ('business', 'status', 'reject_reason', 'subtotal', 'updated_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'pickup_code',
        'customer_name',
        'customer_phone',
        'customer_email',
        'location',
        'order_date',
        'get_status',
        'get_total_amount',
        'created_at'
    )
    list_filter = ('location', 'order_date')
    search_fields = ('pickup_code', 'customer_name', 'customer_phone', 'customer_email', 'public_id')
    readonly_fields = ('public_id', 'order_date', 'created_at', 'get_status', 'get_total_amount')
    inlines = [VendorOrderInline]

    @admin.display(description='Status')
    def get_status(self, obj):
        return obj.status

    @admin.display(description='Total (₹)')
    def get_total_amount(self, obj):
        return f"₹{obj.total_amount}"


@admin.register(VendorOrder)
class VendorOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'business', 'status', 'reject_reason', 'get_subtotal', 'updated_at')
    list_filter = ('status', 'business__location', 'business')
    search_fields = ('order__pickup_code', 'order__customer_name', 'business__name')
    inlines = [OrderItemInline]

    @admin.display(description='Subtotal (₹)')
    def get_subtotal(self, obj):
        return f"₹{obj.subtotal}"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'vendor_order', 'item_name', 'unit_price', 'quantity', 'line_total')
    list_filter = ('vendor_order__business',)
    search_fields = ('item_name', 'vendor_order__order__pickup_code')
