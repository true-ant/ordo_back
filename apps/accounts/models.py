# from django.db import models
# Create your models here.
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Manager
from django.utils import timezone
from django_extensions.db.fields import AutoSlugField
from month import Month
from month.models import MonthField
from phonenumber_field.modelfields import PhoneNumberField

from apps.accounts import managers
from apps.common.models import FlexibleForeignKey, TimeStampedModel
from apps.common.utils import generate_token

INVITE_EXPIRES_DAYS = 7


class User(AbstractUser):
    class Role(models.IntegerChoices):
        OWNER = 0
        ADMIN = 1
        USER = 2

    role = models.IntegerField(choices=Role.choices, default=Role.ADMIN)
    avatar = models.ImageField(null=True, blank=True, upload_to="users")

    @property
    def full_name(self):
        return self.get_full_name()


class Vendor(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    url = models.CharField(max_length=100)
    logo = models.URLField(null=True, blank=True)
    shipping_options = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.name

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if "_" not in k}


class Company(TimeStampedModel):
    name = models.CharField(max_length=100)
    slug = AutoSlugField(populate_from=["name"])
    on_boarding_step = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    billing_together = models.BooleanField(default=False)

    objects = managers.CompanyMemeberActiveManager()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Companies"


class Office(TimeStampedModel):
    company = FlexibleForeignKey(Company, related_name="offices")
    vendors = models.ManyToManyField(Vendor, through="OfficeVendor")
    is_active = models.BooleanField(default=True)

    # Basic Information
    name = models.CharField(max_length=100)
    slug = AutoSlugField(populate_from=["name"])
    phone_number = PhoneNumberField(null=True, blank=True)
    website = models.URLField(max_length=100, null=True, blank=True)
    logo = models.ImageField(null=True, blank=True, upload_to="offices")
    # Budget & Card Information

    objects = managers.CompanyMemeberActiveManager()

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return self.name

    @property
    def shipping_zip_code(self):
        address = self.addresses.filter(address_type="billing").first()
        return address.zip_code if address else None

    @property
    def shipping_address(self):
        address = self.addresses.filter(address_type="billing").first()
        if address:
            return f"{address.address} {address.city}, {address.zip_code}"
        return ""

    @property
    def budget(self):
        current_date = timezone.now().date()
        month = Month(year=current_date.year, month=current_date.month)
        return self.budgets.filter(month=month).first()

    @property
    def active_subscription(self):
        return self.subscriptions.filter(cancelled_on__isnull=True).order_by("-updated_at").first()

    @property
    def card(self):
        return self.cards.first()


class Card(TimeStampedModel):
    last4 = models.CharField(max_length=5, blank=True)
    customer_id = models.CharField(max_length=70, blank=True)
    card_token = models.CharField(max_length=100, blank=True)
    office = models.ForeignKey(Office, null=True, blank=True, on_delete=models.CASCADE, related_name="cards")

    def __str__(self):
        return self.last4


class OfficeAddress(TimeStampedModel):
    class AddressType(models.TextChoices):
        ADDRESS = "address", "Address"
        BILLING_ADDRESS = "billing", "Billing Address"

    office = FlexibleForeignKey(Office, related_name="addresses")
    address_type = models.CharField(max_length=10, choices=AddressType.choices, default=AddressType.ADDRESS)
    address = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=100)

    class Meta:
        ordering = ("address_type",)


class OfficeBudget(TimeStampedModel):
    class BudgetType(models.TextChoices):
        PRODUCTION = "production", "Adjusted Production"
        COLLECTION = "collection", "Collection"

    office = FlexibleForeignKey(Office, related_name="budgets")
    # dental_* is used for managing budgets for net, henry and dental suppliers
    dental_budget_type = models.CharField(max_length=10, choices=BudgetType.choices, default=BudgetType.PRODUCTION)
    dental_total_budget = models.DecimalField(max_digits=10, decimal_places=2)
    dental_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    dental_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    dental_spend = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # office_* is used for managing budgets for amazon
    office_budget_type = models.CharField(max_length=10, choices=BudgetType.choices, default=BudgetType.PRODUCTION)
    office_total_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    office_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    office_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    office_spend = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    miscellaneous_spend = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    month = MonthField()

    class Meta:
        ordering = ("-month",)
        unique_together = ["office", "month"]

    def __str__(self):
        return f"{self.office}'s {self.month} budget"


class OfficeSetting(TimeStampedModel):
    office = models.OneToOneField(Office, related_name="settings", on_delete=models.CASCADE)
    requires_approval_notification_for_all_orders = models.BooleanField(default=False)
    budget_threshold = models.DecimalField(default=0, decimal_places=1, max_digits=10)


class OfficeVendor(TimeStampedModel):
    vendor = FlexibleForeignKey(Vendor, related_name="connected_offices")
    office = FlexibleForeignKey(Office, related_name="connected_vendors")
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    task_id = models.CharField(max_length=64, null=True, blank=True)
    vendor_phone_number = PhoneNumberField(null=True, blank=True)
    vendor_email = models.EmailField(null=True, blank=True)
    representative_full_name = models.CharField(max_length=256, null=True, blank=True)
    representative_email = models.EmailField(null=True, blank=True)
    representative_phone_number = PhoneNumberField(null=True, blank=True)

    class Meta:
        ordering = ("vendor__name",)
        unique_together = [
            ["office", "vendor"],
            ["vendor", "username"],
        ]


def default_expires_at():
    return timezone.now() + timedelta(days=INVITE_EXPIRES_DAYS)


class CompanyMember(TimeStampedModel):
    class InviteStatus(models.IntegerChoices):
        INVITE_SENT = 0
        INVITE_APPROVED = 1
        INVITE_DECLINED = 2

    company = FlexibleForeignKey(Company)
    user = FlexibleForeignKey(User, null=True)
    role = models.IntegerField(choices=User.Role.choices, default=User.Role.ADMIN)
    office = FlexibleForeignKey(Office, null=True)
    email = models.EmailField(null=False, blank=False)
    invited_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="invites")
    invite_status = models.IntegerField(choices=InviteStatus.choices, default=InviteStatus.INVITE_SENT)
    date_joined = models.DateTimeField(null=True, blank=True)
    token = models.CharField(max_length=64, default=generate_token, unique=True)
    token_expires_at = models.DateTimeField(default=default_expires_at)
    is_active = models.BooleanField(default=True)

    objects = managers.CompanyMemeberActiveManager()
    alls = managers.Manager()

    def regenerate_token(self):
        self.key = generate_token()
        self.refresh_expires_at()

    def refresh_expires_at(self):
        self.token_expires_at = timezone.now() + timedelta(days=INVITE_EXPIRES_DAYS)

    # class Meta:
    #     unique_together = ["company", "email"]

    def __str__(self):
        return f"{self.company} - {self.email}"


class Subscription(TimeStampedModel):
    office = models.ForeignKey(Office, on_delete=models.CASCADE, related_name="subscriptions")
    subscription_id = models.CharField(max_length=128)
    start_on = models.DateField()
    cancelled_on = models.DateField(null=True, blank=True)

    objects = Manager()
    actives = managers.ActiveSubscriptionManager()

    def __str__(self):
        return f"{self.office.name}' Subscription"


class VendorRequest(TimeStampedModel):
    company = models.ForeignKey(
        Company, blank=True, null=True, on_delete=models.SET_NULL, related_name="vendor_requests"
    )
    vendor_name = models.CharField(max_length=128)
    description = models.TextField(null=True, blank=True)
