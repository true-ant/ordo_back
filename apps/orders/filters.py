from django_filters import rest_framework as filters

from .models import Order, VendorOrderProduct


class OrderFilter(filters.FilterSet):
    start_date = filters.DateFilter(field_name="order_date", lookup_expr="gte")
    end_date = filters.DateFilter(field_name="order_date", lookup_expr="lte")

    class Meta:
        model = Order
        fields = ["start_date", "end_date", "status"]


class VendorOrderProductFilter(filters.FilterSet):
    product_name = filters.CharFilter(field_name="product__name", lookup_expr="icontains")
    category = filters.CharFilter(field_name="product__category__slug", lookup_expr="exact")

    class Meta:
        model = VendorOrderProduct
        fields = ["product_name", "category"]
