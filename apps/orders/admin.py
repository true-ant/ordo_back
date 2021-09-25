from django.contrib import admin
from django.utils.safestring import mark_safe
from nested_admin.nested import NestedModelAdmin, NestedTabularInline

from apps.common.admins import ReadOnlyAdminMixin

from . import models as m


class VendorOrderProductInline(ReadOnlyAdminMixin, NestedTabularInline):
    model = m.VendorOrderProduct
    readonly_fields = (
        "product",
        "unit_price",
        "quantity",
        "total_price",
        "status",
    )

    def total_price(self, obj):
        return obj.quantity * obj.unit_price


class VendorOrderInline(ReadOnlyAdminMixin, NestedTabularInline):
    model = m.VendorOrder
    fk_name = "order"
    readonly_fields = ("vendor", "vendor_order_id", "order_date", "total_amount", "total_items", "currency", "status")
    inlines = (VendorOrderProductInline,)

    def has_add_permission(self, request, obj):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(m.Order)
class OrderAdmin(NestedModelAdmin):
    list_display = ("id", "company", "office", "vendors", "order_date", "status")
    inlines = (VendorOrderInline,)

    @admin.display(description="Company")
    def company(self, obj):
        return obj.office.company

    @admin.display(description="Vendors")
    def vendors(self, objs):
        return ", ".join([vendor_order.vendor.name for vendor_order in objs.vendor_orders.all()])


@admin.register(m.Product)
class ProductAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display = (
        "id",
        "product_thumb",
        "product_id",
        "name",
        "vendor",
        "url",
        "price",
    )

    @admin.display(description="Image")
    def product_thumb(self, obj):
        image = obj.images.first()
        if image:
            return mark_safe("<img src='{}'  width='30' height='30' />".format(image.image))
        else:
            return "No Image Found"
