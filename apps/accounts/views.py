from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework_jwt.serializers import jwt_encode_handler, jwt_payload_handler

from apps.common import messages as msgs

from . import models as m
from . import serializers as s
from .tasks import send_office_invite_email


class UserSignupAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = s.UserSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            if m.User.objects.filter(email=serializer.validated_data["email"]).exists():
                return Response({"email": msgs.SIGNUP_DUPLICATE_EMAIL})

            user = m.User.objects.create_user(
                first_name=serializer.validated_data["first_name"],
                last_name=serializer.validated_data["last_name"],
                password=serializer.validated_data["password"],
                email=serializer.validated_data["email"],
                username=serializer.validated_data["email"],
            )
            company = m.Company.objects.create(name=serializer.validated_data["company_name"], on_boarding_step=0)
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
                    "success": True,
                    "data": {"token": jwt_encode_handler(payload), "company": s.CompanySerializer(company).data},
                }
            )


class CompanyViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.CompanySerializer
    queryset = m.Company.objects.all()

    def update(self, request, *args, **kwargs):
        kwargs.setdefault("partial", True)
        return super().update(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="onboarding-step")
    def get_company_on_boarding_step(self, request):
        company_member = m.CompanyMember.objects.filter(user=request.user).first()
        if company_member:
            return Response({"success": True, "on_boarding_step": company_member.company.on_boarding_step})
        else:
            return Response({"success": False, "message": ""})


class OfficeViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return m.Office.objects.filter(company_id=self.kwargs["company_pk"])


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
        return Response({"success": True})


class CompanyMemberInvitationCheckAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        invite = m.CompanyMember.objects.filter(token=token).first()
        if invite is None:
            return Response({"message": msgs.INVITE_TOKEN_WRONG}, status=HTTP_400_BAD_REQUEST)

        company = invite.company
        if company.on_boarding_step < 5:
            return Response({"message": msgs.INVITE_NOT_ACCEPTABLE})

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
