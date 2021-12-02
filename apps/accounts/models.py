# from django.db import models
# Create your models here.
from datetime import timedelta

from creditcards.models import CardExpiryField, CardNumberField, SecurityCodeField
from django.contrib.auth.models import AbstractUser
from django.db import models
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


class Vendor(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    url = models.CharField(max_length=100)
    logo = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.name

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if "_" not in k}


class Company(TimeStampedModel):
    name = models.CharField(max_length=100)
    slug = AutoSlugField(populate_from=["name"])
    on_boarding_step = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

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
    cc_number = CardNumberField("Card Number", null=True, blank=True)
    cc_expiry = CardExpiryField("Expiration Date", null=True, blank=True)
    cc_code = SecurityCodeField("Security Code", null=True, blank=True)

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
    def budget(self):
        current_date = timezone.now().date()
        month = Month(year=current_date.year, month=current_date.month)
        return self.budgets.filter(month=month).first()


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

    month = MonthField()

    class Meta:
        ordering = ("-month",)
        unique_together = ["office", "month"]

    def __str__(self):
        return f"{self.office}'s {self.month} budget"


class OfficeVendor(models.Model):
    vendor = FlexibleForeignKey(Vendor, related_name="connected_offices")
    office = FlexibleForeignKey(Office, related_name="connected_vendors")
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    task_id = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
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

    class Meta:
        unique_together = ["company", "email"]
