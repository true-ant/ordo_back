import datetime

from django.db.models import Q
from django_filters import rest_framework as filters

from apps.common.utils import get_date_range

from .models import OfficeProduct, Order, Product, VendorOrder, VendorOrderProduct


class OrderFilter(filters.FilterSet):
    start_date = filters.DateFilter(field_name="order_date", lookup_expr="gte")
    end_date = filters.DateFilter(field_name="order_date", lookup_expr="lte")
    vendor = filters.CharFilter(field_name="vendor_orders__vendor__slug", lookup_expr="iexact")

    class Meta:
        model = Order
        fields = ["start_date", "end_date", "status", "vendor"]


class VendorOrderFilter(filters.FilterSet):
    ids = filters.CharFilter(method="filter_by_ids")
    start_date = filters.DateFilter(field_name="order_date", lookup_expr="gte")
    end_date = filters.DateFilter(field_name="order_date", lookup_expr="lte")
    budget_type = filters.CharFilter(method="filter_by_budget_type")
    date_range = filters.CharFilter(method="filter_by_range")
    status = filters.CharFilter(field_name="status")
    q = filters.CharFilter(method="filter_orders")

    class Meta:
        model = VendorOrder
        fields = ["status", "start_date", "end_date"]

    def filter_by_ids(self, queryset, name, value):
        ids = value.split(",")
        q = Q(id__in=ids)

        return queryset.filter(q)

    def filter_by_budget_type(self, queryset, name, value):
        q = Q()
        if value == "dental":
            q = ~Q(vendor__slug="amazon")
        elif value == "office":
            q = Q(vendor__slug="amazon")

        return queryset.filter(q)

    def filter_by_range(self, queryset, name, value):
        start_end_date = get_date_range(value)
        if start_end_date:
            q = Q(order_date__gte=start_end_date[0]) & Q(order_date__lte=start_end_date[1])
            return queryset.filter(q)
        else:
            return queryset

    def filter_orders(self, queryset, name, value):
        q = (
            Q(products__name__icontains=value)
            | Q(products__category__name__icontains=value)
            | Q(vendor__name__icontains=value)
            | Q(nickname__icontains=value)
        )
        try:
            value = datetime.datetime.strptime(value, "%m/%d/%y").date()
            q |= Q(order_date=value)
        except (TypeError, ValueError):
            pass
        return queryset.filter(q).distinct()


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


class ProductV2Filter(filters.FilterSet):
    vendors = filters.CharFilter(method="filter_by_vendors")
    # search = filters.CharFilter(field_name="name", lookup_expr="search")
    # search = filters.CharFilter(method="filter_by_name")

    def filter_by_vendors(self, queryset, name, value):
        vendor_slugs = value.split(",")
        q = Q(vendor__slug__in=vendor_slugs) | (Q(vendor__isnull=True) & (Q(child__vendor__slug__in=vendor_slugs)))

        return queryset.filter(q).distinct()

    # def filter_by_name(self, queryset, name, value):
    #     product_id_value = value.replace("-", "")
    #     return queryset.filter(
    #         Q(name__search=value)
    #         | Q(product_id__icontains=product_id_value)
    #         | Q(product_id__icontains=value)
    #         | Q(child__product_id__icontains=product_id_value)
    #         | Q(child__product_id__icontains=value)
    #     ).distinct()


class OfficeProductFilter(filters.FilterSet):
    q = filters.CharFilter(method="filter_product")
    inventory = filters.BooleanFilter(field_name="is_inventory")
    favorite = filters.BooleanFilter(field_name="is_favorite")
    category = filters.CharFilter(field_name="office_product_category__slug")
    vendors = filters.CharFilter(method="filter_by_vendors")

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

    def filter_by_vendors(self, queryset, name, value):
        vendors = value.split(",")
        if vendors:
            return queryset.filter(product__vendor__slug__in=vendors)
        return queryset
