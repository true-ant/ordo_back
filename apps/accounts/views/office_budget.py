import logging
from datetime import datetime

from _decimal import Decimal
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.accounts import filters as f
from apps.accounts import models as m
from apps.accounts import serializers as s
from apps.common.month import Month

logger = logging.getLogger(__name__)


class BudgetViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = m.Budget.objects.all()
    filterset_class = f.BudgetFilter

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return s.BudgetUpdateSerializerV1
        if self.action == "create":
            return s.BudgetCreateSerializerV1
        return self.get_response_serializer_class()

    def get_response_serializer_class(self):
        if self.request.version == "1.0":
            return s.BudgetSerializerV1
        elif self.request.version == "2.0":
            return s.BudgetSerializerV2
        raise ValidationError("Wrong version")

    def get_queryset(self):
        return super().get_queryset().filter(office_id=self.kwargs["office_pk"])

    def create(self, request, *args, **kwargs):
        on_boarding_step = request.data.pop("on_boarding_step", None)
        company = get_object_or_404(m.Company, pk=self.kwargs["company_pk"])
        if on_boarding_step and company.on_boarding_step < on_boarding_step:
            company.on_boarding_step = on_boarding_step
            company.save()

        now_date = timezone.now().date()
        request.data.setdefault("office", self.kwargs["office_pk"])
        request.data.setdefault("month", now_date)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = self.perform_create(serializer)
        serializer_class = self.get_response_serializer_class()
        serializer = serializer_class(instance=instance)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=["get"], url_path="charts")
    def get_chart_data(self, request, *args, **kwargs):
        # TODO: rewrite this one
        queryset = self.get_queryset().compatible_with_office_budget()
        this_month = Month.from_date(timezone.now().date().replace(day=1))
        a_year_ago = this_month - 11
        queryset = list(queryset.filter(month__lte=this_month, month__gte=a_year_ago).order_by("month"))
        items = {o.month: o for o in queryset}

        ret = []
        for i in range(12):
            month = a_year_ago + i
            if month in items:
                item = items[month]
                ret.append(
                    {
                        "month": month.strftime("%Y-%m"),
                        "dental_budget": item.dental_budget,
                        "dental_spend": item.dental_spend,
                        "office_budget": item.office_budget,
                        "office_spend": item.office_spend,
                    }
                )
            else:
                decimal_0 = Decimal(0)
                ret.append(
                    {
                        "month": month.strftime("%Y-%m"),
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
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        serializer_class = self.get_response_serializer_class()
        serializer = serializer_class(instance=instance)
        return Response(serializer.data)

    @action(detail=False, url_path="stats", methods=["get"])
    def get_current_month_budget(self, request, *args, **kwargs):
        month = self.request.query_params.get("month", "")
        try:
            requested_date = datetime.strptime(month, "%Y-%m")
        except ValueError:
            requested_date = timezone.now().date()
        current_month_budget = (
            self.get_queryset()
            .compatible_with_office_budget()
            .filter(month=Month(requested_date.year, requested_date.month))
            .first()
        )
        serializer = self.get_serializer(current_month_budget)
        return Response(serializer.data)
