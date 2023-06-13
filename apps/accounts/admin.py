from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.db.models import CharField, F, Func, OuterRef, Subquery, Value
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from nested_admin.nested import NestedModelAdmin, NestedTabularInline

from apps.accounts.filters import VendorDateFilter
from apps.accounts.tasks import fetch_order_history
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
        "full_name",
        "companies",
        "date_joined",
        "role",
        "is_staff",
    )
    readonly_fields = (
        "date_joined",
        "last_login",
    )
    list_filter = ()

    def get_queryset(self, request):
        company_names = (
            m.CompanyMember.objects.filter(user_id=OuterRef("pk"))
            .order_by()
            .annotate(companies=Func(F("company__name"), Value(", "), function="string_agg", output_field=CharField()))
            .values("companies")
        )
        return m.User.objects.annotate(companies=Subquery(company_names))

    @admin.display(description="Companies")
    def companies(self, obj):
        return obj.companies


class CompanyMemberInline(ReadOnlyAdminMixin, NestedTabularInline):
    model = m.CompanyMember
    exclude = ("token", "token_expires_at")
    readonly_fields = (
        "invited_by",
        "user_full_name",
        "email",
        "role",
        "office",
        "invite_status",
        "date_joined",
        "is_active",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    @admin.display(description="User")
    def user_full_name(self, obj):
        return obj.user.full_name


class OfficeVendorInline(ReadOnlyAdminMixin, NestedTabularInline):
    model = m.OfficeVendor
    readonly_fields = fields = ("vendor", "username", "password", "relink", "vendor_login")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("vendor")

    @admin.display(description="Relink Vendor")
    def relink(self, obj):
        if obj.login_success:
            return ""
        else:
            return format_html(
                '<a class="btn btn-outline-primary" href="{}" class="link">Relink Vendor</a>',
                reverse_lazy("admin:admin_relink_officevendor", args=[obj.pk]),
            )

    @admin.display(description="Vendor Login")
    def vendor_login(self, obj):
        url = obj.vendor.url
        return mark_safe("<a target='_blank' href='{}' class='btn btn-outline-primary'>Vendor Login</a>".format(url))


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

    def get_urls(self):
        urls = super().get_urls()
        return [
            path("relink-officevendor/<int:pk>/", self.relink_officevendor, name="admin_relink_officevendor"),
            *urls,
        ]

    def relink_officevendor(self, request, pk):
        officevendor = get_object_or_404(m.OfficeVendor, pk=pk)
        officevendor.login_success = True
        officevendor.save()
        fetch_order_history.delay(
            vendor_slug=officevendor.vendor.slug,
            office_id=officevendor.office_id,
        )
        return redirect(request.META.get("HTTP_REFERER"))

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
    list_filter = (VendorDateFilter,)
    search_fields = ("name",)

    @admin.display(description="Logo")
    def logo_thumb(self, obj):
        return mark_safe("<img src='{}'  width='30' height='30' />".format(obj.logo))

    @admin.display(description="Vendor Order Count")
    def vendor_order_count(self, obj):
        return obj._vendor_order_count

    vendor_order_count.admin_order_field = "_vendor_order_count"
