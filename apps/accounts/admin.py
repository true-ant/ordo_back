from decimal import Decimal
from dateutil.relativedelta import relativedelta

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.safestring import mark_safe
from nested_admin.nested import NestedModelAdmin, NestedTabularInline

from apps.common.admins import ReadOnlyAdminMixin, AdminDynamicPaginationMixin
from apps.common.choices import OrderType, OrderStatus
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


class OfficeOrdersInline(NestedTabularInline):
    model = om.Order
    readonly_fields = ("id", "company", "office", "vendors", "total_price", "order_date", "order_type", "status")
    fields = ("vendors", "order_date", "total_items", "total_amount", "company", "order_type", "status")

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
        "ordo_order_count",
        "vendor_order_count",
        "ordo_order_volume",
        "is_active",
    )
    inlines = (
        CompanyMemberInline,
        OfficeInline,
    )
    ordering = ("-on_boarding_step",)

    @admin.display(description="Order Count")
    def ordo_order_count(self, obj):
        return om.Order.objects.filter(
            order_type__in=[OrderType.ORDO_ORDER, OrderType.ORDER_REDUNDANCY],
            office__in=obj.offices.all()
        ).count()

    @admin.display(description="Vendor Order Count")
    def vendor_order_count(self, obj):
        return om.VendorOrder.objects.filter(
            status__in=[OrderStatus.OPEN, OrderStatus.CLOSED],
            order__office__in=obj.offices.all()
        ).count()

    @admin.display(description="Order Volume")
    def ordo_order_volume(self, obj):
        total_amount = om.Order.objects.filter(
            order_type__in=[OrderType.ORDO_ORDER, OrderType.ORDER_REDUNDANCY],
            office__in=obj.offices.all()
        ).aggregate(
            order_total_amount=Coalesce(Sum("total_amount"), Decimal(0))
        )["order_total_amount"]

        return f"${total_amount}"


@admin.register(m.Vendor)
class VendorAdmin(AdminDynamicPaginationMixin, admin.ModelAdmin):
    list_display = (
        "__str__",
        "logo_thumb",
        "name",
        "slug",
        "vendor_order_count",
        "url",
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = (
            queryset.annotate(
                _vendor_order_count=Count(
                    "vendororder",
                    filter=Q(vendororder__status__in=[OrderStatus.OPEN, OrderStatus.CLOSED])
                )
            ).order_by("-_vendor_order_count")
        )
        return queryset

    @admin.display(description="Logo")
    def logo_thumb(self, obj):
        return mark_safe("<img src='{}'  width='30' height='30' />".format(obj.logo))

    @admin.display(description="Vendor Order Count")
    def vendor_order_count(self, obj):
        return obj._vendor_order_count
