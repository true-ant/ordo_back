from datetime import timedelta

from asgiref.sync import sync_to_async
from django.apps import apps
from django.db import transaction
from django.utils import timezone
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ReadOnlyModelViewSet
from rest_framework_jwt.serializers import jwt_encode_handler, jwt_payload_handler

from apps.common import messages as msgs
from apps.common.asyncdrf import AsyncMixin
from apps.scrapers.errors import VendorAuthenticationFailed, VendorNotSupported
from apps.scrapers.scraper_factory import ScraperFactory

from . import models as m
from . import permissions as p
from . import serializers as s
from .tasks import fetch_orders_from_vendor, send_office_invite_email


class UserSignupAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = s.UserSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            if m.User.objects.filter(email=serializer.validated_data["email"]).exists():
                return Response({"message": msgs.SIGNUP_DUPLICATE_EMAIL}, status=HTTP_400_BAD_REQUEST)

            company_name = serializer.validated_data.pop("company_name")
            user = m.User.objects.create_user(
                username=serializer.validated_data["email"],
                **serializer.validated_data,
            )
            company = m.Company.objects.create(name=company_name, on_boarding_step=0)
            m.CompanyMember.objects.create(
                company=company,
                user=user,
                office=None,
                email=user.email,
                invite_status=m.CompanyMember.InviteStatus.INVITE_APPROVED,
                date_joined=timezone.now(),
            )
            payload = jwt_payload_handler(user)
            return Response(
                {
                    "token": jwt_encode_handler(payload),
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
        instance.is_active = False
        instance.save()


class OfficeViewSet(ModelViewSet):
    permission_classes = [p.CompanyOfficePermission]
    serializer_class = s.OfficeSerializer
    queryset = m.Office.objects.filter(is_active=True)

    def get_queryset(self):
        return super().get_queryset().filter(company_id=self.kwargs["company_pk"])

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()


class CompanyMemberViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.CompanyMemberSerializer

    def get_queryset(self):
        return m.CompanyMember.objects.filter(company_id=self.kwargs["company_pk"])

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk_invite(self, request, *args, **kwargs):
        serializer = s.CompanyMemberBulkInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        emails = [member["email"] for member in serializer.validated_data["members"]]
        with transaction.atomic():
            company = m.Company.objects.get(id=self.kwargs["company_pk"])
            company.on_boarding_step = serializer.validated_data["on_boarding_step"]
            company.save()
            users = m.User.objects.in_bulk(emails, field_name="username")
            members = (
                m.CompanyMember(
                    company_id=kwargs["company_pk"],
                    office=member["office"],
                    email=member["email"],
                    user=users.get(member["email"], None),
                    token_expires_at=timezone.now() + timedelta(m.INVITE_EXPIRES_DAYS),
                )
                for member in serializer.validated_data["members"]
            )
            m.CompanyMember.objects.bulk_create(members, ignore_conflicts=True)
            send_office_invite_email.delay(
                [
                    {"office_id": member["office"].id, "email": member["email"]}
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
        if company.on_boarding_step < 5:
            return Response({"message": msgs.INVITE_NOT_ACCEPTABLE}, status=HTTP_400_BAD_REQUEST)

        now = timezone.now()
        if invite.token_expires_at > now:
            return Response({"message": msgs.INVITE_TOKEN_EXPIRED}, status=HTTP_400_BAD_REQUEST)

        if invite.user:
            invite.invite_status = m.CompanyMember.InviteStatus.INVITE_APPROVED
            invite.date_joined = timezone.now()
            invite.save()
            return Response({"redirect": "login"})

        return Response(
            {
                "redirect": "signup",
                "email": invite.email,
                "organization": invite.organization.name,
                "token": token,
            }
        )


class VendorViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.VendorSerializer
    queryset = m.Vendor.objects.all()


class OfficeVendorViewSet(AsyncMixin, ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return m.OfficeVendor.objects.filter(office_id=self.kwargs["office_pk"])

    @sync_to_async
    def _validate(self, data):
        serializer = s.OfficeVendorSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer

    @sync_to_async
    def _save(self, serializer):
        return serializer.save()

    async def create(self, request, *args, **kwargs):
        serializer = await self._validate(request.data)
        session = apps.get_app_config("accounts").session
        session._cookie_jar.clear()
        try:
            scraper = ScraperFactory.create_scraper(
                scraper_name=serializer.validated_data["vendor"].slug,
                username=serializer.validated_data["username"],
                password=serializer.validated_data["password"],
                session=session,
            )
            login_cookies = await scraper.login()
            office_vendor = await self._save(serializer)
            fetch_orders_from_vendor.delay(
                office_vendor_id=office_vendor.id,
                login_cookies=login_cookies.output(),
            )
        except VendorNotSupported:
            return Response(
                {
                    "message": msgs.VENDOR_SCRAPER_IMPROPERLY_CONFIGURED,
                },
                status=HTTP_400_BAD_REQUEST,
            )
        except VendorAuthenticationFailed:
            return Response({"message": msgs.VENDOR_WRONG_INFORMATION}, status=HTTP_400_BAD_REQUEST)

        return Response({"message": msgs.VENDOR_CONNECTED})


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
