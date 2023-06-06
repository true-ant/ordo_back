from django.db import transaction
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.accounts import models as m
from apps.accounts import permissions as p
from apps.accounts import serializers as s
from apps.accounts.services.offices import OfficeService


class CompanyViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    permission_classes = [p.CompanyOfficePermission]
    queryset = m.Company.objects.filter(is_active=True)

    def get_serializer_class(self):
        if self.request.version == "1.0":
            return s.CompanySerializerV1
        elif self.request.version == "2.0":
            return s.CompanySerializerV2
        else:
            raise ValidationError("Wrong version")

    def update(self, request, *args, **kwargs):
        kwargs.setdefault("partial", True)
        return super().update(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="onboarding-step")
    def get_company_on_boarding_step(self, request):
        company_member = m.CompanyMember.objects.filter(user=request.user).first()
        if company_member:
            return Response({"on_boarding_step": company_member.company.on_boarding_step})
        else:
            return Response({"message": ""})

    def perform_destroy(self, instance):
        with transaction.atomic():
            active_members = m.CompanyMember.objects.all()
            for active_member in active_members:
                active_member.is_active = False

            m.CompanyMember.objects.bulk_update(active_members, ["is_active"])
            instance.is_active = False
            instance.save()

            for office in instance.offices.all():
                OfficeService.cancel_subscription(office)
