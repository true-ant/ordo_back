from django.db import models

from apps.accounts.models import OfficeVendor
from apps.common.models import FlexibleForeignKey, TimeStampedModel


class Order(TimeStampedModel):
    class Status(models.IntegerChoices):
        SHIPPED = 0
        PROCESSING = 1

    office_vendor = FlexibleForeignKey(OfficeVendor)
    order_id = models.CharField(max_length=100)
    total_amount = models.DecimalField(decimal_places=2, max_digits=10)
    currency = models.CharField(max_length=100)
    order_date = models.DateField()
    status = models.CharField(max_length=100)
    # status = models.IntegerField(choices=Status.choices, default=Status.PROCESSING)

    def __str__(self):
        return self.order_id

    class Meta:
        ordering = ["-order_date"]

    @classmethod
    def from_dataclass(cls, office_vendor, dict_data):
        return cls.objects.create(office_vendor=office_vendor, **dict_data)


class OrderItem(TimeStampedModel):
    class Status(models.IntegerChoices):
        OPEN = 0
        SHIPPED = 1
        BACKORDER = 2

    order = FlexibleForeignKey(Order, related_name="items")
    name = models.CharField(max_length=100)
    quantity = models.IntegerField(default=0)
    unit_price = models.DecimalField(decimal_places=2, max_digits=10)
    status = models.CharField(max_length=100)
    # status = models.IntegerField(choices=Status.choices, default=Status.OPEN)

    def __str__(self):
        return f"{self.order} - {self.name}"

    @classmethod
    def from_dataclass(cls, order, dict_data):
        return cls.objects.create(order=order, **dict_data)
