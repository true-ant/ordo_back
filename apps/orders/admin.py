from django.contrib import admin

from . import models as m


@admin.register(m.Order)
class OrderAdmin(admin.ModelAdmin):
    pass


@admin.register(m.Product)
class ProductAdmin(admin.ModelAdmin):
    pass
