from django.contrib import admin
from django.utils.safestring import mark_safe
from nested_admin.nested import NestedModelAdmin, NestedTabularInline

from apps.common.admins import ReadOnlyAdminMixin

from . import models as m


@admin.register(m.User)
class UserAdmin(admin.ModelAdmin):
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
    readonly_fields = (
        "vendor",
        "username",
    )


class OfficeInline(NestedTabularInline):
    model = m.Office
    inlines = [OfficeVendorInline]
    can_delete = False
    readonly_fields = (
        "logo_thumb",
        "name",
        "phone_number",
        "website",
        "cc_number",
        "cc_expiry",
        "cc_code",
        "is_active",
    )
    exclude = ("logo",)
    extra = 0

    @admin.display(description="Logo")
    def logo_thumb(self, obj):
        return mark_safe("<img src='{}'  width='30' height='30' />".format(obj.logo))


@admin.register(m.Company)
class CompanyAdmin(NestedModelAdmin):
    list_display = (
        "name",
        "on_boarding_step",
        "is_active",
    )
    inlines = (
        OfficeInline,
        CompanyMemberInline,
    )


@admin.register(m.Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "logo_thumb",
        "name",
        "slug",
        "url",
    )

    @admin.display(description="Logo")
    def logo_thumb(self, obj):
        return mark_safe("<img src='{}'  width='30' height='30' />".format(obj.logo))
