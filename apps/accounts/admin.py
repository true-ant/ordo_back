from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.db.models import Count, F, Func, OuterRef, Q, Subquery
from django.utils import timezone
from django.utils.safestring import mark_safe
from nested_admin.nested import NestedModelAdmin, NestedTabularInline

from apps.common.admins import AdminDynamicPaginationMixin, ReadOnlyAdminMixin
from apps.common.choices import OrderStatus, OrderType
from apps.common.month import Month
from apps.orders import models as om

from . import models as m

admin.ModelAdmin.list_per_page = 50


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


class CompanyMemberInline(ReadOnlyAdminMixin, NestedTabularInline):
    model = m.CompanyMember
    exclude = ("token", "token_expires_at")
    readonly_fields = (
        "invited_by",
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


class OfficeBudgetInline(NestedTabularInline):
    model = m.OfficeBudget
    fields = readonly_fields = (
        "month",
        "dental_budget_type",
        "dental_budget",
        "dental_spend",
        "dental_percentage",
        "office_budget_type",
        "office_budget",
        "office_spend",
        "office_percentage",
    )

    def get_queryset(self, request):
        current_date = timezone.localtime().date()
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
    fields = ("subscription_id", "start_on", "cancelled_on")
    readonly_fields = ("subscription_id",)


class OfficeInline(NestedTabularInline):
    model = m.Office
    inlines = [SubscriptionInline, OfficeVendorInline, OfficeBudgetInline, OfficeOrdersInline]
    can_delete = False
    readonly_fields = ("dental_api", "logo_thumb", "name", "phone_number", "website", "is_active", "practice_software")
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
    search_fields = ("name",)
    inlines = (
        CompanyMemberInline,
        OfficeInline,
    )
    ordering = ("-on_boarding_step",)

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

        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
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

    order_count.admin_order_field = "order_count"
    vendor_order_count.admin_order_field = "vendor_order_count"
    ordo_order_volume.admin_order_field = "ordo_order_volume"


@admin.register(m.Vendor)
class VendorAdmin(AdminDynamicPaginationMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "logo_thumb",
        "vendor_order_count",
        "url",
    )
    search_fields = ("name",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            _vendor_order_count=Count(
                "vendororder", filter=Q(vendororder__status__in=[OrderStatus.OPEN, OrderStatus.CLOSED])
            )
        ).order_by("-_vendor_order_count")
        return queryset

    @admin.display(description="Logo")
    def logo_thumb(self, obj):
        return mark_safe("<img src='{}'  width='30' height='30' />".format(obj.logo))

    @admin.display(description="Vendor Order Count")
    def vendor_order_count(self, obj):
        return obj._vendor_order_count

    vendor_order_count.admin_order_field = "_vendor_order_count"
