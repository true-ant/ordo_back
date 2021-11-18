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
    fields = ("vendor", "invoice", "order_date", "total_amount", "total_items", "currency", "status")
    readonly_fields = fields
    inlines = (VendorOrderProductInline,)

    def invoice(self, obj):
        return mark_safe("<a href='{}'> {} </a>".format(obj.invoice_link, obj.vendor_order_id))


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


class ProductImageInline(ReadOnlyAdminMixin, admin.TabularInline):
    model = m.ProductImage
    readonly_fields = (
        "image_preview",
        "image",
    )

    def image_preview(self, obj):
        return mark_safe("<img src='{}'  width='30' height='30' />".format(obj.image))

    image_preview.short_description = "Preview"


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
    )
    search_fields = (
        "product_id",
        "name",
        "tags__keyword",
    )
    list_filter = (
        "vendor",
        "category",
    )
    inlines = (ProductImageInline,)

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


@admin.register(m.Keyword)
class KeywordAdmin(admin.ModelAdmin):
    search_fields = ("keyword",)


@admin.register(m.OfficeKeyword)
class OfficeKeywordAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_display = (
        "keyword",
        "office",
        "vendor",
        "task_status",
    )
    search_fields = ("keyword__keyword",)


@admin.register(m.OfficeProduct)
class OfficeProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product_id",
        "product_name",
        "product_vendor",
        "product_category",
        "price",
        "is_favorite",
        "is_inventory",
    )
    search_fields = (
        "product__product_id",
        "product__name",
        "product__tags__keyword",
    )

    list_filter = (
        "is_inventory",
        "is_favorite",
        "product__vendor",
        "product__category",
    )

    @admin.display(description="Product ID")
    def product_id(self, obj):
        return obj.product.product_id

    @admin.display(description="Product Name")
    def product_name(self, obj):
        return obj.product.name

    @admin.display(description="Vendor")
    def product_vendor(self, obj):
        return obj.product.vendor

    @admin.display(description="Product Category")
    def product_category(self, obj):
        return obj.product.category
