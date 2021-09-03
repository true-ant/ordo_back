from dateutil.relativedelta import relativedelta
from django.db.models import DateField, F, Func, Sum
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from . import filters as f
from . import models as m
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

    @action(detail=False, methods=["get"], url_path="by-vendors")
    def get_statics_by_vendor(self, request, *args, **kwargs):
        qs = self.get_queryset()
        qs = (
            qs.values("office_vendor")
            .order_by("office_vendor")
            .annotate(total_amount=Sum("total_amount"), vendor=F("office_vendor__vendor__name"))
        )
        serializer = s.TotalSpendSerializer(qs, many=True)
        return Response(serializer.data)


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


class YearMonth(Func):
    function = "TO_CHAR"
    template = "%(function)s(%(expressions)s, 'YYYY-MM')"
    output_field = DateField()


class CompanyTotalSpendAPIView(APIView):
    def get(self, request, company_id):
        queryset = m.Order.objects.select_related("office_vendor__vendor").filter(
            office_vendor__office__company__id=company_id
        )
        monthly = request.query_params.get("monthly", False)
        if monthly:
            last_year_today = (timezone.now() - relativedelta(months=11)).date()
            last_year_today.replace(day=1)
            qs = (
                queryset.filter(order_date__gte=last_year_today)
                .annotate(month=YearMonth("order_date"))
                .values("month")
                .order_by("month")
                .annotate(total_amount=Sum("total_amount"))
            )
        else:
            qs = (
                queryset.values("office_vendor__vendor")
                .order_by("office_vendor__vendor")
                .annotate(total_amount=Sum("total_amount"), vendor=F("office_vendor__vendor__name"))
            )
        serializer = s.TotalSpendSerializer(qs, many=True)
        return Response(serializer.data)
