from django.db import transaction
from rest_framework import serializers

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
    vendors = VendorSerializer(many=True, required=False)

    class Meta:
        model = m.Office
        fields = "__all__"


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


class UserSignupSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField()
    company_name = serializers.CharField()
    role = serializers.ChoiceField(choices=(m.User.Role.ADMIN,))


class CompanyMemberBulkInviteSerializer(serializers.Serializer):
    on_boarding_step = serializers.IntegerField()
    members = serializers.ListField(child=CompanyMemberSerializer(), allow_empty=False)


class OfficeVendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.OfficeVendor
        fields = "__all__"


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.User
        fields = (
            "first_name",
            "last_name",
            "email",
            "username",
            "role",
        )
