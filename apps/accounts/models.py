# from django.db import models
# Create your models here.
from datetime import timedelta

from creditcards.models import CardExpiryField, CardNumberField, SecurityCodeField
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from month import Month
from month.models import MonthField

from apps.accounts import managers
from apps.common.models import FlexibleForeignKey, TimeStampedModel
from apps.common.utils import generate_token

# from phonenumber_field.modelfields import PhoneNumberField


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
    logo = models.ImageField(null=True, blank=True, upload_to="vendors")

    def __str__(self):
        return self.name


class Company(TimeStampedModel):
    name = models.CharField(max_length=100)
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
    address = models.CharField(max_length=100, null=True, blank=True)
    postal_code = models.CharField(max_length=100, null=True, blank=True)
    phone_number = models.CharField(max_length=25, null=True, blank=True)
    website = models.CharField(max_length=100, null=True, blank=True)
    logo = models.ImageField(null=True, blank=True, upload_to="offices")
    # Budget & Card Information
    cc_number = CardNumberField("Card Number", null=True, blank=True)
    cc_expiry = CardExpiryField("Expiration Date", null=True, blank=True)
    cc_code = SecurityCodeField("Security Code", null=True, blank=True)

    objects = managers.CompanyMemeberActiveManager()

    def __str__(self):
        return f"{self.company} -> {self.name}"

    @property
    def budget(self):
        current_date = timezone.now().date()
        month = Month(year=current_date.year, month=current_date.month)
        return self.budgets.filter(month=month).first()


class OfficeBudget(TimeStampedModel):
    class BudgetType(models.TextChoices):
        PRODUCTION = "production", "Adjusted Production"
        COLLECTION = "collection", "Collection"

    office = FlexibleForeignKey(Office, related_name="budgets")
    budget_type = models.CharField(max_length=10, choices=BudgetType.choices, default=BudgetType.PRODUCTION)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    spend = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    month = MonthField(auto_now_add=True)

    class Meta:
        ordering = ("-month",)
        unique_together = ["office", "month"]


class OfficeVendor(models.Model):
    vendor = FlexibleForeignKey(Vendor)
    office = FlexibleForeignKey(Office)
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)

    class Meta:
        unique_together = ["office", "vendor"]


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
