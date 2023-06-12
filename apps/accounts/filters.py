from django.contrib.admin import SimpleListFilter
from django.db.models import Count, Q
from django_filters import rest_framework as filters

from apps.common.choices import OrderStatus
from apps.common.utils import CUSTOM_DATE_FILTER, get_date_range

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


class VendorDateFilter(SimpleListFilter):
    title = "date range"

    parameter_name = "vendororder_range"

    def lookups(self, request, model_admin):
        return CUSTOM_DATE_FILTER

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the date range.
        """
        date_range = get_date_range(self.value())
        if date_range:
            return queryset.annotate(
                _vendor_order_count=Count(
                    "vendororder",
                    filter=Q(
                        vendororder__order_date__gte=date_range[0],
                        vendororder__order_date__lte=date_range[1],
                        vendororder__status__in=[OrderStatus.OPEN, OrderStatus.CLOSED],
                    ),
                )
            ).order_by("-_vendor_order_count")
        else:
            return queryset.annotate(
                _vendor_order_count=Count(
                    "vendororder", filter=Q(vendororder__status__in=[OrderStatus.OPEN, OrderStatus.CLOSED])
                )
            ).order_by("-_vendor_order_count")
