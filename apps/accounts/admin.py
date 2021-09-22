from django.contrib import admin
from django.utils.safestring import mark_safe

from . import models as m


@admin.register(m.User)
class UserAdmin(admin.ModelAdmin):
    pass


class OfficeInline(admin.TabularInline):
    model = m.Office
    extra = 0


@admin.register(m.Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "on_boarding_step",
        "is_active",
    )
    inlines = (OfficeInline,)


@admin.register(m.Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = (
        "logo_thumb",
        "name",
        "slug",
        "url",
    )

    @admin.display(description="Logo")
    def logo_thumb(self, obj):
        return mark_safe("<img src='{}'  width='30' height='30' />".format(obj.logo.url))
