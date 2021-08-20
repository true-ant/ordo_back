# from django.db import models

# Create your models here.
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.common.models import FlexibleForeignKey, TimeStampedModel
from apps.common.utils import generate_token

INVITE_EXPIRES_DAYS = 7


class User(AbstractUser):
    class Role(models.IntegerChoices):
        OWNER = 0
        ADMIN = 1
        USER = 2

    role = models.IntegerField(choices=Role.choices, default=Role.USER)


class Company(TimeStampedModel):
    name = models.CharField(max_length=100)
    on_boarding_step = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Companies"


class Vendor(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    url = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Office(TimeStampedModel):
    company = FlexibleForeignKey(Company, related_name="offices")
    # Basic Information
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=100, null=True, blank=True)
    phone_number = models.CharField(max_length=100, null=True, blank=True)
    website = models.CharField(max_length=100, null=True, blank=True)
    # Budget & Card Information
    budget = models.PositiveIntegerField(default=0)
    cc_number = models.CharField(max_length=20, null=True, blank=True)
    cc_expiry = models.CharField(max_length=20, null=True, blank=True)
    cc_code = models.CharField(max_length=20, null=True, blank=True)
    # Billing address
    billing_address = models.CharField(max_length=100, null=True, blank=True)
    # Shipping Address
    shipping_address = models.CharField(max_length=100, null=True, blank=True)
    shipping_address_zipcode = models.CharField(max_length=100, null=True, blank=True)
    vendors = models.ManyToManyField(Vendor, through="OfficeVendor")

    def __str__(self):
        return self.company


class OfficeVendor(models.Model):
    vendor = FlexibleForeignKey(Vendor, related_name="vendors")
    office = FlexibleForeignKey(Office, related_name="offices")
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)


class CompanyMember(TimeStampedModel):
    class InviteStatus(models.IntegerChoices):
        INVITE_SENT = 0
        INVITE_APPROVED = 1
        INVITE_DECLINED = 2

    company = FlexibleForeignKey(Company)
    user = FlexibleForeignKey(User, null=True)
    office = FlexibleForeignKey(Office, null=True)
    email = models.EmailField()
    invite_status = models.IntegerField(choices=InviteStatus.choices, default=InviteStatus.INVITE_SENT)
    date_joined = models.DateTimeField(null=True, blank=True)
    token = models.CharField(max_length=64, default=generate_token, unique=True)
    token_expires_at = models.DateTimeField(default=None, null=True)

    class Meta:
        unique_together = ["company", "email"]

    def regenerate_token(self):
        self.key = generate_token()
        self.refresh_expires_at()

    def refresh_expires_at(self):
        self.token_expires_at = timezone.now() + timedelta(days=INVITE_EXPIRES_DAYS)
