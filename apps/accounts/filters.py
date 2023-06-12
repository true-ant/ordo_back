from datetime import datetime
from decimal import Decimal

from django.contrib.admin import SimpleListFilter
from django.db.models import Count, F, Func, OuterRef, Q, Subquery
from django_filters import rest_framework as filters

from apps.common.choices import OrderStatus, OrderType
from apps.common.utils import CUSTOM_DATE_FILTER, get_date_range
from apps.orders import models as om

from .models import CompanyMember, OfficeBudget, Vendor


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
        if not date_range:
            date_range = (datetime.min, datetime.max)
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


class CompanyDateFilter(SimpleListFilter):
    title = "date range"
    parameter_name = "date_range"

    def lookups(self, request, model_admin):
        return CUSTOM_DATE_FILTER

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the date range.
        """
        date_range = get_date_range(self.value())
        if not date_range:
            date_range = (datetime.min, datetime.max)

        orders = (
            om.Order.objects.filter(
                order_type__in=[OrderType.ORDO_ORDER, OrderType.ORDER_REDUNDANCY],
                office__company_id=OuterRef("pk"),
                order_date__gte=date_range[0],
                order_date__lte=date_range[1],
            )
            .order_by()
            .annotate(count=Func(F("id"), function="Count"))
            .values("count")
        )

        vendor_orders = (
            om.VendorOrder.objects.filter(
                status__in=[OrderStatus.OPEN, OrderStatus.CLOSED],
                order__office__company_id=OuterRef("pk"),
                order_date__gte=date_range[0],
                order_date__lte=date_range[1],
            )
            .order_by()
            .annotate(count=Func(F("id"), function="Count"))
            .values("count")
        )

        total_amount = (
            om.Order.objects.filter(
                order_type__in=[OrderType.ORDO_ORDER, OrderType.ORDER_REDUNDANCY],
                office__company_id=OuterRef("pk"),
                order_date__gte=date_range[0],
                order_date__lte=date_range[1],
            )
            .order_by()
            .annotate(
                sum_total_amount=Func(Func(F("total_amount"), function="Sum"), Decimal(0), function="Coalesce"),
            )
            .values("sum_total_amount")
        )

        qs = queryset.annotate(
            order_count=Subquery(orders),
            vendor_order_count=Subquery(vendor_orders),
            ordo_order_volume=Subquery(total_amount),
        )
        return qs
