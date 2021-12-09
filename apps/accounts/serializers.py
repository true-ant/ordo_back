# from celery.result import AsyncResult
from decimal import Decimal

from creditcards.validators import CCNumberValidator, CSCValidator, ExpiryDateValidator
from django.db import transaction
from django.utils import timezone
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers

from apps.accounts.services.stripe import (
    add_customer_to_stripe,
    create_subscription,
    get_payment_method_token,
)
from apps.common.serializers import Base64ImageField, OptionalSchemeURLValidator

from . import models as m

# from .tasks import fetch_orders_from_vendor


class CompanyMemberSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=m.Company.objects.all(), allow_null=True)
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), allow_null=True)
    role_name = serializers.CharField(source="get_role_display", required=False)

    class Meta:
        model = m.CompanyMember
        exclude = ("token", "token_expires_at")


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Vendor
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


class OfficeSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    company = serializers.PrimaryKeyRelatedField(queryset=m.Company.objects.all(), required=False)
    addresses = OfficeAddressSerializer(many=True, required=False)
    logo = Base64ImageField(required=False)
    vendors = VendorSerializer(many=True, required=False)
    phone_number = PhoneNumberField()
    website = serializers.CharField(validators=[OptionalSchemeURLValidator()])
    cc_number = serializers.CharField(validators=[CCNumberValidator()], write_only=True)
    cc_expiry = serializers.DateField(
        validators=[ExpiryDateValidator()], input_formats=["%m/%y"], format="%m/%y", write_only=True
    )
    cc_code = serializers.CharField(validators=[CSCValidator()], write_only=True)
    budget = OfficeBudgetSerializer()

    class Meta:
        model = m.Office
        fields = "__all__"

    def to_representation(self, instance):
        res = super().to_representation(instance)
        if self.context.get("exclude_vendors"):
            res.pop("vendors")
        return res


class CompanySerializer(serializers.ModelSerializer):
    offices = OfficeSerializer(many=True)

    class Meta:
        model = m.Company
        fields = "__all__"

    def _update_subscription(self, offices, offices_data):
        try:
            for office, office_data in zip(offices, offices_data):
                card_number = office_data.get("cc_number", None)
                expiry = office_data.get("cc_expiry", None)
                cvc = office_data.get("cc_code", None)

                if card_number or expiry or cvc:
                    card_token = get_payment_method_token(card_number=card_number, expiry=expiry, cvc=cvc)
                    if office.cards.filter(card_token=card_token.id).exists():
                        continue

                    _, customer = add_customer_to_stripe(
                        email=self.context["request"].user.email,
                        customer_name=office.name,
                        payment_method_token=card_token,
                    )

                    subscription = create_subscription(customer_id=customer.id)

                    with transaction.atomic():
                        m.Card.objects.create(
                            last4=card_token.card.last4,
                            customer_id=customer.id,
                            card_token=card_token.id,
                            office=office,
                        )
                        m.Subscription.objects.create(
                            subscription_id=subscription.id, office=office, start_on=timezone.now().date()
                        )

        except Exception:
            raise serializers.ValidationError({"message": "Invalid Card Information"})

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
            )

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
    )
    email = serializers.EmailField()


class CompanyMemberBulkInviteSerializer(serializers.Serializer):
    on_boarding_step = serializers.IntegerField()
    members = serializers.ListField(child=CompanyMemberInviteSerializer(), allow_empty=False)


class CompanyMemberUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=(
            m.User.Role.ADMIN,
            m.User.Role.USER,
        )
    )


class OfficeVendorSerializer(serializers.ModelSerializer):
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), allow_null=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = m.OfficeVendor
        fields = "__all__"


class OfficeVendorListSerializer(serializers.ModelSerializer):
    vendor = VendorSerializer()
    # status = serializers.SerializerMethodField()

    class Meta:
        model = m.OfficeVendor
        exclude = (
            "office",
            "password",
        )

    #
    # def get_status(self, instance):
    #     if not instance.task_id:
    #         return "SUCCESS"
    #     ar: AsyncResult = fetch_orders_from_vendor.AsyncResult(instance.task_id)
    #     return ar.status


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
        company_member = m.CompanyMember.objects.select_related("company").filter(user=instance).first()
        if company_member:
            return CompanySerializer(company_member.company, context=self.context).data
