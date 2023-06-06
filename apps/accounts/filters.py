from django.db.models import Q
from django_filters import rest_framework as filters

from .models import Budget, CompanyMember, Vendor


class BudgetFilter(filters.FilterSet):
    start_month = filters.DateFilter(field_name="month", lookup_expr="gte", input_formats=["%Y-%m"])
    end_month = filters.DateFilter(field_name="month", lookup_expr="lte", input_formats=["%Y-%m"])

    class Meta:
        model = Budget
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


class CompanyMemberFilter(filters.FilterSet):
    office_id = filters.NumberFilter(method="filter_office_members")

    class Meta:
        model = CompanyMember
        fields = ["office_id"]

    def filter_office_members(self, queryset, name, value):
        return queryset.filter(Q(office_id=value) | Q(office__isnull=True))
