import logging
from datetime import datetime

from _decimal import Decimal
from dateutil.relativedelta import relativedelta
from django.shortcuts import get_object_or_404
from django.utils import timezone
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
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="charts")
    def get_chart_data(self, request, *args, **kwargs):
        # TODO: rewrite this one
        queryset = self.get_queryset().compatible_with_office_budget()
        this_month = timezone.now().date().replace(day=1)
        a_year_ago = this_month - relativedelta(months=11)
        queryset = list(queryset.filter(month__lte=this_month, month__gte=a_year_ago).order_by("month"))
        items = {o.month: o for o in queryset}

        ret = []
        for i in range(12):
            month = a_year_ago + relativedelta(months=i)
            if month in items:
                ret.append(items[month])
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
        return super().update(request, *args, **kwargs)

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
