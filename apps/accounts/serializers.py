from django.db import transaction
from rest_framework import serializers

from apps.common.serializers import Base64ImageField

from . import models as m


class CompanyMemberSerializer(serializers.ModelSerializer):
    office = serializers.PrimaryKeyRelatedField(queryset=m.Office.objects.all(), allow_null=True)

    class Meta:
        model = m.CompanyMember
        exclude = ("company",)


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Vendor
        fields = "__all__"


class OfficeSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    company = serializers.PrimaryKeyRelatedField(queryset=m.Company.objects.all(), required=False)
    logo = Base64ImageField()

    class Meta:
        model = m.Office
        fields = "__all__"


class CompanySerializer(serializers.ModelSerializer):
    offices = OfficeSerializer(many=True)
    vendors = VendorSerializer(many=True)

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
        if self.context.get("exclude_vendors"):
            res.pop("vendors")
        return res


class UserSignupSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField()
    company_name = serializers.CharField()
    role = serializers.ChoiceField(choices=(m.User.Role.ADMIN.value,))


class CompanyMemberBulkInviteSerializer(serializers.Serializer):
    on_boarding_step = serializers.IntegerField()
    members = serializers.ListField(child=CompanyMemberSerializer(), allow_empty=False)


class CompanyVendorSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(queryset=m.Company.objects.all(), allow_null=True)

    class Meta:
        model = m.CompanyVendor
        fields = "__all__"


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
