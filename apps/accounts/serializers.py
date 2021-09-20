from creditcards.validators import CCNumberValidator, CSCValidator, ExpiryDateValidator
from django.db import transaction

# from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers

from apps.common.serializers import Base64ImageField

from . import models as m


class CompanyMemberSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=m.Company.objects.all(), allow_null=True)
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), allow_null=True)
    role_name = serializers.CharField(source="get_role_display", required=False)

    class Meta:
        model = m.CompanyMember
        exclude = ("token", "token_expires_at")


class VendorSerializer(serializers.ModelSerializer):
    logo = Base64ImageField()

    class Meta:
        model = m.Vendor
        fields = "__all__"


class OfficeBudgetSerializer(serializers.ModelSerializer):
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), required=False)
    spend = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = m.OfficeBudget
        exclude = ("created_at", "updated_at")


class OfficeSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    company = serializers.PrimaryKeyRelatedField(queryset=m.Company.objects.all(), required=False)
    phone_number = serializers.CharField()
    logo = Base64ImageField()
    vendors = VendorSerializer(many=True, required=False)
    cc_number = serializers.CharField(validators=[CCNumberValidator()])
    cc_expiry = serializers.DateField(validators=[ExpiryDateValidator()], input_formats=["%m/%y"])
    cc_code = serializers.CharField(validators=[CSCValidator()])
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

    def create(self, validated_data):
        offices = validated_data.pop("offices", None)
        with transaction.atomic():
            company = m.Company.objects.create(**validated_data)
            offices = [
                m.Office(
                    company=company,
                    name=office["name"],
                    address=office["address"],
                    phone_number=office["phone_number"],
                    website=office["website"],
                )
                for office in offices
            ]
            m.Office.objects.bulk_create(offices)
        return company

    def update(self, instance, validated_data):
        offices = validated_data.pop("offices", [])

        with transaction.atomic():
            for key, value in validated_data.items():
                if key == "on_boarding_step" and instance.on_boarding_step > value:
                    continue
                setattr(instance, key, value)

            if validated_data:
                instance.save()

            for office in offices:
                office_id = office.pop("id", None)
                if office_id:
                    office_obj = m.Office.objects.get(id=office_id, company=instance)
                    for key, value in office.items():
                        setattr(office_obj, key, value)
                    office_obj.save()
                else:
                    m.Office.objects.create(company=instance, **office)

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
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), required=False, allow_null=True)
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

    class Meta:
        model = m.OfficeVendor
        fields = "__all__"


class OfficeVendorListSerializer(serializers.ModelSerializer):
    vendor = VendorSerializer()

    class Meta:
        model = m.OfficeVendor
        exclude = ("office",)


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
