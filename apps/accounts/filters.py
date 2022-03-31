from django_filters import rest_framework as filters

from .models import OfficeBudget, Vendor


class OfficeBudgetFilter(filters.FilterSet):
    start_month = filters.DateFilter(field_name="month", lookup_expr="gte", input_formats=["%Y-%m"])
    end_month = filters.DateFilter(field_name="month", lookup_expr="lte", input_formats=["%Y-%m"])

    class Meta:
        model = OfficeBudget
        fields = ["start_month", "end_month"]


class VendorFilter(filters.FilterSet):
    slugs = filters.CharFilter(method="filter_slugs")

    class Meta:
        model = Vendor
        fields = ["slugs"]

    def filter_slugs(self, queryset, name, value):
        slugs = value.split(",")
        if slugs:
            return queryset.filter(slug__in=slugs)
        return queryset
