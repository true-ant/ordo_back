import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED
from rest_framework.viewsets import ModelViewSet

from apps.accounts import filters as f
from apps.accounts import models as m
from apps.accounts import serializers as s
from apps.accounts import tasks as accounts_tasks
from apps.common.month import Month

logger = logging.getLogger(__name__)


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
                    "office__budget_set",
                    m.Budget.objects.filter(month=Month(year=current_time.year, month=current_time.month)),
                    to_attr="prefetched_current_budget",
                ),
                "office__settings",
            )
        return queryset

    def get_serializer_class(self):
        if self.action == "update":
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
        accounts_tasks.send_company_invite_email.delay(
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

        accounts_tasks.send_company_invite_email.delay(
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
