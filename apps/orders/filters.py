from django.db.models import Q
from django_filters import rest_framework as filters

from .models import OfficeProduct, Order, Product, VendorOrderProduct


class OrderFilter(filters.FilterSet):
    start_date = filters.DateFilter(field_name="order_date", lookup_expr="gte")
    end_date = filters.DateFilter(field_name="order_date", lookup_expr="lte")
    vendor = filters.CharFilter(field_name="vendor_orders__vendor__slug", lookup_expr="iexact")

    class Meta:
        model = Order
        fields = ["start_date", "end_date", "status", "vendor"]


class VendorOrderProductFilter(filters.FilterSet):
    product_name = filters.CharFilter(field_name="product__name", lookup_expr="icontains")
    category = filters.CharFilter(field_name="product__category__slug", lookup_expr="exact")

    class Meta:
        model = VendorOrderProduct
        fields = ["product_name", "category"]


class ProductFilter(filters.FilterSet):
    q = filters.CharFilter(method="filter_product")

    class Meta:
        model = Product
        fields = ["q"]

    def filter_product(self, queryset, name, value):
        q = Q(product_id=value) | Q(name__icontains=value) | Q(tags__keyword__iexact=value)
        return queryset.filter(q).distinct()


class OfficeProductFilter(filters.FilterSet):
    q = filters.CharFilter(method="filter_product")
    inventory = filters.BooleanFilter(field_name="is_inventory")
    favorite = filters.BooleanFilter(field_name="is_favorite")

    class Meta:
        model = OfficeProduct
        fields = ["q", "inventory", "favorite"]

    def filter_product(self, queryset, name, value):
        q = (
            Q(product__product_id=value)
            | Q(product__name__icontains=value)
            | Q(product__tags__keyword__iexact=value)
            | Q(product__child__product_id=value)
            | Q(product__child__name__icontains=value)
            | Q(product__child__tags__keyword__iexact=value)
        )
        return queryset.filter(q).distinct()
