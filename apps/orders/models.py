from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django_extensions.db.fields import AutoSlugField

from apps.accounts.models import Office, User, Vendor
from apps.common.models import FlexibleForeignKey, TimeStampedModel


class ProductCategory(models.Model):
    name = models.CharField(max_length=128)
    slug = AutoSlugField(populate_from=["name"])
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    vendor_categories = models.JSONField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.slug

    class Meta:
        verbose_name_plural = "Product categories"


class Keyword(models.Model):
    keyword = models.CharField(max_length=128, unique=True)

    def __str__(self):
        return self.keyword


class Product(TimeStampedModel):
    """
    This model store basic product info from vendor store
    """

    vendor = FlexibleForeignKey(Vendor, related_name="products", db_index=True)
    product_id = models.CharField(max_length=100)
    category = models.ForeignKey(ProductCategory, null=True, blank=True, on_delete=models.SET_NULL, db_index=True)
    name = models.CharField(max_length=255)
    product_unit = models.CharField(max_length=16, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    url = models.URLField(null=True, blank=True, max_length=300)
    tags = models.ManyToManyField(Keyword)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children", related_query_name="child"
    )

    class Meta:
        unique_together = [
            "vendor",
            "product_id",
        ]

    def __str__(self):
        return f"{self.name} from {self.vendor}"


class ProductImage(TimeStampedModel):
    product = FlexibleForeignKey(Product, related_name="images")
    image = models.URLField(max_length=300)

    def __str__(self):
        return f"{self.product}'s Image"


class OfficeProduct(TimeStampedModel):
    """
    This model is actually used for storing products fetched from search result.
    prices will vary depending on vendor account, so we follow this inheritance
    """

    office = models.ForeignKey(Office, on_delete=models.CASCADE, related_name="products", db_index=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    office_category = models.ForeignKey(ProductCategory, null=True, blank=True, on_delete=models.SET_NULL)
    is_favorite = models.BooleanField(default=False)
    is_inventory = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.product} for {self.office}"

    @classmethod
    def from_dataclass(cls, vendor, dict_data):
        return cls.objects.create(vendor=vendor, **dict_data)

    class Meta:
        unique_together = ["office", "product"]

    # def to_dataclass(self):
    #     return ProductDataClass(
    #         product_id=self.product_id,
    #         name=self.name,
    #         description=self.description,
    #         url=self.url,
    #         images=[ProductImageDataClass(image=image.image) for image in self.images.all()],
    #         price=self.price,
    #         vendor=VendorDataClass(
    #             id=self.vendor.id,
    #             name=self.vendor.name,
    #             slug=self.vendor.slug,
    #             url=self.vendor.url,
    #             logo=self.vendor.logo,
    #         ),
    #     )
    #


class OrderStatus(models.IntegerChoices):
    SHIPPED = 0
    PROCESSING = 1


class OrderMonthManager(models.Manager):
    def get_queryset(self):
        today = timezone.now().date()
        month_first_day = today.replace(day=1)
        next_month_first_day = (month_first_day + timedelta(days=32)).replace(day=1)
        return (
            super().get_queryset().filter(Q(order_date__gte=month_first_day) & Q(order_date__lt=next_month_first_day))
        )


class Order(TimeStampedModel):
    office = FlexibleForeignKey(Office)
    created_by = models.ForeignKey(
        User,
        related_name="orders",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    order_date = models.DateField()
    total_items = models.IntegerField(default=1)
    total_amount = models.DecimalField(decimal_places=2, max_digits=10, default=0)
    status = models.CharField(max_length=100)
    is_approved = models.BooleanField(default=True)
    approved_by = models.ForeignKey(
        User,
        related_name="orders_approved_me",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    objects = models.Manager()
    current_months = OrderMonthManager()

    class Meta:
        ordering = ("-order_date",)

    def __str__(self):
        return f"{self.office.name}(#{self.pk})"


class VendorOrder(TimeStampedModel):
    order = FlexibleForeignKey(Order, related_name="vendor_orders")
    vendor = FlexibleForeignKey(Vendor)
    vendor_order_id = models.CharField(max_length=100)
    total_amount = models.DecimalField(decimal_places=2, max_digits=10)
    total_items = models.IntegerField(default=1)
    currency = models.CharField(max_length=100, default="USD")
    order_date = models.DateField()
    status = models.CharField(max_length=100)
    products = models.ManyToManyField(Product, through="VendorOrderProduct")
    invoice_link = models.URLField(null=True, blank=True)

    objects = models.Manager()
    current_months = OrderMonthManager()

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


class Cart(TimeStampedModel):
    office = FlexibleForeignKey(Office)
    product = FlexibleForeignKey(Product)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    save_for_later = models.BooleanField(default=False)

    class Meta:
        unique_together = [
            "office",
            "product",
        ]


class OfficeCheckoutStatus(TimeStampedModel):
    class ORDER_STATUS(models.TextChoices):
        COMPLETE = "complete", "Complete"
        IN_PROGRESS = "processing", "In Progress"

    class CHECKOUT_STATUS(models.TextChoices):
        COMPLETE = "complete", "Complete"
        IN_PROGRESS = "processing", "In Progress"

    office = models.OneToOneField(Office, on_delete=models.CASCADE, related_name="checkout_status")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    checkout_status = models.CharField(
        choices=CHECKOUT_STATUS.choices, default=CHECKOUT_STATUS.COMPLETE, max_length=16
    )
    order_status = models.CharField(choices=ORDER_STATUS.choices, default=ORDER_STATUS.COMPLETE, max_length=16)


class OfficeKeyword(models.Model):
    class TaskStatus(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not Started"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        FETCHING_COMPLETE = "FETCH_COMPLETE", "Fetching Completed"
        COMPLETE = "COMPLETE", "Completed"
        FAILED = "FAILED", "Failed"

    keyword = models.ForeignKey(Keyword, on_delete=models.CASCADE)
    office = models.ForeignKey(Office, on_delete=models.CASCADE, related_name="keywords")
    vendor = FlexibleForeignKey(Vendor, related_name="keywords")
    task_status = models.CharField(max_length=16, choices=TaskStatus.choices, default=TaskStatus.NOT_STARTED)

    class Meta:
        unique_together = ["office", "vendor", "keyword"]

    def __str__(self):
        return self.keyword.keyword
