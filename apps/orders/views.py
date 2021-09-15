import asyncio
import operator
from functools import reduce
from typing import List

from asgiref.sync import sync_to_async
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.db import transaction
from django.db.models import F, Q, Sum
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
        queryset = m.VendorOrder.objects.select_related("vendor").filter(order__office__company=company)
        data = get_spending(request.query_params.get("by", "vendor"), queryset, company)
        serializer = s.TotalSpendSerializer(data, many=True)
        return Response(serializer.data)


class OfficeSpendAPIView(APIView):
    permission_classes = [p.CompanyOfficeReadPermission]

    def get(self, request, office_id):
        office = get_object_or_404(Office, id=office_id)
        self.check_object_permissions(request, office)
        queryset = m.VendorOrder.objects.select_related("vendor").filter(order__office=office)
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
        office_vendors = OfficeVendor.objects.select_related("vendor").filter(office__company=company_member.company)
        return list(office_vendors)
        # return [
        #     LinkedVendor(
        #         vendor=office_vendor.vendor.slug, username=office_vendor.username, password=office_vendor.password
        #     )
        #     for office_vendor in office_vendors
        # ]

    @action(detail=False, methods=["get"], url_path="search")
    async def search_product(self, request, *args, **kwargs):
        q = request.query_params.get("q", "")
        page = request.query_params.get("page", 1)

        if len(q) <= 3:
            return Response({"message": msgs.SEARCH_QUERY_LIMIT}, status=HTTP_400_BAD_REQUEST)
        try:
            page = int(page)
        except ValueError:
            return Response({"message": msgs.SEARCH_PAGE_NUMBER_INCORRECT}, status=HTTP_400_BAD_REQUEST)

        session = apps.get_app_config("accounts").session
        office_vendors = await self._get_linked_vendors(request)
        tasks = []
        for office_vendor in office_vendors:
            scraper = ScraperFactory.create_scraper(
                scraper_name=office_vendor.vendor.slug,
                session=session,
                username=office_vendor.username,
                password=office_vendor.password,
                vendor_id=office_vendor.vendor.id,
            )
            tasks.append(scraper.search_products(query=q, page=page))

        scrapers_products = await asyncio.gather(*tasks, return_exceptions=True)
        data = [
            product.to_dict()
            for scraper_products in scrapers_products
            for product in scraper_products
            if isinstance(product, ProductDataClass)
        ]

        return Response(data)


class CartViewSet(AsyncMixin, ModelViewSet):
    permission_classes = [IsAuthenticated]
    model = m.Cart
    serializer_class = s.CartSerializer
    queryset = m.Cart.objects.all()

    def get_queryset(self):
        return self.queryset.filter(office_id=self.kwargs["office_pk"], user=self.request.user)

    def create(self, request, *args, **kwargs):
        request.data.setdefault("user", request.user.id)
        request.data.setdefault("office", self.kwargs["office_pk"])
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    @sync_to_async
    def _pre_checkout_hook(self):
        queryset = (
            self.get_queryset()
            .annotate(vendor_product_id=F("product__product_id"))
            .annotate(vendor_slug=F("product__vendor__slug"))
            # .values("vendor_product_id", "quantity", "office", "vendor")
        )

        q = reduce(
            operator.or_,
            [Q(office=item.office) & Q(vendor=item.product.vendor) for item in queryset],
        )
        office_vendors = OfficeVendor.objects.select_related("vendor").filter(q)

        vendors_order_status = m.OrderProgressStatus.objects.filter(office_vendor__in=office_vendors)
        is_checking = vendors_order_status.exists()
        return queryset, list(office_vendors), vendors_order_status, is_checking

    @sync_to_async
    def _update_vendors_order_status(self, vendors_order_status, status):
        for vendor_order_status in vendors_order_status:
            vendor_order_status.status = status
        m.OrderProgressStatus.objects.bulk_update(vendors_order_status, ["status"])

    @sync_to_async
    def _create_order(self, cart_products):
        with transaction.atomic():
            products = [
                m.Product(
                    vendor=cart_product.vendor,
                    product_id=cart_product.product_id,
                    name=cart_product.name,
                    description=cart_product.description,
                    url=cart_product.url,
                    image=cart_product.image,
                    price=cart_product.price,
                )
                for cart_product in cart_products
            ]
            m.Product.objects.bulk_create(products)

        # order = m.Order.objects(office=office, status="PENDING")
        # for office_vendor in office_vendors:
        #     m.VendorOrder.objects.create(
        #         order=order, vendor=vendor,
        #         vendor_order_id="vendor",
        #         total_amount=1,
        #         total_items=1,
        #         currency="USD",
        #         order_date=timezone.now()
        #         status="PENDING"
        #     )
        #     product = Product.objects.create(
        #         vendor="",
        #         product_id
        #         name
        #         description
        #         url
        #         image
        #         price
        #         retail_price
        #     )
        #     VendorOrderProduct

        cart_products.delete()

    @action(detail=False, url_path="checkout", methods=["get"], permission_classes=[p.OrderCheckoutPermission])
    async def checkout(self, request, *args, **kwargs):
        cart_products, office_vendors, vendors_order_status, is_checking = await self._pre_checkout_hook()
        if is_checking:
            return Response({"message": msgs.ORDER_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)

        await self._update_vendors_order_status(vendors_order_status, status=m.OrderProgressStatus.STATUS.IN_PROGRESS)
        session = apps.get_app_config("accounts").session
        tasks = []
        for office_vendor in office_vendors:
            scraper = ScraperFactory.create_scraper(
                scraper_name=office_vendor.vendor.slug,
                session=session,
                username=office_vendor.username,
                password=office_vendor.password,
            )
            tasks.append(
                scraper.checkout(
                    [product for product in cart_products if product.vendor_slug == office_vendor.vendor.slug]
                )
            )
        await asyncio.gather(*tasks, return_exceptions=True)
        await self._update_vendors_order_status(vendors_order_status, status=m.OrderProgressStatus.STATUS.COMPLETE)
        await self._create_order(cart_products)
        return Response({"message": "okay"})
