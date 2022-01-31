import datetime

from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.utils import timezone
from django_filters import rest_framework as filters

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
        today = timezone.now().date()
        first_day_of_this_week = today - relativedelta(days=today.weekday())
        first_day_of_this_month = today.replace(day=1)
        first_day_of_this_year = datetime.date(year=today.year, month=1, day=1)
        first_day_of_last_year = datetime.date(year=today.year - 1, month=1, day=1)
        first_day_of_last_month = first_day_of_this_month - relativedelta(months=1)
        last_day_of_last_month = first_day_of_this_month - relativedelta(days=1)
        last_day_of_last_year = datetime.date(year=today.year - 1, month=12, day=31)
        days_30_ago = today - relativedelta(days=30)
        days_90_ago = today - relativedelta(days=90)
        months_12_ago = today - relativedelta(months=12)

        q = Q()
        if value == "thisWeek":
            q = Q(order_date__gte=first_day_of_this_week) & Q(order_date__lte=today)
        elif value == "thisMonth":
            q = Q(order_date__gte=first_day_of_this_month) & Q(order_date__lte=today)
        elif value == "lastMonth":
            q = Q(order_date__gte=first_day_of_last_month) & Q(order_date__lte=last_day_of_last_month)
        elif value == "last30Days":
            q = Q(order_date__gte=days_30_ago) & Q(order_date__lte=today)
        elif value == "last90Days":
            q = Q(order_date__gte=days_90_ago) & Q(order_date__lte=today)
        elif value == "last12Months":
            q = Q(order_date__gte=months_12_ago) & Q(order_date__lte=today)
        elif value == "thisYear":
            q = Q(order_date__gte=first_day_of_this_year) & Q(order_date__lte=today)
        elif value == "lastYear":
            q = Q(order_date__gte=first_day_of_last_year) & Q(order_date__lte=last_day_of_last_year)

        return queryset.filter(q)


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
    category = filters.CharFilter(field_name="office_category__slug")
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
