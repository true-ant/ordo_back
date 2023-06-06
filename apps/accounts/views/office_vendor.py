import logging

from asgiref.sync import sync_to_async
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.viewsets import ModelViewSet

from apps.accounts import models as m
from apps.accounts import serializers as s
from apps.accounts import tasks as accounts_tasks
from apps.common import messages as msgs
from apps.common.asyncdrf import AsyncMixin
from apps.common.enums import OnboardingStep
from apps.scrapers.errors import (
    NetworkConnectionException,
    VendorAuthenticationFailed,
    VendorNotSupported,
)

logger = logging.getLogger(__name__)


class OfficeVendorViewSet(AsyncMixin, ModelViewSet):
    serializer_class = s.OfficeVendorListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = m.OfficeVendor.objects.filter(office_id=self.kwargs["office_pk"])
        if self.action == "list":
            return queryset.select_related("vendor", "default_shipping_option").prefetch_related("shipping_options")
        return queryset

    def get_serializer_class(self):
        if self.request.method in ["POST"]:
            return s.OfficeVendorSerializer
        return s.OfficeVendorListSerializer

    @sync_to_async
    def _validate(self, data):
        office = get_object_or_404(m.Office, id=data["office"])
        company = office.company
        if company.on_boarding_step < OnboardingStep.BILLING_INFORMATION:
            raise ValidationError({"message": msgs.VENDOR_IMPOSSIBLE_LINK})
        company.on_boarding_step = OnboardingStep.LINK_VENDOR
        company.save()

        serializer = s.OfficeVendorSerializer(data=data)
        serializer.is_valid()
        return serializer

    @sync_to_async
    def serializer_data(self, serializer):
        return serializer.data

    async def create(self, request, *args, **kwargs):
        serializer = await self._validate({**request.data, "office": kwargs["office_pk"]})
        # await sync_to_async(serializer.save)()
        # session = apps.get_app_config("accounts").session
        # session._cookie_jar.clear()
        try:
            if (
                serializer.validated_data["vendor"].slug != "amazon"
                and serializer.validated_data["vendor"].slug != "ebay"
            ):
                # scraper = ScraperFactory.create_scraper(
                #     vendor=serializer.validated_data["vendor"],
                #     username=serializer.validated_data["username"],
                #     password=serializer.validated_data["password"],
                #     session=session,
                # )
                office_vendor = await sync_to_async(serializer.save)()
                # login_cookies = await scraper.login()

                # All scrapers work with login_cookies,
                # but henryschein doesn't work with login_cookies...
                accounts_tasks.link_vendor.delay(
                    vendor_slug=office_vendor.vendor.slug,
                    office_id=office_vendor.office.id,
                )

            else:
                await sync_to_async(serializer.save)()
                # office_vendor.task_id = ar.id
                # await sync_to_async(office_vendor.save)()

        except VendorNotSupported:
            return Response(
                {
                    "message": msgs.VENDOR_SCRAPER_IMPROPERLY_CONFIGURED,
                },
                status=HTTP_400_BAD_REQUEST,
            )
        except VendorAuthenticationFailed:
            return Response({"message": msgs.VENDOR_WRONG_INFORMATION}, status=HTTP_400_BAD_REQUEST)
        except NetworkConnectionException:
            return Response({"message": msgs.VENDOR_BAD_NETWORK_CONNECTION}, status=HTTP_400_BAD_REQUEST)
        except Exception:  # noqa
            return Response({"message": msgs.UNKNOWN_ISSUE, **serializer.data}, status=HTTP_400_BAD_REQUEST)

        data = await self.serializer_data(serializer)
        return Response({"message": msgs.VENDOR_CONNECTED, **data})

    @action(detail=True, methods=["post"])
    def relink_office_vendor(self, request, *args, **kwargs):
        office_vendor = self.get_object()
        if office_vendor.login_success:
            return Response({"message": msgs.OFFICE_VENDOR_ALREADY_LINKED}, status=HTTP_400_BAD_REQUEST)

        serializer = s.OfficeVendorSerializer(
            office_vendor, data={**request.data, "login_success": True}, partial=True
        )
        if serializer.is_valid():
            self.perform_update(serializer)

        accounts_tasks.fetch_order_history.delay(
            vendor_slug=office_vendor.vendor.slug,
            office_id=office_vendor.office.id,
        )
        return Response({"message": msgs.OFFICE_VENDOR_RECONNECTED})

    @action(detail=True, methods=["get"], url_path="fetch-prices")
    def fetch_product_prices(self, request, *args, **kwargs):
        instance = self.get_object()
        accounts_tasks.fetch_vendor_products_prices.delay(office_vendor_id=instance.id)
        return Response(s.OfficeVendorSerializer(instance).data)

    @action(detail=True, methods=["post"], url_path="fetch")
    def fetch_orders(self, request, *args, **kwargs):
        instance = self.get_object()
        accounts_tasks.fetch_order_history.delay(vendor_slug=instance.vendor.slug, office_id=instance.office.id)
        return Response(s.OfficeVendorSerializer(instance).data)
