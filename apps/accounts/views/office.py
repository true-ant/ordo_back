import logging

from django.db import transaction
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST
from rest_framework.viewsets import ModelViewSet

from apps.accounts import models as m
from apps.accounts import permissions as p
from apps.accounts import serializers as s
from apps.accounts.services.offices import OfficeService
from apps.orders.models import OfficeCheckoutStatus

logger = logging.getLogger(__name__)


class OfficeViewSet(ModelViewSet):
    permission_classes = [p.CompanyOfficePermission]
    queryset = m.Office.objects.filter(is_active=True)

    def get_serializer_class(self):
        if self.request.version == "1.0":
            return s.OfficeSerializerV1
        elif self.request.version == "2.0":
            return s.OfficeSerializerV2
        else:
            raise ValidationError("Wrong version")

    def get_queryset(self):
        return super().get_queryset().filter(company_id=self.kwargs["company_pk"])

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="renew-subscription")
    def renew_subscription(self, request, *args, **kwargs):
        instance = self.get_object()

        result, message = OfficeService.create_subscription(instance)
        return Response({"message": message}, status=HTTP_200_OK if result else HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"], url_path="cancel-subscription")
    def cancel_subscription(self, request, *args, **kwargs):
        instance = self.get_object()
        result, message = OfficeService.cancel_subscription(instance)
        return Response({"message": message}, status=HTTP_200_OK if result else HTTP_400_BAD_REQUEST)

    def perform_destroy(self, instance):
        with transaction.atomic():
            active_members = m.CompanyMember.objects.filter(office=instance)
            for active_member in active_members:
                active_member.is_active = False

            if active_members:
                m.CompanyMember.objects.bulk_update(active_members, ["is_active"])
            instance.is_active = False
            instance.save()

            # cancel subscription
            OfficeService.cancel_subscription(instance)

    @action(detail=True, methods=["post"], url_path="settings")
    def update_settings(self, request, *args, **kwargs):
        instance = self.get_object()
        office_setting, _ = m.OfficeSetting.objects.get_or_create(office=instance)
        serializer = s.OfficeSettingSerializer(office_setting, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def mark_checkout_status_as_ready(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.checkout_status.user != request.user:
            return Response(
                data={"message": "You're not the owner of items added to checkout page"}, status=HTTP_400_BAD_REQUEST
            )
        if instance.checkout_status.checkout_status != OfficeCheckoutStatus.CHECKOUT_STATUS.IN_PROGRESS:
            return Response(data={"message": "Checkout status is already marked as ready"}, status=HTTP_200_OK)
        instance.checkout_status.checkout_status = OfficeCheckoutStatus.CHECKOUT_STATUS.COMPLETE
        instance.checkout_status.order_status = OfficeCheckoutStatus.ORDER_STATUS.COMPLETE
        instance.checkout_status.save()

        return Response(status=HTTP_200_OK, data={"message": "Successfully marked checkout status as ready"})

    @action(detail=True, methods=["get"], url_path="available_dental_key")
    def get_available_dental_key(self, request, *args, **kwargs):
        available_key = m.OpenDentalKey.objects.filter(office__isnull=True).order_by("?")[0]
        if available_key:
            return Response(status=HTTP_200_OK, data={"key": available_key.key})
        return Response({"message": "No available key. Please contact admin."}, status=HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="dental_api")
    def set_dental_api(self, request, *args, **kwargs):
        instance = self.get_object()
        if "dental_key" in request.data:
            key = m.OpenDentalKey.objects.get(key=request.data["dental_key"])
            instance.dental_api = key
            instance.save()
            if "budget_type" in request.data and len(request.data["budget_type"]) > 0:
                resp = self.update_budget_from_dental(request, *args, **kwargs)
                return Response(status=HTTP_200_OK, data=resp.data)
            return Response({"message": "Dental API key is set. Invalid budget type."}, status=HTTP_200_OK)
        return Response({"message": "Invalid key"}, status=HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def unlink_open_dental(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.dental_api = None
        instance.save()
        return Response({"message": "Removed Open Dental API key"}, status=HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def open_dental_connect_status(self, request, *args, **kwargs):
        instance = self.get_object()
        api_key = instance.dental_api
        return Response(status=HTTP_200_OK, data={"connected": api_key is not None})