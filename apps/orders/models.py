from datetime import timedelta

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import (  # TrigramSimilarity,
    SearchQuery,
    SearchVectorField,
)
from django.db import models
from django.db.models import Q
from django.db.models.expressions import RawSQL
from django.utils import timezone
from django_extensions.db.fields import AutoSlugField
from slugify import slugify

from apps.accounts.models import Office, ShippingMethod, User, Vendor
from apps.common.choices import (
    BUDGET_SPEND_TYPE,
    OrderStatus,
    ProcedureType,
    ProductStatus,
)
from apps.common.models import FlexibleForeignKey, TimeStampedModel
from apps.common.utils import remove_dash_between_numerics
from apps.scrapers.schema import Product as ProductDataClass
from apps.scrapers.schema import ProductImage as ProductImageDataClass
from apps.scrapers.schema import Vendor as VendorDataClass
from apps.vendor_clients.types import Product as ProductDict


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


class Keyword(TimeStampedModel):
    keyword = models.CharField(max_length=128, unique=True)

    def __str__(self):
        return self.keyword


class ProductQuerySet(models.QuerySet):
    def search(self, text):
        # this is for search for henry schein product id
        text = remove_dash_between_numerics(text)
        # trigram_similarity = TrigramSimilarity("name", text)
        q = SearchQuery(text, config="english")
        return (
            self
            # .annotate(similarity=trigram_similarity)
            .filter(Q(search_vector=q))
        )

    def with_inventory_refs(self):
        return self.annotate(_inventory_refs=RawSQL("inventory_refs", (), output_field=models.IntegerField()))


class ProductManager(models.Manager):
    _queryset_class = ProductQuerySet

    def search(self, text):
        return self.get_queryset().search(text)


class Promotion(models.Model):
    """
    This model store promotion for one-time apply in cart.
    """

    code = models.CharField(max_length=128, unique=True)
    type = models.IntegerField(default=1)
    reduction_price = models.IntegerField(default=0, null=True)
    description = models.CharField(max_length=128, null=True)

    def __str__(self):
        return self.code


class Product(TimeStampedModel):
    """
    This model store basic product info from vendor store
    """

    vendor = FlexibleForeignKey(Vendor, related_name="products", null=True, blank=True)
    product_id = models.CharField(max_length=128, db_index=True, null=True)
    sku = models.CharField(max_length=32, null=True, blank=True)
    manufacturer_number = models.CharField(max_length=128, null=True, blank=True)
    manufacturer_number_origin = models.CharField(max_length=128, null=True, blank=True)
    category = models.ForeignKey(ProductCategory, null=True, blank=True, on_delete=models.SET_NULL, db_index=True)
    name = models.CharField(max_length=512)
    product_unit = models.CharField(max_length=16, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    url = models.URLField(null=True, blank=True, max_length=1024)
    tags = models.ManyToManyField(Keyword)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        related_query_name="child",
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    last_price_updated = models.DateTimeField(null=True, blank=True, db_index=True)
    product_vendor_status = models.CharField(max_length=512, null=True, blank=True)

    is_special_offer = models.BooleanField(default=False)
    special_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    promotion_description = models.TextField(null=True, blank=True)
    search_vector = SearchVectorField(null=True, blank=True, help_text="Search vector")
    price_expiration = models.DateTimeField(null=True, blank=True, help_text="Price expiration")

    objects = ProductManager()

    class Meta:
        unique_together = [
            "vendor",
            "product_id",
        ]
        indexes = [
            GinIndex(name="product_name_gin_idx", fields=["name"], opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self):
        return f"{self.name} from {self.vendor}"

    @property
    def inventory_refs(self):
        return self._inventory_refs

    @property
    def sibling_products(self):
        if self.parent:
            return self.parent.children.exclude(id=self.id)
        return self.__class__.objects.none()

    @property
    def recent_price(self):
        # TODO: let's get rid of this code in favor of either cleaning up, updating
        #       more frequently or returning `oudated` flag
        if self.vendor.slug in settings.NON_FORMULA_VENDORS:
            if self.vendor.slug in ["net_32", "dental_city"] and self.last_price_updated:
                ages_in_days = (timezone.now() - self.last_price_updated).days
                life_span_in_days = (
                    settings.NET32_PRODUCT_PRICE_UPDATE_CYCLE
                    if self.vendor.slug == "net_32"
                    else settings.PRODUCT_PRICE_UPDATE_CYCLE
                )
                if ages_in_days < life_span_in_days:
                    return self.price
            else:
                return self.price

    def to_dict(self) -> ProductDict:
        return {
            "vendor": self.vendor.slug,
            "product_id": self.product_id if self.product_id else "",
            "sku": "",
            "name": self.name,
            "url": self.url if self.url else "",
            "images": [image.image for image in self.images.all()],
            "price": self.price,
            "category": self.category.slug if self.category else "",
            "unit": self.product_unit,
        }

    async def ato_dict(self) -> ProductDict:
        return {
            "vendor": self.vendor.slug,
            "product_id": self.product_id if self.product_id else "",
            "sku": "",
            "name": self.name,
            "url": self.url if self.url else "",
            "images": [image.image async for image in self.images.all()],
            "price": self.price,
            "category": self.category.slug if self.category else "",
            "unit": self.product_unit,
        }

    def to_dataclass(self):
        return ProductDataClass(
            product_id=self.product_id,
            name=self.name,
            description=self.description,
            url=self.url,
            images=[ProductImageDataClass(image=image.image) for image in self.images.all()],
            price=self.price,
            vendor=VendorDataClass(
                id=self.vendor.id,
                name=self.vendor.name,
                slug=self.vendor.slug,
                url=self.vendor.url,
                logo=self.vendor.logo,
            ),
        )


class ProductImage(TimeStampedModel):
    product = FlexibleForeignKey(Product, related_name="images")
    image = models.URLField(max_length=1024)

    def __str__(self):
        return f"{self.product}'s Image"


class OfficeProductCategory(TimeStampedModel):
    office = models.ForeignKey(Office, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=128)
    slug = models.CharField(max_length=128)
    predefined = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.slug}"

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if "_" not in k}

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ["office", "name"]

    @classmethod
    def office_product_categories_mapper(cls, office):
        if isinstance(office, Office):
            objs = cls.objects.filter(office=office)
        else:
            objs = cls.objects.filter(office_id=office)
        return {product_category["slug"]: product_category["id"] for product_category in objs.values("id", "slug")}


class OfficeProduct(TimeStampedModel):
    """
    This model is actually used for storing products fetched from search result.
    prices will vary depending on vendor account, so we follow this inheritance
    """

    office = models.ForeignKey(Office, on_delete=models.CASCADE, related_name="products", db_index=True)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, null=True, blank=True, related_name="office_products"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    product_vendor_status = models.CharField(max_length=512, null=True, blank=True)
    office_category = models.ForeignKey(ProductCategory, null=True, blank=True, on_delete=models.SET_NULL)
    office_product_category = models.ForeignKey(
        OfficeProductCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    previous_office_product_category = models.BigIntegerField(null=True, blank=True)
    last_order_date = models.DateField(null=True, blank=True)
    last_order_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    last_price_updated = models.DateTimeField(null=True, blank=True, db_index=True)
    price_expiration = models.DateTimeField(null=True, blank=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, null=True, blank=True)
    nickname = models.CharField(max_length=128, null=True, blank=True)
    image_url = models.ImageField(null=True, blank=True, upload_to="offices")
    is_favorite = models.BooleanField(default=False)
    is_inventory = models.BooleanField(default=False)
    # The following field will exist in database,
    # but we can't have it explicitly in model until the following PR
    # is merged in Django codebase and released:
    # https://github.com/django/django/pull/16417
    # nn_vector = SearchVectorField(null=True, blank=True, help_text="Nickname search vector")

    def __str__(self):
        return f"{self.product} for {self.office}"

    class Meta:
        unique_together = ["office", "product"]
        # These indexes will exist in DB, but they won't be
        # available from model, due to the reasons above
        # indexes = [
        #     GinIndex(fields=["office", "nn_vector"])
        # ]

    @property
    def recent_product(self):
        if self.last_price_updated and (timezone.now() - self.last_price_updated).days > 10:
            return self.price

    @classmethod
    def from_dataclass(cls, vendor, dict_data):
        return cls.objects.create(vendor=vendor, **dict_data)

    def to_dataclass(self):
        return ProductDataClass.from_dict(
            {
                "product_id": self.product.product_id,
                "name": self.product.name,
                "description": self.product.description,
                "url": self.product.url,
                "images": [{"image": image.image} for image in self.product.images.all()],
                "price": self.price,
                "vendor": {
                    "id": self.product.vendor.id,
                    "name": self.product.vendor.name,
                    "slug": self.product.vendor.slug,
                    "url": self.product.vendor.url,
                    "logo": self.product.vendor.logo,
                },
            }
        )


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
    status = models.CharField(max_length=100, choices=OrderStatus.choices, default=OrderStatus.OPEN)
    order_type = models.CharField(max_length=100)

    objects = models.Manager()
    current_months = OrderMonthManager()

    class Meta:
        ordering = ("-order_date", "-updated_at")

    def __str__(self):
        return f"{self.office.name}(#{self.pk})"


class VendorOrder(TimeStampedModel):
    order = FlexibleForeignKey(Order, related_name="vendor_orders")
    vendor = FlexibleForeignKey(Vendor)
    vendor_order_id = models.CharField(max_length=100)
    vendor_order_reference = models.CharField(max_length=128, null=True, blank=True)
    nickname = models.CharField(max_length=128, null=True, blank=True)
    total_amount = models.DecimalField(decimal_places=2, max_digits=10)
    total_items = models.IntegerField(default=1)
    currency = models.CharField(max_length=100, default="USD")
    order_date = models.DateField()
    status = models.CharField(max_length=100, choices=OrderStatus.choices, default=OrderStatus.OPEN)
    vendor_status = models.CharField(max_length=100, null=True, blank=True)
    products = models.ManyToManyField(Product, through="VendorOrderProduct")
    invoice_link = models.URLField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        related_name="approved_orders",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    rejected_reason = models.TextField(null=True, blank=True)
    shipping_option = models.ForeignKey(
        ShippingMethod, related_name="vo_shipping_option", on_delete=models.SET_NULL, null=True, blank=True
    )

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

    @property
    def is_invoice_available(self):
        """
        - ultradent: we use order_id to download invoice, orders with digit-format vendor_order_id have invoices
        """
        if self.total_amount == 0:
            return False

        if self.vendor.slug == "ultradent":
            return self.vendor_order_id.isdigit()
        return bool(self.invoice_link)


class VendorOrderProduct(TimeStampedModel):
    class RejectReason(models.TextChoices):
        NOT_NEEDED = "noneed", "Not Needed"
        WRONG_ITEM = "wrong", "Wrong Item"
        EXPENSIVE = "expensive", "Expensive"
        OTHER = "other", "Other"

    vendor_order = FlexibleForeignKey(VendorOrder, related_name="order_products")
    product = FlexibleForeignKey(Product)
    quantity = models.IntegerField(default=0)
    unit_price = models.DecimalField(decimal_places=2, max_digits=10)
    tracking_link = models.URLField(max_length=512, null=True, blank=True)
    tracking_number = models.URLField(max_length=512, null=True, blank=True)
    status = models.CharField(max_length=100, choices=ProductStatus.choices, null=True, blank=True)
    vendor_status = models.CharField(max_length=100, null=True, blank=True)
    rejected_reason = models.CharField(max_length=128, choices=RejectReason.choices, null=True, blank=True)
    budget_spend_type = models.CharField(
        max_length=64,
        choices=BUDGET_SPEND_TYPE.choices,
        default=BUDGET_SPEND_TYPE.DENTAL_SUPPLY_SPEND_BUDGET,
        null=True,
        blank=True,
        db_index=True,
    )

    # status = models.IntegerField(choices=Status.choices, default=Status.OPEN)

    @classmethod
    def from_dataclass(cls, order, dict_data):
        return cls.objects.create(order=order, **dict_data)

    @property
    def is_trackable(self):
        # return self.status == ProductStatus.SHIPPED and (self.tracking_number or self.tracking_link)
        return bool(self.tracking_number or self.tracking_link)


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
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    save_for_later = models.BooleanField(default=False)
    instant_checkout = models.BooleanField(default=True)
    promotion = FlexibleForeignKey(Promotion, null=True)
    budget_spend_type = models.CharField(
        max_length=64,
        choices=BUDGET_SPEND_TYPE.choices,
        default=BUDGET_SPEND_TYPE.DENTAL_SUPPLY_SPEND_BUDGET,
        null=True,
        blank=True,
        db_index=True,
    )

    class Meta:
        ordering = ("created_at",)
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


class OfficeKeyword(TimeStampedModel):
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


class ProcedureCategoryLink(models.Model):
    summary_slug = models.CharField(max_length=256, null=False, blank=False, default="Empty")
    linked_slugs = ArrayField(models.CharField(max_length=100), null=True, blank=True)
    category_order = models.IntegerField(default=0)
    is_favorite = models.BooleanField(default=False)


class ProcedureQuerySet(models.QuerySet):
    def search(self, text):
        text = remove_dash_between_numerics(text)
        q = SearchQuery(text, config="english")
        return self.filter(Q(procedurecode__search_vector=q))


class ProcedureManager(models.Manager):
    _queryset_class = ProcedureQuerySet

    def search(self, text):
        return self.get_queryset().search(text)


class ProcedureCode(models.Model):
    proccode = models.CharField(max_length=16)
    descript = models.CharField(max_length=256, null=True, blank=True)
    category = models.CharField(max_length=256, null=True, blank=True)
    summary_category = models.ForeignKey(ProcedureCategoryLink, on_delete=models.CASCADE, null=True)
    abbr_desc = models.CharField(max_length=256, null=True, blank=True)
    search_vector = SearchVectorField(null=True, blank=True, help_text="Search vector")

    def __str__(self):
        return str(self.proccode)


class Procedure(models.Model):
    start_date = models.DateField()
    count = models.IntegerField(default=0)
    avgfee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    totfee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    procedurecode = models.ForeignKey(ProcedureCode, on_delete=models.CASCADE)
    office = models.ForeignKey(Office, on_delete=models.CASCADE)
    type = models.CharField(max_length=100, choices=ProcedureType.choices, null=True, blank=True)

    objects = ProcedureManager()

    def __str__(self):
        return f"{self.procedurecode.proccode}_{self.count}"

    class Meta:
        unique_together = ["office", "procedurecode", "start_date", "type"]
        ordering = ["start_date"]
