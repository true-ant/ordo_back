# from django.db import models
# Create your models here.
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Case, Manager, OuterRef, Subquery, Value, When
from django.db.models.functions import JSONObject
from django.utils import timezone
from django_extensions.db.fields import AutoSlugField
from phonenumber_field.modelfields import PhoneNumberField

import apps.accounts.managers.company_member
import apps.accounts.managers.subscription
from apps.accounts.managers.vendor import VendorManager
from apps.common.models import FlexibleForeignKey, TimeStampedModel
from apps.common.month import Month
from apps.common.month.models import MonthField
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
    enabled = models.BooleanField(default=True)

    objects = VendorManager()

    def __str__(self):
        return self.name

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if "_" not in k}


class OpenDentalKey(models.Model):
    key = models.CharField(max_length=30)

    def __str__(self):
        return self.key


class Company(TimeStampedModel):
    name = models.CharField(max_length=100)
    slug = AutoSlugField(populate_from=["name"])
    on_boarding_step = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    billing_together = models.BooleanField(default=False)

    objects = apps.accounts.managers.company_member.CompanyMemberActiveManager()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Companies"


class Office(TimeStampedModel):
    class ManageType(models.TextChoices):
        OPENDENTAL = "open_dental", "Open Dental"
        DENTIRX = "dentirx", "Dentirx"
        EAGLESOFT = "eaglesoft", "EagleSoft"
        CURVE = "curve", "Curve"
        CARESTACK = "carestack", "Carestack"
        MACPRACTICE = "macpractice", "MacPractice"
        OTHER = "other", "Other"

    company = FlexibleForeignKey(Company, related_name="offices")
    vendors = models.ManyToManyField(Vendor, through="OfficeVendor")
    is_active = models.BooleanField(default=True)

    # Basic Information
    name = models.CharField(max_length=100)
    slug = AutoSlugField(populate_from=["name"])
    phone_number = PhoneNumberField(null=True, blank=True)
    website = models.URLField(max_length=100, null=True, blank=True)
    logo = models.ImageField(null=True, blank=True, upload_to="offices")
    dental_api = models.OneToOneField(OpenDentalKey, on_delete=models.SET_NULL, null=True)
    practice_software = models.CharField(max_length=50, choices=ManageType.choices, default=ManageType.OPENDENTAL)
    # Budget & Card Information

    objects = apps.accounts.managers.company_member.CompanyMemberActiveManager()

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
        if hasattr(self, "prefetched_current_budget"):
            budget = self.prefetched_current_budget
            if budget:
                return budget[0]
            return None
        current_date = timezone.localtime().date()
        month = Month(year=current_date.year, month=current_date.month)
        return Budget.objects.filter(office=self, month=month).first()

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


class BudgetType(models.TextChoices):
    PRODUCTION = "production", "Adjusted Production"
    COLLECTION = "collection", "Collection"


class OfficeBudget(TimeStampedModel):
    office = FlexibleForeignKey(Office, related_name="budgets")
    # dental_* is used for managing budgets for net, henry and dental suppliers
    dental_budget_type = models.CharField(max_length=10, choices=BudgetType.choices, default=BudgetType.PRODUCTION)
    dental_total_budget = models.DecimalField(max_digits=10, decimal_places=2)
    dental_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    dental_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    dental_spend = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    adjusted_production = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    collection = models.DecimalField(max_digits=10, decimal_places=2, default=0)

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
        return f"{self.office_id} {self.month} budget"


class BasisType(models.IntegerChoices):
    NONE = 0, "No basis"
    PRODUCTION = 1, "Adjusted Production"
    COLLECTION = 2, "Collection"


BASIS2CATEGORY = {BasisType.PRODUCTION: BudgetType.PRODUCTION, BasisType.COLLECTION: BudgetType.COLLECTION}


class BudgetQueryset(models.QuerySet):
    def compatible_with_office_budget(self):
        dental_subaccount, office_subaccount, misc_subaccount = [
            Subaccount.objects.filter(budget_id=OuterRef("pk"), category__slug=slug).values(
                data=JSONObject(
                    basis="basis",
                    percentage="percentage",
                    spend="spend",
                    budget_type=Case(
                        When(basis=BasisType.PRODUCTION, then=Value(BudgetType.PRODUCTION)),
                        When(basis=BasisType.COLLECTION, then=Value(BudgetType.COLLECTION)),
                        output_field=models.CharField(),
                    ),
                    total_budget=Case(
                        When(basis=BasisType.PRODUCTION, then=OuterRef("adjusted_production")),
                        When(basis=BasisType.COLLECTION, then=OuterRef("collection")),
                        output_field=models.CharField(),
                    ),
                )
            )[:1]
            for slug in ("dental", "office", "misc")
        ]
        return self.annotate(
            dental_sub=Subquery(dental_subaccount),
            office_sub=Subquery(office_subaccount),
            misc_sub=Subquery(misc_subaccount),
        )


class CompatibleBudgetMixin:
    def __getattr__(self, item: str):
        if item == "miscellaneous_spend":
            return self.misc_sub["spend"]
        elif item.startswith("dental_"):
            rest = item.removeprefix("dental_")
            return self.dental_sub[rest]
        elif item.startswith("office_"):
            rest = item.removeprefix("office_")
            return self.office_sub[rest]

    @property
    def dental_budget(self):
        return self.dental_total_budget * self.dental_percentage / 100

    @property
    def office_budget(self):
        return self.office_total_budget * self.office_percentage / 100


class Budget(models.Model, CompatibleBudgetMixin):
    office = models.ForeignKey(Office, on_delete=models.PROTECT, related_name="budget_set")
    month = MonthField()

    adjusted_production = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    collection = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    objects = BudgetQueryset.as_manager()


class BudgetCategory(models.Model):
    office = models.ForeignKey(Office, on_delete=models.PROTECT, related_name="budget_categories")

    # Slug field for the category. It has special meaning and some predefined values
    # dental - general dental budget category
    # office - general office budget category
    # misc - miscelanneous budget category
    # vendor-<vendor_slug> - vendor specific category
    slug = models.SlugField(max_length=30)

    name = models.CharField(max_length=60)
    is_custom = models.BooleanField(default=False)

    def __str__(self):
        if self.is_custom:
            name = f"{self.name}"
        else:
            name = f"[{self.name}]"
        basis = self.get_basis_display()
        return f"{name} ({basis})"


class Subaccount(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.PROTECT, related_name="subaccounts")
    basis = models.IntegerField(choices=BasisType.choices)
    category = models.ForeignKey(BudgetCategory, on_delete=models.PROTECT, related_name="subaccounts")
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    spend = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def budget_type(self):
        return BASIS2CATEGORY.get(self.basis)

    @property
    def total_budget(self):
        if self.basis == BasisType.COLLECTION:
            return self.budget.collection
        elif self.basis == BasisType.PRODUCTION:
            return self.budget.adjusted_production
        return None

    @property
    def budget_(self):
        return (Decimal(self.total_budget * self.percentage) / Decimal(100)).quantize(Decimal(10) ** -2)


class OfficeSetting(TimeStampedModel):
    office = models.OneToOneField(Office, related_name="settings", on_delete=models.CASCADE)
    enable_order_approval = models.BooleanField(default=True)
    requires_approval_notification_for_all_orders = models.BooleanField(default=False)
    budget_threshold = models.DecimalField(default=0, decimal_places=1, max_digits=10)
    percentage_threshold = models.DecimalField(default=0, decimal_places=2, max_digits=5)


class ShippingMethod(models.Model):
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    value = models.CharField(max_length=255, null=True, blank=True)


class OfficeVendor(TimeStampedModel):
    vendor = FlexibleForeignKey(Vendor, related_name="connected_offices")
    office = FlexibleForeignKey(Office, related_name="connected_vendors")
    # account id on vendor side, account id is required for dental city.
    account_id = models.CharField(max_length=128, null=True, blank=True)
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    login_success = models.BooleanField(default=True)
    task_id = models.CharField(max_length=64, null=True, blank=True)
    vendor_phone_number = PhoneNumberField(null=True, blank=True)
    vendor_email = models.EmailField(null=True, blank=True)
    representative_full_name = models.CharField(max_length=256, null=True, blank=True)
    representative_email = models.EmailField(null=True, blank=True)
    representative_phone_number = PhoneNumberField(null=True, blank=True)
    shipping_options = models.ManyToManyField(ShippingMethod, related_name="ov_shipping_options")
    default_shipping_option = models.ForeignKey(
        ShippingMethod, related_name="ov_default_shipping_option", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ("vendor__name",)
        unique_together = [
            ["office", "vendor"],
            ["vendor", "username"],
        ]


def default_expires_at():
    return timezone.localtime() + timedelta(days=INVITE_EXPIRES_DAYS)


class CompanyMember(TimeStampedModel):
    class InviteStatus(models.IntegerChoices):
        INVITE_SENT = 0
        INVITE_APPROVED = 1
        INVITE_DECLINED = 2

    company = FlexibleForeignKey(Company, related_name="members")
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

    objects = apps.accounts.managers.company_member.CompanyMemberActiveManager()

    def regenerate_token(self):
        self.key = generate_token()
        self.refresh_expires_at()

    def refresh_expires_at(self):
        self.token_expires_at = timezone.localtime() + timedelta(days=INVITE_EXPIRES_DAYS)

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
    actives = apps.accounts.managers.subscription.ActiveSubscriptionManager()

    def __str__(self):
        return f"{self.office.name}' Subscription"


class VendorRequest(TimeStampedModel):
    company = models.ForeignKey(
        Company, blank=True, null=True, on_delete=models.SET_NULL, related_name="vendor_requests"
    )
    vendor_name = models.CharField(max_length=128)
    description = models.TextField(null=True, blank=True)
