from django.db import models

from apps.accounts.models import Office, Vendor
from apps.common.models import FlexibleForeignKey, TimeStampedModel


class Product(TimeStampedModel):
    vendor = FlexibleForeignKey(Vendor, related_name="products")
    product_id = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    url = models.URLField(null=True, blank=True)
    image = models.URLField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # stars: Decimal
    # ratings: Decimal

    @classmethod
    def from_dataclass(cls, vendor, dict_data):
        return cls.objects.create(vendor=vendor, **dict_data)


class OrderStatus(models.IntegerChoices):
    SHIPPED = 0
    PROCESSING = 1


class Order(TimeStampedModel):
    office = FlexibleForeignKey(Office)
    status = models.CharField(max_length=100)


class VendorOrder(TimeStampedModel):
    order = FlexibleForeignKey(Order, related_name="vendor_orders")
    vendor = FlexibleForeignKey(Vendor)
    vendor_order_id = models.CharField(max_length=100)
    total_amount = models.DecimalField(decimal_places=2, max_digits=10)
    total_items = models.IntegerField()
    currency = models.CharField(max_length=100, default="USD")
    order_date = models.DateField()
    status = models.CharField(max_length=100)
    products = models.ManyToManyField(Product, through="VendorOrderProduct")

    def __str__(self):
        return self.vendor_order_id

    class Meta:
        ordering = ["-order_date"]

    @classmethod
    def from_dataclass(cls, vendor, order, dict_data):
        vendor_order_id = dict_data.pop("order_id")
        return cls.objects.create(vendor=vendor, order=order, vendor_order_id=vendor_order_id, **dict_data)


class VendorOrderProduct(TimeStampedModel):
    class Status(models.IntegerChoices):
        OPEN = 0
        SHIPPED = 1
        BACKORDER = 2

    vendor_order = FlexibleForeignKey(VendorOrder)
    product = FlexibleForeignKey(Product)
    quantity = models.IntegerField(default=0)
    unit_price = models.DecimalField(decimal_places=2, max_digits=10)
    status = models.CharField(max_length=100, null=True, blank=True)
    # status = models.IntegerField(choices=Status.choices, default=Status.OPEN)

    @classmethod
    def from_dataclass(cls, order, dict_data):
        return cls.objects.create(order=order, **dict_data)


class YearMonth(models.Func):
    function = "TO_CHAR"
    template = "%(function)s(%(expressions)s, 'YYYY-MM')"
    output_field = models.DateField()


class IsoDate(models.Func):
    function = "TO_CHAR"
    template = "%(function)s(%(expressions)s, 'YYYY-MM-DD')"
    output_field = models.DateField()
