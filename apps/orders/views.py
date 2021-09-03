from dateutil.relativedelta import relativedelta
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.models import Company, Office

from . import filters as f
from . import models as m
from . import permissions as p
from . import serializers as s


class OrderViewSet(ModelViewSet):
    queryset = m.Order.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = s.OrderSerializer
    filterset_class = f.OrderFilter

    def get_serializer_class(self):
        return s.OrderListSerializer if self.action == "list" else self.serializer_class

    def get_queryset(self):
        return super().get_queryset().filter(office_vendor__office__id=self.kwargs["office_pk"])


class OrderProductViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = m.OrderProduct.objects.all()
    serializer_class = s.OrderProductSerializer

    def get_queryset(self):
        return super().get_queryset().filter(order__office_vendor__office__id=self.kwargs["office_pk"])


class CompanyOrderAPIView(APIView, LimitOffsetPagination):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        queryset = m.Order.objects.filter(office_vendor__office__company__id=company_id)
        paginate_queryset = self.paginate_queryset(queryset, request, view=self)
        serializer = s.OrderListSerializer(paginate_queryset, many=True)
        return self.get_paginated_response(serializer.data)


def last_months_spending(queryset):
    last_year_today = (timezone.now() - relativedelta(months=11)).date()
    last_year_today.replace(day=1)
    return (
        queryset.filter(order_date__gte=last_year_today)
        .annotate(month=m.YearMonth("order_date"))
        .values("month")
        .order_by("month")
        .annotate(total_amount=Sum("total_amount"))
    )


class CompanySpendAPIView(APIView):
    permission_classes = [p.CompanyOfficeReadPermission]

    def get(self, request, company_id):
        obj = get_object_or_404(Company, id=company_id)
        self.check_object_permissions(request, obj)
        queryset = m.Order.objects.select_related("office_vendor__vendor").filter(office_vendor__office__company=obj)
        by = request.query_params.get("by", "vendor")
        if by == "month":
            qs = last_months_spending(queryset)
        else:
            qs = (
                queryset.values("office_vendor__vendor")
                .order_by("office_vendor__vendor")
                .annotate(total_amount=Sum("total_amount"), vendor=F("office_vendor__vendor__name"))
            )
        serializer = s.TotalSpendSerializer(qs, many=True)
        return Response(serializer.data)


class OfficeSpendAPIView(APIView):
    permission_classes = [p.CompanyOfficeReadPermission]

    def get(self, request, office_id):
        obj = get_object_or_404(Office, id=office_id)
        self.check_object_permissions(request, obj)
        queryset = m.Order.objects.select_related("office_vendor__vendor").filter(office_vendor__office=obj)
        by = request.query_params.get("by", "vendor")
        if by == "month":
            qs = last_months_spending(queryset)

        else:
            qs = (
                queryset.values("office_vendor")
                .order_by("office_vendor")
                .annotate(total_amount=Sum("total_amount"), vendor=F("office_vendor__vendor__name"))
            )
        serializer = s.TotalSpendSerializer(qs, many=True)
        return Response(serializer.data)
