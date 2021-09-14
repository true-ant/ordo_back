from datetime import timedelta

from asgiref.sync import sync_to_async
from django.apps import apps
from django.db import transaction
from django.db.utils import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from rest_framework_jwt.serializers import jwt_encode_handler, jwt_payload_handler

from apps.common import messages as msgs
from apps.common.asyncdrf import AsyncMixin
from apps.scrapers.errors import VendorAuthenticationFailed, VendorNotSupported
from apps.scrapers.scraper_factory import ScraperFactory

from . import models as m
from . import permissions as p
from . import serializers as s
from .tasks import fetch_orders_from_vendor, send_company_invite_email


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
                company_member.user = user
                company_member.invite_status = m.CompanyMember.InviteStatus.INVITE_APPROVED
                company_member.date_joined = timezone.now()
                company_member.save()
                company = company_member.company
            else:
                company = m.Company.objects.create(name=company_name, on_boarding_step=0)
                m.CompanyMember.objects.create(
                    company=company,
                    user=user,
                    role=m.User.Role.ADMIN,
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
        with transaction.atomic():
            active_members = m.CompanyMember.objects.all()
            for active_member in active_members:
                active_member.is_active = False

            m.CompanyMember.objects.bulk_update(active_members, ["is_active"])
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
        with transaction.atomic():
            active_members = m.CompanyMember.objects.filter(office=instance)
            for active_member in active_members:
                active_member.is_active = False

            m.CompanyMember.objects.bulk_update(active_members, ["is_active"])
            instance.is_active = False
            instance.save()


class CompanyMemberViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return m.CompanyMember.objects.filter(company_id=self.kwargs["company_pk"])

    def get_serializer_class(self):
        if self.action == "update":
            return s.CompanyMemberUpdateSerializer
        else:
            return s.CompanyMemberSerializer

    def create(self, request, *args, **kwargs):
        request.data.setdefault("company", self.kwargs["company_pk"])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        send_company_invite_email.delay(
            [
                {
                    "company_id": self.kwargs["company_pk"],
                    "email": serializer.validated_data["email"],
                    "office_id": office_.id if (office_ := serializer.validated_data.get("office", None)) else None,
                }
            ]
        )
        return Response(serializer.data, status=HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer_class = self.get_serializer_class()
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
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
            company.on_boarding_step = serializer.validated_data["on_boarding_step"]
            company.save()
            users = m.User.objects.in_bulk(emails, field_name="username")
            members = (
                m.CompanyMember(
                    company_id=kwargs["company_pk"],
                    office=member.get("office", None),
                    email=member["email"],
                    role=member["role"],
                    user=users.get(member["email"], None),
                    token_expires_at=timezone.now() + timedelta(m.INVITE_EXPIRES_DAYS),
                )
                for member in serializer.validated_data["members"]
            )
            try:
                m.CompanyMember.objects.bulk_create(members)
            except IntegrityError:
                return Response({"message": msgs.INVITE_EMAIL_EXIST}, status=HTTP_400_BAD_REQUEST)
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
        if company.on_boarding_step < 5:
            return Response({"message": msgs.INVITE_NOT_ACCEPTABLE}, status=HTTP_400_BAD_REQUEST)

        now = timezone.now()
        if invite.token_expires_at < now:
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
                "company": invite.company.name,
                "role": invite.role,
                "token": token,
            }
        )


class VendorViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.VendorSerializer
    queryset = m.Vendor.objects.all()

    def update(self, request, *args, **kwargs):
        kwargs.setdefault("partial", True)
        return super().update(request, *args, **kwargs)


class OfficeVendorViewSet(AsyncMixin, ModelViewSet):
    serializer_class = s.OfficeVendorListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return m.OfficeVendor.objects.filter(office_id=self.kwargs["office_pk"])

    @sync_to_async
    def _validate(self, data):
        office = get_object_or_404(m.Office, id=data["office"])
        company = office.company
        if company.on_boarding_step == 4:
            company.on_boarding_step = 5
            company.save()
        elif company.on_boarding_step < 4:
            raise ValidationError({"message": msgs.VENDOR_IMPOSSIBLE_LINK})

        serializer = s.OfficeVendorSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return serializer

    @sync_to_async
    def _save(self, serializer):
        return serializer.save()

    async def create(self, request, *args, **kwargs):
        serializer = await self._validate({**request.data, "office": kwargs["office_pk"]})
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

        return Response({"message": msgs.VENDOR_CONNECTED, **serializer.data})

    @action(detail=True, methods=["post"], url_path="fetch")
    def fetch_orders(self, request, *args, **kwargs):
        instance = self.get_object()
        fetch_orders_from_vendor.delay(office_vendor_id=instance.id, login_cookies=None, perform_login=True)
        return Response({})


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
            instance.is_active = False
            instance.save()
