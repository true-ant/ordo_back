from decimal import Decimal
from typing import Any

from dateutil.relativedelta import relativedelta
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.db.models import Count, F, Func, OuterRef, Q, Subquery
from django.db.models.query import QuerySet
from django.http.request import HttpRequest
from django.utils import timezone
from django.utils.safestring import mark_safe
from apps.common.utils import get_order_string
from nested_admin.nested import NestedModelAdmin, NestedTabularInline

from apps.common.admins import AdminDynamicPaginationMixin, ReadOnlyAdminMixin
from apps.common.choices import OrderStatus, OrderType
from apps.common.month import Month
from apps.orders import models as om

from . import models as m

admin.ModelAdmin.list_per_page = 10


@admin.register(m.User)
# class UserAdmin(admin.ModelAdmin):
class UserAdmin(AdminDynamicPaginationMixin, DefaultUserAdmin):
    list_display = (
        "username",
        "first_name",
        "last_name",
        "email",
        "is_staff",
        "is_active",
        "date_joined",
        "role",
        "avatar",
    )

    def get_queryset(self, request):
        order_str = get_order_string(request)
        if order_str:
            self.ordering = (order_str,)
        return super().get_queryset(request)


class CompanyMemberInline(ReadOnlyAdminMixin, NestedTabularInline):
    model = m.CompanyMember
    exclude = ("token", "token_expires_at")
    readonly_fields = (
        "user",
        "email",
        "role",
        "office",
        "invite_status",
        "date_joined",
        "is_active",
    )


class OfficeVendorInline(ReadOnlyAdminMixin, NestedTabularInline):
    model = m.OfficeVendor
    readonly_fields = fields = ("vendor", "username", "password")


# class OfficeBudgetInline(ReadOnlyAdminMixin, NestedTabularInline):
#     model = m.OfficeBudget
#     readonly_fields = fields = (
#         "month",
#         "dental_budget",
#         "dental_spend",
#         "office_budget",
#         "office_spend",
#     )

#     def get_queryset(self, request):
#         current_date = timezone.now().date()
#         month = Month(year=current_date.year, month=current_date.month)
#         return super().get_queryset(request).filter(month=month)


class OfficeBudgetInline(NestedTabularInline):
    model = m.OfficeBudget
    fields = (
        "month",
        "dental_budget",
        "dental_spend",
        "office_budget",
        "office_spend",
    )

    def get_queryset(self, request):
        current_date = timezone.now().date()
        three_months_ago = current_date - relativedelta(months=3)
        month = Month(year=current_date.year, month=three_months_ago.month)
        return super().get_queryset(request).filter(month__gte=month).order_by("-month")


class OfficeOrdersInline(ReadOnlyAdminMixin, NestedTabularInline):
    model = om.Order
    readonly_fields = (
        "id",
        "company",
        "office",
        "vendors",
        "total_price",
        "order_date",
        "order_type",
        "status",
        "total_items",
        "total_amount",
    )
    fields = ("vendors", "order_date", "total_items", "total_amount", "company", "order_type", "status")
    show_change_link = True

    @admin.display(description="Company")
    def company(self, obj):
        return obj.office.company

    @admin.display(description="Vendors")
    def vendors(self, objs):
        return ", ".join([vendor_order.vendor.name for vendor_order in objs.vendor_orders.all()])

    @admin.display(description="Order Total")
    def total_price(self, objs):
        return objs.total_amount

    def get_queryset(self, request):
        return super().get_queryset(request)


class SubscriptionInline(NestedTabularInline):
    model = m.Subscription
    # readonly_fields = ("subscription_id",)
    extra = 0


class OfficeInline(NestedTabularInline):
    model = m.Office
    inlines = [SubscriptionInline, OfficeVendorInline, OfficeBudgetInline, OfficeOrdersInline]
    can_delete = False
    readonly_fields = (
        "logo_thumb",
        "name",
        "phone_number",
        "website",
        "is_active",
        "practice_software"
    )
    exclude = ("logo",)
    extra = 0

    @admin.display(description="Logo")
    def logo_thumb(self, obj):
        return mark_safe("<img src='{}'  width='30' height='30' />".format(obj.logo))


@admin.register(m.Company)
class CompanyAdmin(AdminDynamicPaginationMixin, NestedModelAdmin):
    list_display = (
        "name",
        "on_boarding_step",
        "order_count",
        "vendor_order_count",
        "ordo_order_volume",
        "is_active",
    )
    inlines = (
        CompanyMemberInline,
        OfficeInline,
    )

    def get_queryset(self, request):
        orders = (
            om.Order.objects.filter(
                order_type__in=[OrderType.ORDO_ORDER, OrderType.ORDER_REDUNDANCY], office__company_id=OuterRef("pk")
            )
            .order_by()
            .annotate(count=Func(F("id"), function="Count"))
            .values("count")
        )

        vendor_orders = (
            om.VendorOrder.objects.filter(
                status__in=[OrderStatus.OPEN, OrderStatus.CLOSED], order__office__company_id=OuterRef("pk")
            )
            .order_by()
            .annotate(count=Func(F("id"), function="Count"))
            .values("count")
        )

        total_amount = (
            om.Order.objects.filter(
                order_type__in=[OrderType.ORDO_ORDER, OrderType.ORDER_REDUNDANCY], office__company_id=OuterRef("pk")
            )
            .order_by()
            .annotate(
                sum_total_amount=Func(Func(F("total_amount"), function="Sum"), Decimal(0), function="Coalesce"),
            )
            .values("sum_total_amount")
        )

        qs = m.Company.objects.annotate(
            order_count=Subquery(orders),
            vendor_order_count=Subquery(vendor_orders),
            ordo_order_volume=Subquery(total_amount),
        )
        
        sort_str = get_order_string(request)
        if sort_str:
            qs = qs.order_by(sort_str)
        return qs

    @admin.display(description="Ordo Order Count")
    def order_count(self, obj):
        return obj.order_count

    @admin.display(description="Vendor Order Count")
    def vendor_order_count(self, obj):
        return obj.vendor_order_count

    @admin.display(description="Ordo Order Volume")
    def ordo_order_volume(self, obj):
        return f"${obj.ordo_order_volume}"


@admin.register(m.Vendor)
class VendorAdmin(AdminDynamicPaginationMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "logo_thumb",
        "vendor_order_count",
        "url",
    )

    sort_exclude = (
        'logo_thumb',
    )

    def get_queryset(self, request):
        queryset = m.Vendor.objects.all().annotate(
            vendor_order_count=Count(
                "vendororder", filter=Q(vendororder__status__in=[OrderStatus.OPEN, OrderStatus.CLOSED])
            )
        )
        order_str = get_order_string(request, self.sort_exclude)
        if order_str:
            self.ordering = (order_str, "name")
        return queryset

    @admin.display(description="Logo")
    def logo_thumb(self, obj):
        return mark_safe("<img src='{}'  width='30' height='30' />".format(obj.logo))

    @admin.display(description="Vendor Order Count")
    def vendor_order_count(self, obj):
        return obj.vendor_order_count
