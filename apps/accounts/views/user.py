import logging

from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.accounts import models as m
from apps.accounts import serializers as s
from apps.accounts.services.offices import OfficeService

logger = logging.getLogger(__name__)


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
