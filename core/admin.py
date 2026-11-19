from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Customer, Service, ServicePrice, PriceAuditLog,
    Voucher, Order, OrderItem, PaymentTransaction, ShiftReconciliation
)


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ('username', 'account_id', 'full_name', 'role', 'account_status', 'is_active')
    list_filter = ('role', 'account_status')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Thông tin phân quyền nội bộ', {'fields': ('full_name', 'role', 'account_status')}),
    )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('is_quang_tri_local', 'subtotal')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'channel', 'visit_date', 'total_quantity', 'total_amount', 'order_status', 'ticket_status')
    list_filter = ('channel', 'order_status', 'ticket_status', 'visit_date')
    search_fields = ('order_id', 'ticket_id', 'qr_code', 'customer__phone', 'customer__customer_name')
    inlines = [OrderItemInline]


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('service_id', 'service_name', 'daily_capacity', 'service_status')
    list_filter = ('service_status',)


@admin.register(ServicePrice)
class ServicePriceAdmin(admin.ModelAdmin):
    list_display = ('service', 'ticket_type', 'day_type', 'price', 'quang_tri_price', 'updated_at')
    list_filter = ('service', 'ticket_type', 'day_type')


admin.site.register(Customer)
admin.site.register(PriceAuditLog)
admin.site.register(Voucher)
admin.site.register(PaymentTransaction)
admin.site.register(ShiftReconciliation)