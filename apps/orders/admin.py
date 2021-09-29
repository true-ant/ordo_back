from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Q
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


class OrderVendorFilter(SimpleListFilter):
    title = "Vendor"
    parameter_name = "vendors"

    def lookups(self, request, model_admin):
        return m.Vendor.objects.values_list("slug", "name")

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(vendor_orders__vendor__slug=value)


@admin.register(m.Order)
class OrderAdmin(NestedModelAdmin):
    list_display = ("id", "company", "office", "vendors", "order_date", "status")
    list_filter = (
        "status",
        OrderVendorFilter,
    )
    inlines = (VendorOrderInline,)

    @admin.display(description="Company")
    def company(self, obj):
        return obj.office.company

    @admin.display(description="Vendors")
    def vendors(self, objs):
        return ", ".join([vendor_order.vendor.name for vendor_order in objs.vendor_orders.all()])


class ProductPriceFilter(SimpleListFilter):
    title = "Price Range"
    parameter_name = "price"

    def lookups(self, request, model_admin):
        return ("_100", "0 - 100"), ("100_200", "100 - 200"), ("200_300", "200 - 300"), ("300_", "300 +")

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        if value == "_100":
            return queryset.filter(price__lte=100)
        elif value == "100_200":
            return queryset.filter(Q(price__gt=100) & Q(price__lte=200))
        elif value == "200_300":
            return queryset.filter(Q(price__gt=200) & Q(price__lte=300))
        else:
            return queryset.filter(price__gt=300)


@admin.register(m.ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("__str__", "name", "parent")


@admin.register(m.Product)
class ProductAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display = (
        "id",
        "product_thumb",
        "product_id",
        "name",
        "vendor",
        "category",
        "get_url",
        "price",
    )
    search_fields = (
        "product_id",
        "name",
    )
    list_filter = (
        "vendor",
        ProductPriceFilter,
    )

    @admin.display(description="url")
    def get_url(self, obj):
        return mark_safe(f"<a target='_blank' href={obj.url}>Link</a>")

    @admin.display(description="Image")
    def product_thumb(self, obj):
        image = obj.images.first()
        if image:
            return mark_safe("<img src='{}'  width='30' height='30' />".format(image.image))
        else:
            return "No Image Found"
