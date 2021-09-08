import asyncio
from typing import List

from asgiref.sync import sync_to_async
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.models import Company, CompanyMember, Office, OfficeVendor
from apps.common import messages as msgs
from apps.common.asyncdrf import AsyncMixin
from apps.common.pagination import StandardResultsSetPagination
from apps.scrapers.schema import Product as ProductDataClass
from apps.scrapers.scraper_factory import ScraperFactory
from apps.types.orders import LinkedVendor

from . import filters as f
from . import models as m
from . import permissions as p
from . import serializers as s


class OrderViewSet(ModelViewSet):
    queryset = m.Order.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = s.OrderSerializer
    pagination_class = StandardResultsSetPagination
    filterset_class = f.OrderFilter

    def get_serializer_class(self):
        return s.OrderListSerializer if self.action == "list" else self.serializer_class

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = (
            queryset.values("id", "status")
            .annotate(order_date=m.IsoDate("created_at"))
            .annotate(total_amount=Sum("vendor_orders__total_amount"))
            .annotate(total_items=Sum("vendor_orders__total_items"))
        )
        page = self.paginate_queryset(queryset)

        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def get_queryset(self):
        return super().get_queryset().filter(office__id=self.kwargs["office_pk"])


class VendorOrderProductViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = m.VendorOrderProduct.objects.all()
    serializer_class = s.VendorOrderSerializer

    def get_queryset(self):
        return super().get_queryset().filter(order__office__id=self.kwargs["office_pk"])


class CompanyOrderAPIView(APIView, StandardResultsSetPagination):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_id):
        queryset = m.Order.objects.filter(office__company__id=company_id)
        queryset = (
            queryset.values("id", "status")
            .annotate(order_date=m.IsoDate("created_at"))
            .annotate(total_amount=Sum("vendor_orders__total_amount"))
            .annotate(total_items=Sum("vendor_orders__total_items"))
        )
        paginate_queryset = self.paginate_queryset(queryset, request, view=self)
        serializer = s.OrderListSerializer(paginate_queryset, many=True)
        return self.get_paginated_response(serializer.data)


def get_spending(by, orders, company):
    if by == "month":
        last_year_today = (timezone.now() - relativedelta(months=11)).date()
        last_year_today.replace(day=1)
        return (
            orders.filter(order_date__gte=last_year_today)
            .annotate(month=m.YearMonth("order_date"))
            .values("month")
            .order_by("month")
            .annotate(total_amount=Sum("total_amount"))
        )
    else:
        qs = (
            orders.values("vendor_id")
            .order_by("vendor_id")
            .annotate(total_amount=Sum("total_amount"), vendor_name=F("vendor__name"))
        )

        vendor_ids = [q["vendor_id"] for q in qs]
        vendors = OfficeVendor.objects.select_related("vendor").filter(
            office__company=company, vendor_id__in=vendor_ids
        )
        vendors = {v.vendor.id: v for v in vendors}

        return [
            {
                "vendor": {
                    "id": q["vendor_id"],
                    "name": q["vendor_name"],
                    "office_associated_id": vendors[q["vendor_id"]].id,
                },
                "total_amount": q["total_amount"],
            }
            for q in qs
        ]


class CompanySpendAPIView(APIView):
    permission_classes = [p.CompanyOfficeReadPermission]

    def get(self, request, company_id):
        company = get_object_or_404(Company, id=company_id)
        self.check_object_permissions(request, company)
        queryset = m.Order.objects.select_related("vendor").filter(office__company=company)
        data = get_spending(request.query_params.get("by", "vendor"), queryset, company)
        serializer = s.TotalSpendSerializer(data, many=True)
        return Response(serializer.data)


class OfficeSpendAPIView(APIView):
    permission_classes = [p.CompanyOfficeReadPermission]

    def get(self, request, office_id):
        office = get_object_or_404(Office, id=office_id)
        self.check_object_permissions(request, office)
        queryset = m.Order.objects.select_related("vendor").filter(office=office)
        data = get_spending(request.query_params.get("by", "vendor"), queryset, office.company)
        serializer = s.TotalSpendSerializer(data, many=True)
        return Response(serializer.data)


class ProductViewSet(AsyncMixin, ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.ProductSerializer
    queryset = m.Product.objects.all()

    @sync_to_async
    def _get_linked_vendors(self, request) -> List[LinkedVendor]:
        company_member = CompanyMember.objects.filter(user=request.user).first()
        company_vendors = OfficeVendor.objects.select_related("vendor").filter(company=company_member.company)
        return [
            LinkedVendor(
                vendor=company_vendor.vendor.slug, username=company_vendor.username, password=company_vendor.password
            )
            for company_vendor in company_vendors
        ]

    @action(detail=False, methods=["get"], url_path="search")
    async def search_product(self, request, *args, **kwargs):
        q = request.query_params.get("q", "")
        if len(q) <= 3:
            return Response({"message": msgs.SEARCH_QUERY_LIMIT}, status=HTTP_400_BAD_REQUEST)
        session = apps.get_app_config("accounts").session
        data = []
        company_vendors = await self._get_linked_vendors(request)
        tasks = []
        for company_vendor in company_vendors:
            scraper = ScraperFactory.create_scraper(
                scraper_name=company_vendor["vendor"],
                session=session,
                username=company_vendor["username"],
                password=company_vendor["password"],
            )
            tasks.append(scraper.search_products(query=q))

        scrapers_products = await asyncio.gather(*tasks, return_exceptions=True)
        data = [
            product.to_dict()
            for scraper_products in scrapers_products
            for product in scraper_products
            if isinstance(product, ProductDataClass)
        ]

        return Response(data)
