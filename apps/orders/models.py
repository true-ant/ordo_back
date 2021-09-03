from django.db import models

from apps.accounts.models import OfficeVendor, Vendor
from apps.common.models import FlexibleForeignKey, TimeStampedModel


class Product(TimeStampedModel):
    vendor = FlexibleForeignKey(Vendor, related_name="products")
    product_id = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    url = models.URLField(null=True, blank=True)
    image = models.URLField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    # stars: Decimal
    # ratings: Decimal

    @classmethod
    def from_dataclass(cls, vendor, dict_data):
        return cls.objects.create(vendor=vendor, **dict_data)


class Order(TimeStampedModel):
    class Status(models.IntegerChoices):
        SHIPPED = 0
        PROCESSING = 1

    office_vendor = FlexibleForeignKey(OfficeVendor, related_name="orders")
    order_id = models.CharField(max_length=100)
    total_amount = models.DecimalField(decimal_places=2, max_digits=10)
    currency = models.CharField(max_length=100)
    order_date = models.DateField()
    status = models.CharField(max_length=100)
    products = models.ManyToManyField(Product, through="OrderProduct")
    # status = models.IntegerField(choices=Status.choices, default=Status.PROCESSING)

    def __str__(self):
        return self.order_id

    class Meta:
        ordering = ["-order_date"]

    @classmethod
    def from_dataclass(cls, office_vendor, dict_data):
        return cls.objects.create(office_vendor=office_vendor, **dict_data)


class OrderProduct(TimeStampedModel):
    class Status(models.IntegerChoices):
        OPEN = 0
        SHIPPED = 1
        BACKORDER = 2

    order = FlexibleForeignKey(Order)
    product = FlexibleForeignKey(Product)
    quantity = models.IntegerField(default=0)
    unit_price = models.DecimalField(decimal_places=2, max_digits=10)
    status = models.CharField(max_length=100)
    # status = models.IntegerField(choices=Status.choices, default=Status.OPEN)

    @classmethod
    def from_dataclass(cls, order, dict_data):
        return cls.objects.create(order=order, **dict_data)


class YearMonth(models.Func):
    function = "TO_CHAR"
    template = "%(function)s(%(expressions)s, 'YYYY-MM')"
    output_field = models.DateField()
