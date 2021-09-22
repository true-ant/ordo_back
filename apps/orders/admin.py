from django.contrib import admin

from . import models as m


class VendorOrderInline(admin.TabularInline):
    model = m.VendorOrder
    fk_name = "order"
    readonly_fields = ("total_amount", "total_items", "vendor", "vendor_order_id", "currency", "order_date", "status")
    can_delete = False


@admin.register(m.Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = (VendorOrderInline,)


@admin.register(m.Product)
class ProductAdmin(admin.ModelAdmin):
    pass
