from django.contrib import admin
from django.utils.safestring import mark_safe

from . import models as m


class VendorOrderInline(admin.TabularInline):
    model = m.VendorOrder
    fk_name = "order"
    readonly_fields = ("total_amount", "total_items", "vendor", "vendor_order_id", "currency", "order_date", "status")
    can_delete = False

    def has_add_permission(self, request, obj):
        return False


@admin.register(m.Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "office", "created_by", "status")
    inlines = (VendorOrderInline,)

    @admin.display(description="Company")
    def company(self, obj):
        return obj.office.company


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
