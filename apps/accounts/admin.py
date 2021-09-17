from django.contrib import admin

from . import models as m


@admin.register(m.User)
class UserAdmin(admin.ModelAdmin):
    pass


@admin.register(m.Company)
class CompanyAdmin(admin.ModelAdmin):
    pass
