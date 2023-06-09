# from celery.result import AsyncResult
from decimal import Decimal

from creditcards.validators import CCNumberValidator, CSCValidator, ExpiryDateValidator
from django.db import transaction
from django.utils import timezone
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.accounts.services.stripe import (
    add_customer_to_stripe,
    create_subscription,
    get_payment_method_token,
)
from apps.common.serializers import Base64ImageField, OptionalSchemeURLValidator

from ..utils.misc import normalize_decimal_values
from . import models as m

# from .tasks import fetch_orders_from_vendor


class VendorLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Vendor
        fields = "__all__"


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Vendor
        fields = "__all__"


class OpenDentalKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.OpenDentalKey
        fields = "__all__"


class BudgetSerializerV1(serializers.ModelSerializer):
    class Meta:
        model = m.Budget
        fields = (
            "id",
            "office",
            "month",
            "adjusted_production",
            "collection",
        )

    def get_remaining_budget(self, result):
        TWO_DECIMAL_PLACES = Decimal(10) ** -2
        return {
            "dental": (result["dental_budget"] - result["dental_spend"]).quantize(TWO_DECIMAL_PLACES),
            "office": (result["office_budget"] - result["office_spend"]).quantize(TWO_DECIMAL_PLACES),
        }

    def to_representation(self, instance: m.Budget):
        result = super().to_representation(instance)
        for subaccount in instance.subaccounts.all():
            category_slug = subaccount.category.slug
            if category_slug in ("dental", "office"):
                key_prefix = f"{category_slug}"
                key_data = {
                    "budget_type": subaccount.budget_type,
                    "total_budget": subaccount.total_budget,
                    "percentage": subaccount.percentage,
                    "budget": subaccount.budget_,
                    "spend": subaccount.spend,
                }
                result.update({f"{key_prefix}_{key}": value for key, value in key_data.items()})
            elif category_slug == "misc":
                result["miscellaneous_spend"] = subaccount.spend
            else:
                continue
        remaining_budget = self.get_remaining_budget(result)
        return normalize_decimal_values({**result, "remaining_budget": remaining_budget})


class BudgetSerializerV2(serializers.ModelSerializer):
    class Meta:
        model = m.Budget
        fields = "__all__"


class OfficeBudgetSerializer(serializers.ModelSerializer):
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), required=False)
    # spend = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    remaining_budget = serializers.SerializerMethodField()

    class Meta:
        model = m.OfficeBudget
        exclude = ("created_at", "updated_at")

    def get_remaining_budget(self, instance):
        TWO_DECIMAL_PLACES = Decimal(10) ** -2
        return {
            "dental": (instance.dental_budget - instance.dental_spend).quantize(TWO_DECIMAL_PLACES),
            "office": (instance.office_budget - instance.office_spend).quantize(TWO_DECIMAL_PLACES),
        }


class OfficeBudgetChartSerializer(serializers.Serializer):
    month = serializers.CharField()
    dental_budget = serializers.DecimalField(max_digits=8, decimal_places=2)
    dental_spend = serializers.DecimalField(max_digits=8, decimal_places=2)
    office_budget = serializers.DecimalField(max_digits=8, decimal_places=2)
    office_spend = serializers.DecimalField(max_digits=8, decimal_places=2)


class OfficeAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.OfficeAddress
        exclude = ("office",)


class OfficeSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.OfficeSetting
        exclude = ("office",)


class BaseOfficeSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    company = serializers.PrimaryKeyRelatedField(queryset=m.Company.objects.all(), required=False)
    addresses = OfficeAddressSerializer(many=True, required=False)
    logo = Base64ImageField(required=False)
    vendors = VendorLiteSerializer(many=True, required=False)
    phone_number = PhoneNumberField()
    website = serializers.CharField(validators=[OptionalSchemeURLValidator()], allow_null=True)
    cc_number = serializers.CharField(validators=[CCNumberValidator()], write_only=True)
    cc_expiry = serializers.DateField(
        validators=[ExpiryDateValidator()], input_formats=["%m/%y"], format="%m/%y", write_only=True
    )
    coupon = serializers.CharField(write_only=True, required=False)
    cc_code = serializers.CharField(validators=[CSCValidator()], write_only=True)
    settings = OfficeSettingSerializer(read_only=True)
    name = serializers.CharField()
    dental_api = OpenDentalKeySerializer()
    practice_software = serializers.CharField()

    class Meta:
        model = m.Office
        fields = "__all__"

    def to_representation(self, instance):
        res = super().to_representation(instance)
        if self.context.get("exclude_vendors"):
            res.pop("vendors")
        return res


class OfficeSerializerV1(BaseOfficeSerializer):
    budget = BudgetSerializerV1()


class OfficeSerializerV2(BaseOfficeSerializer):
    budget = BudgetSerializerV2()


class CompanyMemberSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=m.Company.objects.all(), allow_null=True)
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all())
    role_name = serializers.CharField(source="get_role_display", required=False)

    def validate(self, attrs):
        company = attrs["company"]
        office = attrs["office"]
        if office.company_id != company.id:
            raise ValidationError("Office must belong to company")
        return attrs

    def to_representation(self, instance: m.CompanyMember):
        ret = super().to_representation(instance)
        request = self.context["request"]
        if request.version == "1.0":
            office_serializer_class = OfficeSerializerV1
        elif request.version == "2.0":
            office_serializer_class = OfficeSerializerV2
        else:
            raise ValueError("Version is not supported")
        ret["office"] = office_serializer_class(instance=instance.office, context=self.context).data

        return ret

    class Meta:
        model = m.CompanyMember
        exclude = ("token", "token_expires_at")


class BaseCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Company
        fields = "__all__"

    def _update_subscription(self, offices, offices_data):
        try:
            for office, office_data in zip(offices, offices_data):
                card_number = office_data.get("cc_number", None)
                expiry = office_data.get("cc_expiry", None)
                cvc = office_data.get("cc_code", None)
                coupon = office_data.get("coupon", None)

                if card_number or expiry or cvc:
                    card_token = get_payment_method_token(card_number=card_number, expiry=expiry, cvc=cvc)
                    if office.cards.filter(card_token=card_token.id).exists():
                        continue

                    _, customer = add_customer_to_stripe(
                        email=self.context["request"].user.email,
                        customer_name=office.name,
                        payment_method_token=card_token,
                    )

                    subscription = create_subscription(customer_id=customer.id, promocode=coupon)

                    with transaction.atomic():
                        m.Card.objects.create(
                            last4=card_token.card.last4,
                            customer_id=customer.id,
                            card_token=card_token.id,
                            office=office,
                        )
                        m.Subscription.objects.create(
                            subscription_id=subscription.id, office=office, start_on=timezone.localtime().date()
                        )

        except Exception as e:
            raise serializers.ValidationError({"message": e})

    def _create_or_update_office(self, company, **kwargs):
        office_id = kwargs.pop("id", None)
        addresses = kwargs.pop("addresses", [])
        if office_id:
            office = m.Office.objects.get(id=office_id, company=company)
            for key, value in kwargs.items():
                if not hasattr(office, key):
                    continue
                setattr(office, key, value)
            office.save()
        else:
            office = m.Office.objects.create(
                company=company,
                name=kwargs["name"],
                phone_number=kwargs.get("phone_number"),
                website=kwargs.get("website"),
                practice_software=kwargs.get("practice_software"),
            )
            m.OfficeSetting.objects.create(office=office)

        for address in addresses:
            address_id = address.pop("id", [])
            if address_id:
                office_address = m.OfficeAddress.objects.get(id=address_id)
                for key, value in address.items():
                    if not hasattr(office, key):
                        continue
                    setattr(office_address, key, value)
                office_address.save()
            else:
                m.OfficeAddress.objects.create(office=office, **address)
        return office

    def create(self, validated_data):
        offices_data = validated_data.pop("offices", None)
        offices = []
        with transaction.atomic():
            company = m.Company.objects.create(**validated_data)
            for office in offices_data:
                offices.append(self._create_or_update_office(company, **office))

            m.Office.objects.bulk_create(offices)

        self._update_subscription(offices, offices_data)
        return company

    def update(self, instance, validated_data):
        offices_data = validated_data.pop("offices", [])
        offices = []
        with transaction.atomic():
            for key, value in validated_data.items():
                if key == "on_boarding_step" and instance.on_boarding_step > value:
                    continue
                setattr(instance, key, value)

            if validated_data:
                instance.save()

            for office in offices_data:
                offices.append(self._create_or_update_office(instance, **office))

        self._update_subscription(offices, offices_data)
        return instance

    def to_representation(self, instance):
        res = super().to_representation(instance)
        if self.context.get("exclude_offices"):
            res.pop("offices")
        return res


class CompanySerializerV1(BaseCompanySerializer):
    offices = OfficeSerializerV1(many=True)


class CompanySerializerV2(BaseCompanySerializer):
    offices = OfficeSerializerV2(many=True)


class UserSignupSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField()
    company_name = serializers.CharField()
    token = serializers.CharField(required=False)


class CompanyMemberInviteSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=(
            m.User.Role.ADMIN,
            m.User.Role.USER,
        )
    )
    offices = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), required=False),
        required=False,
        allow_null=True,
    )
    email = serializers.EmailField()


class CompanyMemberBulkInviteSerializer(serializers.Serializer):
    on_boarding_step = serializers.IntegerField(required=False)
    members = serializers.ListField(child=CompanyMemberInviteSerializer(), allow_empty=False)


class CompanyMemberUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=(
            m.User.Role.ADMIN,
            m.User.Role.USER,
        )
    )


class ShippingMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.ShippingMethod
        fields = "__all__"


class OfficeVendorSerializer(serializers.ModelSerializer):
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), allow_null=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = m.OfficeVendor
        fields = "__all__"
        extra_kwargs = {"shipping_options": {"read_only": True}}


class OfficeVendorListSerializer(serializers.ModelSerializer):
    vendor = VendorLiteSerializer()
    default_shipping_option = ShippingMethodSerializer(read_only=True)
    shipping_options = ShippingMethodSerializer(many=True, read_only=True)

    class Meta:
        model = m.OfficeVendor
        exclude = (
            "office",
            "password",
        )


class UserSerializer(serializers.ModelSerializer):
    company = serializers.SerializerMethodField()
    avatar = Base64ImageField()

    class Meta:
        model = m.User
        exclude = (
            "password",
            "is_superuser",
            "is_staff",
            "groups",
            "user_permissions",
        )

    def get_company(self, instance):
        company = m.Company.objects.filter(members__user=instance).first()
        request = self.context["request"]
        if request.version == "1.0":
            company_serializer_class = CompanySerializerV1
        elif request.version == "2.0":
            company_serializer_class = CompanySerializerV2
        else:
            raise ValidationError("Unsupported version")
        if company:
            return company_serializer_class(company, context=self.context).data


class VendorRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.VendorRequest
        fields = ("id", "company", "vendor_name", "description")
        extra_kwargs = {"company": {"write_only": True}}
