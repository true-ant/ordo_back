import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from asgiref.sync import sync_to_async
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_400_BAD_REQUEST
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.helper import OfficeBudgetHelper
from apps.common import messages as msgs
from apps.common.asyncdrf import AsyncMixin
from apps.common.enums import OnboardingStep
from apps.common.month import Month
from apps.orders.models import OfficeCheckoutStatus
from apps.scrapers.errors import (
    NetworkConnectionException,
    VendorAuthenticationFailed,
    VendorNotSupported,
)

from . import filters as f
from . import models as m
from . import permissions as p
from . import serializers as s
from .services.offices import OfficeService
from .tasks import (
    fetch_order_history,
    fetch_vendor_products_prices,
    link_vendor,
    send_company_invite_email,
    send_welcome_email,
)

logger = logging.getLogger(__name__)


class UserSignupAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = s.UserSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            if m.User.objects.filter(email=serializer.validated_data["email"]).exists():
                return Response({"message": msgs.SIGNUP_DUPLICATE_EMAIL}, status=HTTP_400_BAD_REQUEST)

            company_name = serializer.validated_data.pop("company_name", None)
            token = serializer.validated_data.pop("token", None)
            user = m.User.objects.create_user(
                username=serializer.validated_data["email"],
                **serializer.validated_data,
            )
            if token:
                company_member = m.CompanyMember.objects.filter(
                    token=token, email=serializer.validated_data["email"]
                ).first()
                if not company_member:
                    raise ValidationError("Your invite not found")
                company_member.user = user
                company_member.invite_status = m.CompanyMember.InviteStatus.INVITE_APPROVED
                company_member.date_joined = timezone.localtime()
                company_member.save()

                # update the user role with the company member role to be matched...
                user.role = company_member.role
                user.save()

                company = company_member.company
            else:
                company = m.Company.objects.create(name=company_name, on_boarding_step=OnboardingStep.ACCOUNT_SETUP)
                m.CompanyMember.objects.create(
                    company=company,
                    user=user,
                    role=m.User.Role.ADMIN,
                    office=None,
                    email=user.email,
                    invite_status=m.CompanyMember.InviteStatus.INVITE_APPROVED,
                    date_joined=timezone.localtime(),
                )

        send_welcome_email.delay(user_id=user.id)
        token = RefreshToken.for_user(user).access_token
        token["username"] = user.username
        token["email"] = user.username
        return Response(
            {
                "token": str(token),
                "company": s.CompanySerializer(company).data,
            }
        )


class CompanyViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    GenericViewSet,
):
    permission_classes = [p.CompanyOfficePermission]
    serializer_class = s.CompanySerializer
    queryset = m.Company.objects.filter(is_active=True)

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


class OfficeViewSet(ModelViewSet):
    permission_classes = [p.CompanyOfficePermission]
    serializer_class = s.OfficeSerializer
    queryset = m.Office.objects.filter(is_active=True)

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

    @action(detail=True, methods=["post"], url_path="update_budget")
    def update_budget_from_dental(self, request, *args, **kwargs):
        budget_type = request.data.get("budget_type")
        if not budget_type or budget_type not in ["collection", "production"]:
            return Response({"message": "Invalid budget type."}, status=HTTP_400_BAD_REQUEST)
        instance = self.get_object()
        dental_api_key = instance.dental_api.key if instance.dental_api else None
        if not dental_api_key:
            return Response({"message": "No api key"}, HTTP_400_BAD_REQUEST)
        now_date = timezone.localtime().date()
        first_day_of_month = now_date.replace(day=1)
        prev_date = now_date - relativedelta(months=1)

        last_day_of_prev_month = date.today().replace(day=1) - timedelta(days=1)
        start_day_of_prev_month = date.today().replace(day=1) - timedelta(days=last_day_of_prev_month.day)
        prev_adjusted_production, prev_collections = OfficeBudgetHelper.load_prev_month_production_collection(
            start_day_of_prev_month, last_day_of_prev_month, dental_api_key
        )
        if budget_type == "collection":
            budget_from_opendental = prev_collections
        else:
            budget_from_opendental = prev_adjusted_production
        prev_dental_percentage = 5.0
        prev_office_percentage = 0.5

        if m.OfficeBudget.objects.filter(office=instance, month=datetime(prev_date.year, prev_date.month, 1)):
            prev_budget = m.OfficeBudget.objects.get(
                office=instance, month=datetime(prev_date.year, prev_date.month, 1)
            )
            prev_dental_percentage = prev_budget.dental_percentage
            prev_office_percentage = prev_budget.office_percentage

        prev_dental_budget = budget_from_opendental * float(prev_dental_percentage) / 100.0
        prev_office_budget = budget_from_opendental * float(prev_office_percentage) / 100.0

        existing_budget = m.OfficeBudget.objects.filter(office=instance, month=first_day_of_month).first()
        if existing_budget:
            existing_budget.adjusted_production = prev_adjusted_production
            existing_budget.collection = prev_collections
            existing_budget.dental_budget_type = budget_type
            existing_budget.dental_budget_type = budget_type
            existing_budget.dental_total_budget = budget_from_opendental
            existing_budget.dental_percentage = prev_dental_percentage
            existing_budget.dental_budget = prev_dental_budget
            existing_budget.dental_spend = OfficeBudgetHelper.get_office_spent_budget_current_month(instance)
            existing_budget.office_budget_type = budget_type
            existing_budget.office_total_budget = budget_from_opendental
            existing_budget.office_percentage = prev_office_percentage
            existing_budget.office_budget = prev_office_budget
            existing_budget.office_spend = "0.0"
            existing_budget.month = first_day_of_month
            existing_budget.save()
        else:
            m.OfficeBudget.objects.create(
                office=instance,
                adjusted_production=prev_adjusted_production,
                collection=prev_collections,
                dental_budget_type=budget_type,
                dental_total_budget=budget_from_opendental,
                dental_percentage=prev_dental_percentage,
                dental_budget=prev_dental_budget,
                dental_spend=OfficeBudgetHelper.get_office_spent_budget_current_month(instance),
                office_budget_type=budget_type,
                office_total_budget=budget_from_opendental,
                office_percentage=prev_office_percentage,
                office_budget=prev_office_budget,
                office_spend="0.0",
                month=first_day_of_month,
            )
        return Response(
            data={
                "dental_budget_type": budget_type,
                "dental_percentage": prev_dental_percentage,
                "dental_budget": prev_dental_budget,
                "dental_total_budget": budget_from_opendental,
                "adjusted_production": prev_adjusted_production,
                "collections": prev_collections,
            },
            status=HTTP_200_OK,
        )


class CompanyMemberViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    filterset_class = f.CompanyMemberFilter

    def get_queryset(self):
        queryset = m.CompanyMember.objects.filter(company_id=self.kwargs["company_pk"])
        current_time = timezone.localtime()
        if self.action == "list":
            queryset = queryset.select_related(
                "office",
                "office__dental_api",
            ).prefetch_related(
                "office__addresses",
                "office__vendors",
                Prefetch(
                    "office__budgets",
                    m.OfficeBudget.objects.filter(month=Month(year=current_time.year, month=current_time.month)),
                    to_attr="prefetched_current_budget",
                ),
                "office__settings",
            )
        return queryset

    def get_serializer_class(self):
        if self.action == "update" or self.action == "partial_update":
            return s.CompanyMemberUpdateSerializer
        else:
            return s.CompanyMemberSerializer

    def create(self, request, *args, **kwargs):
        request.data.setdefault("company", self.kwargs["company_pk"])
        data = request.data
        data["invited_by"] = request.user.id
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        send_company_invite_email.delay(
            [
                {
                    "company_id": self.kwargs["company_pk"],
                    "email": serializer.validated_data["email"],
                    "office_id": serializer.validated_data["office"].id,
                }
            ]
        )
        return Response(serializer.data, status=HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer_class = self.get_serializer_class()
        data = request.data
        data["invited_by"] = request.user.id
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["role"] is not m.User.Role.ADMIN:
            admin_count = m.CompanyMember.objects.filter(
                company_id=instance.company_id, role=m.User.Role.ADMIN
            ).count()
            if admin_count <= 1:
                return Response({"message": msgs.NO_ADMIN_MEMBER}, status=HTTP_400_BAD_REQUEST)
        instance.role = serializer.validated_data["role"]
        instance.save()
        return Response({"message": ""})

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk_invite(self, request, *args, **kwargs):
        serializer = s.CompanyMemberBulkInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        emails = [member["email"] for member in serializer.validated_data["members"]]
        with transaction.atomic():
            company = m.Company.objects.get(id=self.kwargs["company_pk"])
            on_boarding_step = serializer.validated_data.get("on_boarding_step")
            if on_boarding_step:
                company.on_boarding_step = serializer.validated_data.get("on_boarding_step")
                company.save()

            users = m.User.objects.in_bulk(emails, field_name="username")

            for member in serializer.validated_data["members"]:
                pre_associated_offices = set(
                    m.CompanyMember.objects.filter(company_id=kwargs["company_pk"], email=member["email"]).values_list(
                        "office", flat=True
                    )
                )

                offices = member.get("offices")
                if offices:
                    offices = set(offices)
                    to_be_removed_offices = pre_associated_offices

                    if to_be_removed_offices:
                        m.CompanyMember.objects.filter(
                            email=member["email"], office_id__in=to_be_removed_offices
                        ).delete()

                    for i, office in enumerate(offices):
                        m.CompanyMember.objects.create(
                            company_id=kwargs["company_pk"],
                            office=office,
                            email=member["email"],
                            role=member["role"],
                            user=users.get(member["email"], None),
                            invited_by=request.user,
                            token_expires_at=timezone.localtime() + timedelta(m.INVITE_EXPIRES_DAYS),
                        )
                else:
                    m.CompanyMember.objects.create(
                        company_id=kwargs["company_pk"],
                        office=None,
                        email=member["email"],
                        role=member["role"],
                        user=users.get(member["email"], None),
                        invited_by=request.user,
                        token_expires_at=timezone.localtime() + timedelta(m.INVITE_EXPIRES_DAYS),
                    )

        send_company_invite_email.delay(
            [
                {
                    "company_id": self.kwargs["company_pk"],
                    "email": member["email"],
                    "office_id": office_.id if (office_ := member.get("office", None)) else None,
                }
                for member in serializer.validated_data["members"]
            ]
        )
        return Response({})


class CompanyMemberInvitationCheckAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        invite = m.CompanyMember.objects.filter(token=token).first()
        if invite is None:
            return Response({"message": msgs.INVITE_TOKEN_WRONG}, status=HTTP_400_BAD_REQUEST)

        company = invite.company

        # 4 is the minimum last step.
        if company.on_boarding_step < OnboardingStep.INVITE_TEAM:
            return Response({"message": msgs.INVITE_NOT_ACCEPTABLE}, status=HTTP_400_BAD_REQUEST)

        now = timezone.localtime()
        if invite.token_expires_at < now:
            return Response({"message": msgs.INVITE_TOKEN_EXPIRED}, status=HTTP_400_BAD_REQUEST)

        if invite.user:
            invite.invite_status = m.CompanyMember.InviteStatus.INVITE_APPROVED
            invite.date_joined = timezone.localtime()
            invite.save()
            return Response({"redirect": "login"})

        return Response(
            {
                "redirect": "signup",
                "email": invite.email,
                "company": invite.company.name,
                "role": invite.role,
                "token": token,
            }
        )


class VendorViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.VendorSerializer
    queryset = m.Vendor.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["enabled"]

    def update(self, request, *args, **kwargs):
        kwargs.setdefault("partial", True)
        return super().update(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="shipping_methods")
    def shipping_methods(self, request, *args, **kwargs):
        # TODO: currently hard code because not sure about shipping method across all vendors
        vendors = request.data.get("vendors")
        ret = {
            "henry_schein": [
                "UPS Standard Delivery",
                "Next Day Delivery (extra charge)",
                "Saturday Delivery (extra charge)",
                "Next Day 10:30 (extra charge)",
                "2nd Day Air (extra charge)",
            ]
        }
        ret = {k: v for k, v in ret.items() if k in vendors}
        return Response(ret)


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
                link_vendor.delay(
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

        fetch_order_history.delay(
            vendor_slug=office_vendor.vendor.slug,
            office_id=office_vendor.office.id,
        )
        return Response({"message": msgs.OFFICE_VENDOR_RECONNECTED})

    @action(detail=True, methods=["get"], url_path="fetch-prices")
    def fetch_product_prices(self, request, *args, **kwargs):
        instance = self.get_object()
        fetch_vendor_products_prices.delay(office_vendor_id=instance.id)
        return Response(s.OfficeVendorSerializer(instance).data)

    @action(detail=True, methods=["post"], url_path="fetch")
    def fetch_orders(self, request, *args, **kwargs):
        instance = self.get_object()
        fetch_order_history.delay(vendor_slug=instance.vendor.slug, office_id=instance.office.id)
        return Response(s.OfficeVendorSerializer(instance).data)


class UserViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.UserSerializer
    queryset = m.User.objects.all()

    def get_serializer_context(self):
        res = super().get_serializer_context()
        res["exclude_vendors"] = True
        return res

    def get_object(self):
        if self.kwargs["pk"] == "me":
            self.kwargs["pk"] = self.request.user.id
        return super().get_object()

    def update(self, request, *args, **kwargs):
        kwargs.setdefault("partial", True)
        return super().update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        with transaction.atomic():
            active_memberships = m.CompanyMember.objects.filter(user=instance)
            for active_membership in active_memberships:
                active_membership.is_active = False

            m.CompanyMember.objects.bulk_update(active_memberships, fields=["is_active"])

            # cancel subscription if noone is in office
            for active_membership in active_memberships:
                if not m.CompanyMember.objects.filter(
                    role=m.User.Role.ADMIN, company=active_membership.company
                ).exists():
                    for office in active_membership.company.offices.all():
                        OfficeService.cancel_subscription(office)


class OfficeBudgetViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.OfficeBudgetSerializer
    queryset = m.OfficeBudget.objects.all()
    filterset_class = f.OfficeBudgetFilter

    def get_queryset(self):
        return super().get_queryset().filter(office_id=self.kwargs["office_pk"])

    def create(self, request, *args, **kwargs):
        on_boarding_step = request.data.pop("on_boarding_step", None)
        company = get_object_or_404(m.Company, pk=self.kwargs["company_pk"])
        if on_boarding_step and company.on_boarding_step < on_boarding_step:
            company.on_boarding_step = on_boarding_step
            company.save()

        now_date = timezone.localtime().date()
        request.data.setdefault("office", self.kwargs["office_pk"])
        request.data.setdefault("month", now_date)
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="charts")
    def get_chart_data(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        this_month = timezone.localtime().date().replace(day=1)
        a_year_ago = this_month - relativedelta(months=11)
        queryset = list(
            queryset.filter(month__lte=this_month, month__gte=a_year_ago)
            .order_by("month")
            .values("month", "dental_budget", "dental_spend", "office_budget", "office_spend")
        )
        queryset = {str(q["month"]): q for q in queryset}

        ret = []
        for i in range(12):
            month = a_year_ago + relativedelta(months=i)
            month_str = month.strftime("%Y-%m")
            if month_str in queryset:
                ret.append(queryset[month_str])
            else:
                decimal_0 = Decimal(0)
                ret.append(
                    {
                        "month": month_str,
                        "dental_budget": decimal_0,
                        "dental_spend": decimal_0,
                        "office_budget": decimal_0,
                        "office_spend": decimal_0,
                    }
                )
        serializer = s.OfficeBudgetChartSerializer(ret, many=True)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        kwargs.setdefault("partial", True)
        return super().update(request, *args, **kwargs)

    @action(detail=False, url_path="stats", methods=["get"])
    def get_current_month_budget(self, request, *args, **kwargs):
        month = self.request.query_params.get("month", "")
        try:
            requested_date = datetime.strptime(month, "%Y-%m")
        except ValueError:
            requested_date = timezone.localtime().date()
        current_month_budget = (
            self.get_queryset().filter(month=Month(requested_date.year, requested_date.month)).first()
        )
        serializer = self.get_serializer(current_month_budget)
        return Response(serializer.data)


class HealthCheck(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(status=HTTP_200_OK)


class VendorRequestViewSet(ModelViewSet):
    queryset = m.VendorRequest.objects.all()
    serializer_class = s.VendorRequestSerializer

    def get_queryset(self):
        return self.queryset.filter(company_id=self.kwargs["company_pk"])
