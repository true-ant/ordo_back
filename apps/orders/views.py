import asyncio
import decimal
import operator
import os
import tempfile
import zipfile
from datetime import timedelta
from decimal import Decimal
from functools import reduce
from typing import Union
from aiohttp import ClientSession
from asgiref.sync import sync_to_async
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.db import transaction
from django.db.models import Case, Count, F, Q, Sum, Value, When
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.paginator import Paginator
from django_filters.rest_framework import DjangoFilterBackend
from month import Month
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
)
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.models import Company, Office, OfficeBudget, OfficeVendor, Vendor
from apps.accounts.services.offices import OfficeService
from apps.common.choices import ProductStatus
from apps.common import messages as msgs
from apps.common.asyncdrf import AsyncCreateModelMixin, AsyncMixin
from apps.common.pagination import (
    SearchProductPagination,
    SearchProductV2Pagination,
    StandardResultsSetPagination,
)
from apps.common.utils import get_date_range, group_products_from_search_result
from apps.orders.helpers import OfficeProductHelper, ProductHelper
from apps.orders.services.order import OrderService
from apps.scrapers.amazonsearch import AmazonSearchScraper
from apps.scrapers.errors import VendorNotConnected, VendorNotSupported, VendorSiteError
from apps.scrapers.scraper_factory import ScraperFactory
from apps.types.orders import CartProduct
from apps.types.scraper import SmartID

from . import filters as f
from . import models as m
from . import permissions as p
from . import serializers as s
from .tasks import notify_order_creation, search_and_group_products


class OrderViewSet(AsyncMixin, ModelViewSet):
    queryset = m.Order.objects.all()
    permission_classes = [p.OfficeSubscriptionPermission]
    serializer_class = s.OrderSerializer
    pagination_class = StandardResultsSetPagination
    filterset_class = f.OrderFilter

    @sync_to_async
    def _get_vendor_orders(self):
        order = self.get_object()
        vendor_orders = order.vendor_orders.all()
        vendors = [vendor_order.vendor for vendor_order in vendor_orders]
        office_vendors = OfficeVendor.objects.filter(office_id=self.kwargs["office_pk"], vendor__in=vendors)
        office_vendors = {office_vendor.vendor_id: office_vendor for office_vendor in office_vendors}
        ret = []
        for vendor_order in vendor_orders:
            # TODO: filter by order status as well
            if vendor_order.vendor.slug != "ultradent" and not vendor_order.invoice_link:
                continue
            ret.append(
                {
                    "vendor_order_id": vendor_order.vendor_order_id,
                    "invoice_link": vendor_order.invoice_link,
                    "vendor": vendor_order.vendor,
                    "username": office_vendors[vendor_order.vendor.id].username,
                    "password": office_vendors[vendor_order.vendor.id].password,
                }
            )

        return ret

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        # queryset = (
        #     queryset.values("id", "status")
        #     .annotate(order_date=m.IsoDate("created_at"))
        #     .annotate(total_amount=Sum("vendor_orders__total_amount"))
        #     .annotate(total_items=Sum("vendor_orders__total_items"))
        # )
        page = self.paginate_queryset(queryset)

        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def get_queryset(self):
        return super().get_queryset().filter(office__id=self.kwargs["office_pk"])

    # @action(detail=False, methods=["get"], url_path="stats")
    # def get_orders_stats(self, request, *args, **kwargs):
    #     # TODO: this should be removed
    #     office_id = self.kwargs["office_pk"]
    #
    #     total_items = 0
    #     total_amount = 0
    #     average_amount = 0
    #
    #     month = self.request.query_params.get("month", "")
    #     try:
    #         requested_date = datetime.strptime(month, "%Y-%m")
    #     except ValueError:
    #         requested_date = timezone.now().date()
    #
    #     month_first_day = requested_date.replace(day=1)
    #     next_month_first_day = (requested_date + timedelta(days=32)).replace(day=1)
    #
    #     queryset = (
    #         m.Order.objects.filter(
    #             Q(order_date__gte=month_first_day) & Q(order_date__lt=next_month_first_day) & Q(office_id=office_id)
    #         )
    #         .exclude(status__in=[m.OrderStatus.REJECTED, m.OrderStatus.WAITING_APPROVAL])
    #         .annotate(month_total_items=Sum("total_items", distinct=True))
    #         .annotate(month_total_amount=Sum("total_amount", distinct=True))
    #     )
    #     orders_count = queryset.count()
    #     if orders_count:
    #         total_items = queryset[0].month_total_items
    #         total_amount = queryset[0].month_total_amount
    #         average_amount = (total_amount / orders_count).quantize(Decimal(".01"), rounding=decimal.ROUND_UP)
    #
    #     pending_orders_count = m.VendorOrder.objects.filter(
    #         order__office_id=office_id,
    #         status=m.OrderStatus.WAITING_APPROVAL,
    #     ).count()
    #     vendors = (
    #         m.VendorOrder.objects.filter(
    #             Q(order_date__gte=month_first_day)
    #             & Q(order_date__lt=next_month_first_day)
    #             & Q(order__office_id=office_id)
    #         )
    #         .order_by("vendor_id")
    #         .values("vendor_id")
    #         .annotate(order_counts=Count("vendor_id"))
    #         .annotate(order_total_amount=Sum("total_amount"))
    #         .annotate(vendor_name=F("vendor__name"))
    #         .annotate(vendor_logo=F("vendor__logo"))
    #     )
    #
    #     ret = {
    #         "order": {
    #             "order_counts": orders_count,
    #             "pending_order_counts": pending_orders_count,
    #             "total_items": total_items,
    #             "total_amount": total_amount,
    #             "average_amount": average_amount,
    #         },
    #         "vendors": [
    #             {
    #                 "id": vendor["vendor_id"],
    #                 "name": vendor["vendor_name"],
    #                 "logo": f"{vendor['vendor_logo']}",
    #                 "order_counts": vendor["order_counts"],
    #                 "total_amount": vendor["order_total_amount"],
    #             }
    #             for vendor in vendors
    #         ],
    #     }
    #     return Response(ret)

    @action(detail=True, methods=["get"], url_path="invoice-download")
    async def download_invoice(self, request, *args, **kwargs):
        vendor_orders = await self._get_vendor_orders()
        session = apps.get_app_config("accounts").session
        tasks = []
        if len(vendor_orders) == 0:
            return Response({"message": msgs.NO_INVOICE})

        for vendor_order in vendor_orders:
            scraper = ScraperFactory.create_scraper(
                vendor=vendor_order["vendor"],
                session=session,
                username=vendor_order["username"],
                password=vendor_order["password"],
            )
            tasks.append(
                scraper.download_invoice(
                    invoice_link=vendor_order["invoice_link"], order_id=vendor_order["vendor_order_id"]
                )
            )
        ret = await asyncio.gather(*tasks, return_exceptions=True)

        temp = tempfile.NamedTemporaryFile()

        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as zf:
            for vendor_order, content in zip(vendor_orders, ret):
                zf.writestr(f"{vendor_order['vendor'].name}.pdf", content)

        filesize = os.path.getsize(temp.name)
        data = open(temp.name, "rb").read()
        response = HttpResponse(data, content_type="application/zip")
        response["Content-Disposition"] = "attachment; filename=invoice.zip"
        response["Content-Length"] = filesize
        temp.seek(0)
        return response


class VendorOrderViewSet(AsyncMixin, ModelViewSet):
    queryset = m.VendorOrder.objects.all()
    permission_classes = [p.OfficeSubscriptionPermission]
    serializer_class = s.VendorOrderSerializer
    filterset_class = f.VendorOrderFilter
    filter_backends = [OrderingFilter, DjangoFilterBackend]
    ordering_fields = ["order_date", "vendor__name", "total_items", "total_amount", "status"]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return (
            self.queryset.filter(order__office_id=self.kwargs["office_pk"])
            .select_related("order", "vendor", "order__office")
            .order_by("-order_date", "order")
        )

    @sync_to_async
    def get_office_vendor(self):
        vendor_order = self.get_object()
        office_vendor = OfficeVendor.objects.get(office_id=self.kwargs["office_pk"], vendor=vendor_order.vendor)
        return {
            "vendor_order_id": vendor_order.vendor_order_id,
            "order_date": vendor_order.order_date,
            "invoice_link": vendor_order.invoice_link,
            "vendor": vendor_order.vendor,
            "username": office_vendor.username,
            "password": office_vendor.password,
        }

    @action(detail=True, methods=["post"], url_path="approve", permission_classes=[p.OrderApprovalPermission])
    async def approve_order(self, request, *args, **kwargs):
        serializer = s.ApproveRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor_order = await sync_to_async(self.get_object)()

        if vendor_order.status != m.OrderStatus.PENDING_APPROVAL:
            return Response({"message": "this order status is not waiting approval"})

        if serializer.validated_data["is_approved"]:
            await OrderService.approve_vendor_order(
                approved_by=request.user,
                vendor_order=vendor_order,
                validated_data=serializer.validated_data,
                stage=request.META["HTTP_HOST"],
            )
        else:
            await sync_to_async(OrderService.reject_vendor_order)(
                approved_by=request.user, vendor_order=vendor_order, validated_data=serializer.validated_data
            )

        return Response({"message": "okay"})

    @action(detail=True, methods=["get"], url_path="invoice-download")
    async def download_invoice(self, request, *args, **kwargs):
        vendor_order = await self.get_office_vendor()
        if vendor_order["invoice_link"] is None:
            return Response({"message": msgs.NO_INVOICE})

        session = apps.get_app_config("accounts").session

        scraper = ScraperFactory.create_scraper(
            vendor=vendor_order["vendor"],
            session=session,
            username=vendor_order["username"],
            password=vendor_order["password"],
        )
        content = await scraper.download_invoice(
            invoice_link=vendor_order["invoice_link"], order_id=vendor_order["vendor_order_id"]
        )
        temp = tempfile.NamedTemporaryFile()

        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{vendor_order['vendor'].name}{vendor_order['order_date']}.pdf", content)

        filesize = os.path.getsize(temp.name)
        data = open(temp.name, "rb").read()
        response = HttpResponse(data, content_type="application/zip")
        response["Content-Disposition"] = "attachment; filename=invoice.zip"
        response["Content-Length"] = filesize
        temp.seek(0)
        return response

    @action(detail=False, methods=["get"], url_path="stats")
    def get_orders_stats(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        total_items = 0
        total_amount = 0
        average_amount = 0

        requested_date = timezone.now().date()
        preset_date_range = self.request.query_params.get("date_range")

        if not self.request.query_params:
            month_first_day = requested_date.replace(day=1)
            next_month_first_day = (requested_date + timedelta(days=32)).replace(day=1)
            queryset = queryset.filter(Q(order_date__gte=month_first_day) & Q(order_date__lt=next_month_first_day))

        if preset_date_range and (start_end_date := get_date_range(preset_date_range)):
            start_month = Month(start_end_date[0].year, start_end_date[0].month)
            end_month = Month(start_end_date[1].year, start_end_date[1].month)
            budgets_queryset = OfficeBudget.objects.filter(
                Q(office_id=self.kwargs["office_pk"]),
                Q(month__gte=start_month),
                Q(month__lte=end_month),
            )
        else:
            budgets_queryset = OfficeBudget.objects.filter(
                office_id=self.kwargs["office_pk"], month=Month(requested_date.year, requested_date.month)
            )

        budget_stats = budgets_queryset.aggregate(
            total_dental_budget=Sum("dental_budget"),
            total_dental_spend=Sum("dental_spend"),
            total_office_budget=Sum("office_budget"),
            total_office_spend=Sum("office_spend"),
            total_miscellaneous_spend=Sum("miscellaneous_spend"),
        )

        approved_orders_queryset = queryset.exclude(status=m.OrderStatus.PENDING_APPROVAL)
        aggregation = approved_orders_queryset.aggregate(
            total_items=Sum("total_items"), total_amount=Sum("total_amount")
        )
        approved_orders_count = approved_orders_queryset.count()
        if approved_orders_count:
            total_items = aggregation["total_items"]
            total_amount = aggregation["total_amount"]
            average_amount = (total_amount / approved_orders_count).quantize(Decimal(".01"), rounding=decimal.ROUND_UP)

        pending_orders_count = queryset.filter(status=m.OrderStatus.PENDING_APPROVAL).count()

        vendors = (
            queryset.order_by("vendor_id")
            .values("vendor_id")
            .annotate(order_counts=Count("vendor_id"))
            .annotate(order_total_amount=Sum("total_amount"))
            .annotate(vendor_name=F("vendor__name"))
            .annotate(vendor_logo=F("vendor__logo"))
        )

        ret = {
            "order": {
                "order_counts": approved_orders_count,
                "pending_order_counts": pending_orders_count,
                "total_items": total_items,
                "total_amount": total_amount,
                "average_amount": average_amount,
            },
            "budget": {
                field: budget_stats[field]
                for field in (
                    "total_dental_budget",
                    "total_dental_spend",
                    "total_office_budget",
                    "total_office_spend",
                    "total_miscellaneous_spend",
                )
            },
            "vendors": [
                {
                    "id": vendor["vendor_id"],
                    "name": vendor["vendor_name"],
                    "logo": f"{vendor['vendor_logo']}",
                    "order_counts": vendor["order_counts"],
                    "total_amount": vendor["order_total_amount"],
                }
                for vendor in vendors
            ],
        }
        return Response(ret)

    @action(detail=True, methods=["post"], url_path="vendororders-return")
    def update_vendororder_return(self, request, *args, **kwargs):
        print("Update")
        serializer = s.VendorOrderReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor_order = self.get_object()
        
        if serializer.validated_data['return_items']:

            for i, item in enumerate(serializer.validated_data['return_items']):
                vendor_product = m.VendorOrderProduct.objects.get(
                    id=item)
                vendor_product.status = ProductStatus.RETURNED
                vendor_product.save()
        
        return Response()



class VendorOrderProductViewSet(ModelViewSet):
    permission_classes = [p.ProductStatusUpdatePermission, p.OfficeSubscriptionPermission]
    queryset = m.VendorOrderProduct.objects.all()
    serializer_class = s.VendorOrderProductSerializer
    filterset_class = f.VendorOrderProductFilter
    pagination_class = StandardResultsSetPagination

    def update(self, request, *args, **kwargs):
        kwargs.setdefault("partial", True)
        return super().update(request, *args, **kwargs)

    # def get_queryset(self):
    #     category_ordering = self.request.query_params.get("category_ordering")
    #     return (
    #         super()
    #         .get_queryset()
    #         .filter(vendor_order__order__office__id=self.kwargs["office_pk"])
    #         .annotate(
    #             category_order=Case(When(product__category__slug=category_ordering, then=Value(0)), default=Value(1))
    #         )
    #         .order_by("category_order", "product__category__slug", "product__product_id")
    #         .distinct("category_order", "product__category__slug", "product__product_id")
    #     )


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
                    "logo": f"{vendors[q['vendor_id']].vendor.logo}",
                    "office_associated_id": vendors[q["vendor_id"]].id,
                },
                "total_amount": q["total_amount"],
            }
            for q in qs
        ]


def get_inventory_products(office: Union[SmartID, m.Office]):
    if not isinstance(office, m.Office):
        office = get_object_or_404(m.Office, pk=office)

    office_inventory_products = m.OfficeProduct.objects.filter(office=office, is_inventory=True).values(
        "product__product_id", "product__vendor"
    )
    return set(
        [
            f"{office_inventory_product['product__product_id']}-{office_inventory_product['product__vendor']}"
            for office_inventory_product in office_inventory_products
        ]
    )


class CompanySpendAPIView(APIView):
    # TODO: Update proper permission
    permission_classes = [p.CompanyOfficeReadPermission]

    def get(self, request, company_pk):
        company = get_object_or_404(Company, id=company_pk)
        self.check_object_permissions(request, company)
        queryset = m.VendorOrder.objects.select_related("vendor").filter(order__office__company=company)
        data = get_spending(request.query_params.get("by", "vendor"), queryset, company)
        serializer = s.TotalSpendSerializer(data, many=True)
        return Response(serializer.data)


class OfficeSpendAPIView(APIView):
    # TODO: update proper permission
    permission_classes = [p.CompanyOfficeReadPermission]

    def get(self, request, office_pk):
        office = get_object_or_404(Office, id=office_pk)
        self.check_object_permissions(request, office)
        queryset = m.VendorOrder.objects.select_related("vendor").filter(order__office=office)
        data = get_spending(request.query_params.get("by", "vendor"), queryset, office.company)
        serializer = s.TotalSpendSerializer(data, many=True)
        return Response(serializer.data)


class OfficeProductCategoryViewSet(ModelViewSet):
    queryset = m.OfficeProductCategory.objects.all()
    serializer_class = s.OfficeProductCategorySerializer

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(has_category=Case(When(slug="other", then=Value(1)), default=Value(0)))
            .filter(office__id=self.kwargs["office_pk"])
            .order_by("has_category", "name")
        )

    def create(self, request, *args, **kwargs):
        request.data.setdefault("office", self.kwargs["office_pk"])
        request.data.setdefault("predefined", False)
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.predefined:
            return Response({"message": msgs.PRODUCT_CATEGORY_NOT_PERMITTED}, status=HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            office_products = instance.products.all()

            # move products to original uncategorized category
            other_product_category = m.OfficeProductCategory.objects.filter(slug="other", office=instance.office)
            for office_product in office_products:
                office_product.office_product_category = other_product_category

            # this uncommented logic move products to original product category
            # office_product_categories = {}
            # for office_product in office_products:
            #     original_product_category_slug = office_product.product.category.slug
            #     original_product_category = office_product_categories.get(original_product_category_slug)
            #
            #     if original_product_category is None:
            #         original_product_category = m.OfficeProductCategory.objects.filter(
            #             slug=original_product_category_slug, office=instance.office
            #         ).first()
            #         office_product_categories[original_product_category_slug] = original_product_category
            #
            #     office_product.office_product_category = original_product_category

            if office_products:
                m.OfficeProduct.objects.bulk_update(office_products, fields=["office_product_category"])
            instance.delete()

        return Response(status=HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="inventory")
    def get_inventory_view(self, request, *args, **kwargs):
        vendors = {vendor.id: vendor.to_dict() for vendor in m.Vendor.objects.all()}
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True, context={"with_inventory_count": True})
        ret = serializer.data
        for office_product_category in ret:
            vendor_ids = office_product_category.pop("vendor_ids")
            office_product_category["vendors"] = [vendors[vendor_id] for vendor_id in vendor_ids]
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="inventory-vendor")
    def get_inventory_vendor_view(self, request, *args, **kwargs):
        categories = {category.id: category.to_dict() for category in m.OfficeProductCategory.objects.all()}
        queryset = m.Vendor.objects.all()
        serializer = s.OfficeProductVendorSerializer(queryset, many=True, context={"with_inventory_count": True, "office_id":kwargs["office_pk"]})
        ret = serializer.data
        for office_product_vendor in ret:
            category_ids = office_product_vendor.pop("category_ids")
            office_product_vendor["categories"] = [categories[category_id] for category_id in category_ids if category_id != None]
        return Response(serializer.data)


class ProductViewSet(AsyncMixin, ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.ProductSerializer
    filterset_class = f.ProductFilter
    queryset = m.Product.objects.all()

    @action(detail=False, methods=["get"], url_path="suggestion")
    def product_suggestion(self, request, *args, **kwargs):
        # get suggestions from inventory list first
        office_id = request.query_params.get("office")
        q = request.query_params.get("q", "")
        office_products = (
            m.OfficeProduct.objects.select_related("product__images")
            .filter(
                Q(office_id=office_id)
                & Q(product__parent__isnull=True)
                & (
                    Q(product__product_id=q)
                    | Q(product__name__icontains=q)
                    | Q(product__tags__keyword__iexact=q)
                    | Q(product__child__product_id=q)
                    | Q(product__child__name__icontains=q)
                    | Q(product__child__tags__keyword__iexact=q)
                )
            )
            .distinct()
            .order_by("-is_inventory")
            .values("id", "is_inventory", "product__product_id", "product__name", "product__images__image")[:5]
        )
        suggestion_products = [
            {
                "id": product["id"],
                "product_id": product["product__product_id"],
                "name": product["product__name"],
                "image": product["product__images__image"],
                "is_inventory": product["is_inventory"],
            }
            for product in office_products
        ]
        # product_ids = [product["product_id"] for product in suggestion_products]
        # if len(office_products) < 5:
        #     # get suggestions from from product list
        #     products = (
        #         m.Product.objects.select_related("images")
        #         .filter(
        #             Q(parent__isnull=True)
        #             & (
        #                 Q(product_id=q)
        #                 | Q(name__icontains=q)
        #                 | Q(tags__keyword__iexact=q)
        #                 | Q(child__product_id=q)
        #                 | Q(child__name__icontains=q)
        #                 | Q(child__tags__keyword__iexact=q)
        #             )
        #         )
        #         .exclude(product_id__in=product_ids)
        #         .distinct()
        #         .values("product_id", "name", "images__image")[: 5 - len(office_products)]
        #     )
        #     suggestion_products.extend(
        #         [
        #             {
        #                 "id": "",
        #                 "product_id": product["product_id"],
        #                 "name": product["name"],
        #                 "image": product["images__image"],
        #                 "is_inventory": False,
        #             }
        #             for product in products
        #         ]
        #     )

        serializer = s.ProductSuggestionSerializer(suggestion_products, many=True)
        return Response(serializer.data)


class ProductDataViewSet(ModelViewSet):
    serializer_class = s.ProductSerializer
    queryset = m.Product.objects.all()

    def get_queryset(self):
        query = self.request.GET.get("search", "")
        return m.Product.objects.search(query)


def get_office_vendor(office_pk, vendor_pk):
    try:
        return OfficeVendor.objects.get(office_id=office_pk, vendor_id=vendor_pk)
    except OfficeVendor.DoesNotExist:
        return


def get_cart(office_pk):
    cart_products = (
        m.Cart.objects.filter(office_id=office_pk, save_for_later=False, instant_checkout=True)
        .order_by("-updated_at")
        .select_related("product__vendor")
    )
    if not cart_products:
        return cart_products, []
    else:
        vendors = set(cart_product.product.vendor for cart_product in cart_products)
        q = reduce(operator.or_, [Q(office_id=office_pk) & Q(vendor=vendor) for vendor in vendors])
        office_vendors = OfficeVendor.objects.filter(q).select_related("vendor", "office")
        return cart_products, list(office_vendors)


def get_cart_status_and_order_status(office, user):
    if isinstance(office, str) or isinstance(office, int):
        office = m.Office.objects.get(id=office)

    if not hasattr(office, "checkout_status"):
        m.OfficeCheckoutStatus.objects.create(office=office, user=user)

    can_use_cart = (
        office.checkout_status.user == user
        or office.checkout_status.checkout_status == m.OfficeCheckoutStatus.CHECKOUT_STATUS.COMPLETE
    )
    can_create_order = (
        office.checkout_status.user == user
        or office.checkout_status.order_status == m.OfficeCheckoutStatus.ORDER_STATUS.COMPLETE
    )
    return can_use_cart, can_create_order


def update_cart_or_checkout_status(office, user, checkout_status=None, order_status=None):
    office.checkout_status.user = user
    if checkout_status:
        office.checkout_status.checkout_status = checkout_status
    if order_status:
        office.checkout_status.order_status = order_status
    office.checkout_status.save()


def save_serailizer(serializer):
    serializer.save()
    return serializer.data


def get_serializer_data(serializer_class, data, many=True):
    serializer = serializer_class(data, many=True)
    return serializer.data


class CartViewSet(AsyncMixin, AsyncCreateModelMixin, ModelViewSet):
    permission_classes = [p.OfficeSubscriptionPermission]
    model = m.Cart
    serializer_class = s.CartSerializer
    queryset = m.Cart.objects.all()

    def get_queryset(self):
        queryset = self.queryset.filter(office_id=self.kwargs["office_pk"])
        order_by = self.request.query_params.get("by", "vendor")
        if order_by == "time":
            return queryset.order_by("-updated_at")
        else:
            return queryset.order_by("product__vendor", "created_at", "-save_for_later")

    def get_serializer_class(self):
        if self.request.method in ["GET"]:
            return s.CartSerializer
        return s.CartCreateSerializer

    # async def update_vendor_cart(self, product_id, vendor, serializer=None):
    #     office_vendor = await sync_to_async(get_office_vendor)(office_pk=self.kwargs["office_pk"], vendor_pk=vendor.id)
    #     if office_vendor is None:
    #         raise VendorNotConnected()
    #     session = apps.get_app_config("accounts").session
    #     scraper = ScraperFactory.create_scraper(
    #         vendor=vendor,
    #         session=session,
    #         username=office_vendor.username,
    #         password=office_vendor.password,
    #     )
    #     try:
    #         await scraper.remove_product_from_cart(product_id=product_id, use_bulk=False, perform_login=True)
    #     except Exception as e:
    #         raise VendorSiteError(f"{e}")

    #     if not serializer:
    #         return True

    #     updated_save_for_later = serializer.instance and "save_for_later" in serializer.validated_data

    #     if updated_save_for_later and serializer.validated_data["save_for_later"]:
    #         return True

    #     if updated_save_for_later and not serializer.validated_data["save_for_later"]:
    #         quantity = serializer.instance.quantity
    #     else:
    #         quantity = serializer.validated_data["quantity"]

    #     try:
    #         vendor_cart_product = await scraper.add_product_to_cart(
    #             CartProduct(product_id=product_id, product_unit=serializer, quantity=quantity),
    #             perform_login=True,
    #         )
    #         serializer.validated_data["unit_price"] = vendor_cart_product["unit_price"]
    #     except Exception as e:
    #         raise VendorSiteError(f"{e}")

    async def create(self, request, *args, **kwargs):
        data = request.data
        office_pk = self.kwargs["office_pk"]
        data["office"] = office_pk
        can_use_cart, _ = await sync_to_async(get_cart_status_and_order_status)(office=office_pk, user=request.user)
        if not can_use_cart:
            return Response({"message": msgs.CHECKOUT_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)

        serializer = await sync_to_async(self.get_serializer)(data=data)
        await sync_to_async(serializer.is_valid)(raise_exception=True)
        serializer_data = await sync_to_async(save_serailizer)(serializer)
        return Response(serializer_data, status=HTTP_201_CREATED)

    #
    # @sync_to_async
    # def get_object_with_related(self):
    #     instance = self.get_object()
    #     return instance, instance.product.product_id, instance.product.vendor
    #

    @action(detail=True, url_path="change-product", methods=["post"])
    def change_product(self, request, *args, **kwargs):
        instance = self.get_object()
        product_id = request.data.get("product_id")
        unit_price = request.data.get("unit_price")
        product = get_object_or_404(m.Product, product_id=product_id)
        if m.Cart.objects.filter(office_id=self.kwargs["office_pk"], product=product).exists():
            return Response({"message": "This product is already in your cart"}, status=HTTP_400_BAD_REQUEST)
        instance.unit_price = unit_price
        instance.product = product
        instance.save()
        return Response(self.serializer_class(instance).data)

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    # async def update(self, request, *args, **kwargs):
    #     instance, product_id, vendor = await self.get_object_with_related()
    #     can_use_cart, _ = await sync_to_async(get_cart_status_and_order_status)(
    #         office=self.kwargs["office_pk"], user=request.user
    #     )
    #     if not can_use_cart:
    #         return Response({"message": msgs.CHECKOUT_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)
    #
    #     serializer = self.get_serializer(instance, request.data, partial=True)
    #     await sync_to_async(serializer.is_valid)(raise_exception=True)
    #     try:
    #         await self.update_vendor_cart(product_id, vendor, serializer)
    #     except VendorSiteError:
    #         return Response({"message": msgs.VENDOR_SITE_ERROR}, status=HTTP_500_INTERNAL_SERVER_ERROR)
    #     except VendorNotConnected:
    #         return Response({"message": "Vendor not connected"}, status=HTTP_400_BAD_REQUEST)
    #     serializer_data = await sync_to_async(save_serailizer)(serializer)
    #     return Response(serializer_data)
    #
    # async def destroy(self, request, *args, **kwargs):
    #     instance, product_id, vendor = await self.get_object_with_related()
    #     can_use_cart, _ = await sync_to_async(get_cart_status_and_order_status)(
    #         office=self.kwargs["office_pk"], user=request.user
    #     )
    #     if not can_use_cart:
    #         return Response({"message": msgs.CHECKOUT_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)
    #
    #     try:
    #         await self.update_vendor_cart(product_id, vendor)
    #     except VendorSiteError:
    #         return Response({"message": msgs.VENDOR_SITE_ERROR}, status=HTTP_500_INTERNAL_SERVER_ERROR)
    #     except VendorNotConnected:
    #         return Response({"message": "Vendor not connected"}, status=HTTP_400_BAD_REQUEST)
    #     await sync_to_async(self.perform_destroy)(instance)
    #     return Response(status=HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="clear")
    def clear_cart(self, request, *args, **kwargs):
        serializer = s.ClearCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart_products = self.get_queryset()
        if serializer.validated_data["remove"] == "save_for_later":
            cart_products.filter(save_for_later=True).delete()
        elif serializer.validated_data["remove"] == "cart":
            cart_products.filter(save_for_later=False).delete()
        return Response({"message": msgs.SUCCESS})

    @sync_to_async
    def _create_order(self, office_vendors, vendor_order_results, cart_products, approval_needed, data):
        order_date = timezone.now().date()
        office = office_vendors[0].office
        vendor_order_ids = []
        with transaction.atomic():
            order = m.Order.objects.create(
                office_id=self.kwargs["office_pk"],
                created_by=self.request.user,
                order_date=order_date,
                status=m.OrderStatus.PENDING_APPROVAL if approval_needed else m.OrderStatus.OPEN,
                order_type=msgs.ORDER_TYPE_ORDO
            )
            total_amount = 0.0
            total_items = 0.0

            for office_vendor, vendor_order_result in zip(office_vendors, vendor_order_results):
                if not isinstance(vendor_order_result, dict):
                    continue

                vendor = office_vendor.vendor
                vendor_order_id = vendor_order_result.get("order_id", "")
                if vendor_order_id == None: vendor_order_id="invalid"
                vendor_total_amount = vendor_order_result.get("total_amount", 0.0)
                total_amount += float(vendor_total_amount)
                vendor_order_products = cart_products.filter(product__vendor=vendor)
                total_items += (vendor_total_items := vendor_order_products.count())
                order_type = vendor_order_result.get("order_type", msgs.ORDER_TYPE_ORDO)
                if order_type == msgs.ORDER_TYPE_REDUNDANCY:
                    order.order_type = order_type
                vendor_order = m.VendorOrder.objects.create(
                    order=order,
                    vendor=office_vendor.vendor,
                    vendor_order_id=vendor_order_id,
                    total_amount=vendor_total_amount,
                    total_items=vendor_total_items,
                    currency="USD",
                    order_date=order_date,
                    status=m.OrderStatus.PENDING_APPROVAL if approval_needed else m.OrderStatus.OPEN,
                )
                vendor_order_ids.append(vendor_order.id)
                objs = []
                for vendor_order_product in vendor_order_products:
                    objs.append(
                        m.VendorOrderProduct(
                            vendor_order=vendor_order,
                            product=vendor_order_product.product,
                            quantity=vendor_order_product.quantity,
                            unit_price=vendor_order_product.unit_price,
                            status=m.ProductStatus.PENDING_APPROVAL if approval_needed else m.ProductStatus.PROCESSING,
                        )
                    )
                m.VendorOrderProduct.objects.bulk_create(objs)

            order.total_amount = total_amount
            order.total_items = total_items
            order.save()

            update_cart_or_checkout_status(
                office=office_vendors[0].office,
                user=self.request.user,
                checkout_status=m.OfficeCheckoutStatus.CHECKOUT_STATUS.COMPLETE,
                order_status=m.OfficeCheckoutStatus.ORDER_STATUS.COMPLETE,
            )

            current_date = timezone.now().date()
            month = Month(year=current_date.year, month=current_date.month)
            office_budget = office.budgets.filter(month=month).first()
            if office_budget:
                office_budget.dental_spend = F("dental_spend") + total_amount
                office_budget.save()

        cart_products.delete()

        notify_order_creation.delay(vendor_order_ids, approval_needed)
        return s.OrderSerializer(order).data

    @action(detail=False, url_path="checkout", methods=["get"], permission_classes=[p.OrderCheckoutPermission])
    async def checkout(self, request, *args, **kwargs):
        can_use_cart = await sync_to_async(get_cart_status_and_order_status)(
            office=self.kwargs["office_pk"], user=request.user
        )
        if not can_use_cart:
            return Response({"message": msgs.CHECKOUT_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)

        cart_products, office_vendors = await sync_to_async(get_cart)(office_pk=self.kwargs["office_pk"])
        if not cart_products:
            return Response({"can_checkout": False, "message": msgs.EMPTY_CART}, status=HTTP_400_BAD_REQUEST)

        await sync_to_async(update_cart_or_checkout_status)(
            office=office_vendors[0].office,
            user=request.user,
            checkout_status=m.OfficeCheckoutStatus.CHECKOUT_STATUS.IN_PROGRESS,
        )
        ret = {}
        try:
            conf = apps.get_app_config("accounts")
            if hasattr(conf, 'session'):
                session = conf.session
            else:
                session = ClientSession()
            tasks = []
            tmp_variables = []
            for office_vendor in office_vendors:
                scraper = ScraperFactory.create_scraper(
                    vendor=office_vendor.vendor,
                    session=session,
                    username=office_vendor.username,
                    password=office_vendor.password,
                )
                tmp_variables.append(
                    sum(
                        [
                            cart_product.quantity * (cart_product.unit_price if isinstance(cart_product.unit_price, (int, float,Decimal)) else 0)
                            for cart_product in cart_products
                            if cart_product.product.vendor.id == office_vendor.vendor.id
                        ]
                    )
                )
                tasks.append(
                    scraper.create_order(
                        [
                            CartProduct(
                                product_id=cart_product.product.product_id,
                                product_unit=cart_product.product.product_unit,
                                quantity=int(cart_product.quantity),
                                price=cart_product.unit_price if isinstance(cart_product.unit_price, (int, float,Decimal)) else 0,
                                product_url=cart_product.product.url
                            )
                            for cart_product in cart_products
                            if cart_product.product.vendor.id == office_vendor.vendor.id
                        ]
                    )
                )
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                vendor_slug = list(result.keys())[0]
                if vendor_slug not in ("henry_schein", "implant_direct", "darby", "benco", "net_32", "patterson", "dental_city"):
                    result[vendor_slug]["retail_amount"] = Decimal(0)
                    result[vendor_slug]["savings_amount"] = Decimal(0)
                    result[vendor_slug]["subtotal_amount"] = tmp_variables[i]
                    result[vendor_slug]["shipping_amount"] = Decimal(0)
                    result[vendor_slug]["tax_amount"] = Decimal(0)
                    result[vendor_slug]["total_amount"] = tmp_variables[i]
                ret.update(result)
            await session.close()
        except Exception as e:
            await session.close()
            return Response({"message": f"{e}"}, status=HTTP_400_BAD_REQUEST)

        products = await sync_to_async(get_serializer_data)(s.CartSerializer, cart_products, many=True)
        return Response({"products": products, "order_details": ret})

    @action(detail=False, url_path="confirm-order", methods=["post"], permission_classes=[p.OrderCheckoutPermission])
    async def confirm_order(self, request, *args, **kwargs):
        data = request.data["data"]
        shipping_options = request.data["shipping_options"]

        cart_products, office_vendors = await sync_to_async(get_cart)(office_pk=self.kwargs["office_pk"])

        if not cart_products:
            return Response({"can_checkout": False, "message": msgs.EMPTY_CART}, status=HTTP_400_BAD_REQUEST)

        conf = apps.get_app_config("accounts")
        if hasattr(conf, 'session'):
            session = apps.get_app_config("accounts").session
        else:
            session = ClientSession()
        tasks = []
        debug = OrderService.is_debug_mode(request.META["HTTP_HOST"])

        # check order app
        if request.user.role == m.User.Role.ADMIN:
            order_approval_needed = False
        else:
            # total_amount = sum(
            #     [Decimal(str(vendor_data["total_amount"])) for vendor, vendor_data in data.items() if
            #      vendor != "amazon"]
            # )

            remaining_budget = await sync_to_async(OfficeService.get_office_remaining_budget)(
                office_pk=self.kwargs["office_pk"]
            )
            office_setting = await sync_to_async(OfficeService.get_office_setting)(office_pk=self.kwargs["office_pk"])
            order_approval_needed = (office_setting.requires_approval_notification_for_all_orders is True) or (
                office_setting.requires_approval_notification_for_all_orders is False
                and remaining_budget[0] < office_setting.budget_threshold
            )

        fake_order = debug or order_approval_needed

        for office_vendor in office_vendors:
            # vendor_slug = vendor_data["slug"]
            scraper = ScraperFactory.create_scraper(
                vendor=office_vendor.vendor,
                session=session,
                username=office_vendor.username,
                password=office_vendor.password,
            )

            if hasattr(scraper, "confirm_order"):
                tasks.append(
                    scraper.confirm_order(
                        [
                            CartProduct(
                                product_id=cart_product.product.product_id,
                                product_unit=cart_product.product.product_unit,
                                product_url=cart_product.product.url,
                                price=cart_product.unit_price if isinstance(cart_product.unit_price, (int, float,Decimal)) else 0,
                                quantity=int(cart_product.quantity),
                            )
                            for cart_product in cart_products
                            if cart_product.product.vendor.id == office_vendor.vendor.id
                        ],
                        shipping_method=shipping_options.get(office_vendor.vendor.slug),
                        fake=fake_order,
                    )
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        order_data = await self._create_order(office_vendors, results, cart_products, order_approval_needed, data)
        await session.close()
        return Response(order_data)

    @action(detail=False, url_path="add-multiple-products", methods=["post"])
    def add_multiple_products(self, request, *args, **kwargs):
        data = request.data
        office_pk = self.kwargs["office_pk"]
        can_use_cart, _ = get_cart_status_and_order_status(office=office_pk, user=request.user)
        if not can_use_cart:
            return Response({"message": msgs.CHECKOUT_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)

        serializer = s.CartCreateSerializer(data=data, many=True)
        serializer.is_valid(raise_exception=True)
        serializer_data = save_serailizer(serializer)
        return Response(serializer_data, status=HTTP_201_CREATED)

        # products = request.data
        # office_pk = self.kwargs["office_pk"]
        # can_use_cart, _ = await sync_to_async(get_cart_status_and_order_status)(office=office_pk, user=request.user)
        # if not can_use_cart:
        #     return Response({"message": msgs.CHECKOUT_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)
        # if not isinstance(products, list):
        #     return Response({"message": msgs.PAYLOAD_ISSUE}, status=HTTP_400_BAD_REQUEST)
        # result = []
        # for product in products:
        #     product["office"] = office_pk
        #     serializer = self.get_serializer(data=product)
        #     await sync_to_async(serializer.is_valid)(raise_exception=True)
        #     product_id = serializer.validated_data["office_product"]["product"]["product_id"]
        #     product_url = serializer.validated_data["office_product"]["product"]["url"]
        #     vendor = serializer.validated_data["office_product"]["product"]["vendor"]
        #     product_category = serializer.validated_data["office_product"]["product"]["category"]
        #     serializer.validated_data["unit_price"] = serializer.validated_data["office_product"]["price"]
        #     #     try:
        #     #         await self.update_vendor_cart(
        #     #             product_id,
        #     #             vendor,
        #     #             serializer,
        #     #         )
        #     if not product_category:
        #         update_product_detail.delay(product_id, product_url, office_pk, vendor.id)
        #         # except VendorSiteError as e:
        #         #     return Response(
        #         #         {"message": f"{msgs.VENDOR_SITE_ERROR} - {e}"},
        #         #         status=HTTP_500_INTERNAL_SERVER_ERROR
        #         #     )
        #         # except VendorNotConnected:
        #         #     return Response({"message": "Vendor not connected"}, status=HTTP_400_BAD_REQUEST)
        #     serializer_data = await sync_to_async(save_serailizer)(serializer)
        #     result.append(serializer_data)
        # return Response(result, status=HTTP_201_CREATED)


class CheckoutAvailabilityAPIView(APIView):
    permission_classes = [p.OrderCheckoutPermission, p.OfficeSubscriptionPermission]

    def get(self, request, *args, **kwargs):
        cart_products, office_vendors = get_cart(office_pk=kwargs.get("office_pk"))
        if not cart_products:
            return Response({"message": msgs.EMPTY_CART}, status=HTTP_400_BAD_REQUEST)

        can_use_cart, _ = get_cart_status_and_order_status(office=office_vendors[0].office, user=request.user)
        return Response({"can_use_cart": can_use_cart})


class CheckoutUpdateStatusAPIView(APIView):
    permission_classes = [p.OrderCheckoutPermission, p.OfficeSubscriptionPermission]

    def post(self, request, *args, **kwargs):
        cart_products, office_vendors = get_cart(office_pk=kwargs.get("office_pk"))
        if not cart_products:
            return Response({"message": msgs.EMPTY_CART}, status=HTTP_400_BAD_REQUEST)

        office = office_vendors[0].office
        serializer = s.OfficeCheckoutStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if office.checkout_status.checkout_status and office.checkout_status.user != request.user:
            return Response({"message": msgs.WAIT_UNTIL_ORDER_FINISH}, status=HTTP_400_BAD_REQUEST)
        else:
            update_cart_or_checkout_status(
                office=office,
                user=request.user,
                checkout_status=serializer.validated_data["checkout_status"],
            )
            return Response({"message": "Status updated successfully"})


class OfficeProductViewSet(AsyncMixin, ModelViewSet):
    queryset = m.OfficeProduct.objects.all()
    serializer_class = s.OfficeProductSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [p.OfficeSubscriptionPermission]
    filterset_class = f.OfficeProductFilter

    def get_serializer_context(self):
        ret = super().get_serializer_context()
        ret["office_pk"] = self.kwargs["office_pk"]
        ret["include_children"] = True
        ret["filter_inventory"] = self.request.query_params.get("inventory", False)
        return ret

    def get_queryset(self):
        category_ordering = self.request.query_params.get("category_ordering")
        category_or_price = self.request.query_params.get("category_or_price", "price")
        price_from = self.request.query_params.get("price_from", -1)
        price_to = self.request.query_params.get("price_to", -1)
        queryset = (
            super()
            .get_queryset()
            .filter(Q(office__id=self.kwargs["office_pk"]), Q(product__parent__isnull=True))
            .annotate(
                category_order=Case(
                    When(office_product_category__slug=category_ordering, then=Value(0)),
                    When(office_product_category__slug="other", then=Value(2)),
                    default=Value(1),
                )
            )
        ).distinct()

        if price_from != -1:
            queryset = queryset.filter(price__gte=price_from)
        if price_to != -1:
            queryset = queryset.filter(price__lte=price_to)
            
        if category_or_price == "category":
            return queryset.order_by("category_order", "office_product_category__slug", "price", "-updated_at")
        else:
            return queryset.order_by("price", "category_order", "office_product_category__slug", "-updated_at")

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="remove")
    def remove_from_inventory(self, request, *args, **kwargs):
        instance = self.get_object()
        other_category = m.OfficeProductCategory.objects.filter(office=instance.office, slug="other").first()
        instance.office_product_category = other_category
        instance.save()
        return Response({"message": "Deleted successfully"}, status=HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="prices")
    async def get_product_prices(self, request, *args, **kwargs):
        serializer = s.ProductPriceRequestSerializer(data=request.data)
        await sync_to_async(serializer.is_valid)(raise_exception=True)
        products = {product.id: product for product in serializer.validated_data["products"]}
        response = await OfficeProductHelper.get_product_prices(products=products, office=self.kwargs["office_pk"])
        return Response(response)


class SearchProductAPIView(AsyncMixin, APIView, SearchProductPagination):
    # queryset = m.OfficeProduct.objects.all()
    # serializer_class = s.OfficeProductSerializer
    # pagination_class = SearchProductPagination
    permission_classes = [p.OfficeSubscriptionPermission]

    def get_queryset(self):
        data = self.request.data
        keyword = data.get("q")
        pagination_meta = data.get("meta", {})
        min_price = data.get("min_price", 0)
        max_price = data.get("max_price", 0)
        vendors_slugs = [vendor_meta["vendor"] for vendor_meta in pagination_meta.get("vendors", [])]
        queryset = m.OfficeProduct.objects.filter(
            Q(office__id=self.kwargs["office_pk"])
            & Q(product__parent__isnull=True)
            & Q(is_inventory=False)
            & (
                Q(product__product_id=keyword)
                | Q(product__name__search=keyword)
                | Q(product__tags__keyword__iexact=keyword)
                | Q(product__child__product_id=keyword)
                | Q(product__child__name__icontains=keyword)
                | Q(product__child__tags__keyword__iexact=keyword)
            )
        )

        product_filters = Q()
        if min_price:
            product_filters &= Q(price__gte=min_price)

        if max_price:
            product_filters &= Q(price__lte=max_price)

        if vendors_slugs:
            product_filters &= Q(product__vendor__slug__in=vendors_slugs)

        if product_filters:
            queryset = queryset.filter(product_filters)
        return queryset.distinct().order_by("price")

    def get_linked_vendors(self):
        office_vendors = OfficeVendor.objects.select_related("vendor").filter(office_id=self.kwargs["office_pk"])
        return list(office_vendors)

    def has_keyword_history(self, keyword: str):
        keyword = keyword.lower()
        office_vendors = self.get_linked_vendors()
        # new_office_vendors is a list of vendors which we haven't search history yet
        vendors_to_be_scraped = []
        vendors_to_be_waited = []
        pagination_meta = self.request.data.get("meta", {})
        vendors_slugs = [
            vendor_meta["vendor"]
            for vendor_meta in pagination_meta.get("vendors", [])
            if vendor_meta["vendor"] != "amazon"
        ]
        amazon_linked = False
        for office_vendor in office_vendors:
            if (
                office_vendor.vendor.slug in ["ultradent", "amazon", "edge_endo"]
                or vendors_slugs
                and office_vendor.vendor.slug not in vendors_slugs
            ):
                amazon_linked = True
                continue

            keyword_obj, _ = m.Keyword.objects.get_or_create(keyword=keyword)
            office_keyword_obj, _ = m.OfficeKeyword.objects.get_or_create(
                keyword=keyword_obj, office_id=self.kwargs["office_pk"], vendor=office_vendor.vendor
            )
            if office_keyword_obj.task_status in [
                m.OfficeKeyword.TaskStatus.NOT_STARTED,
                m.OfficeKeyword.TaskStatus.FAILED,
            ]:
                vendors_to_be_scraped.append(office_vendor.vendor.id)
            elif office_keyword_obj.task_status in [
                m.OfficeKeyword.TaskStatus.IN_PROGRESS,
                m.OfficeKeyword.TaskStatus.FETCHING_COMPLETE,
            ]:
                vendors_to_be_waited.append(office_vendor.vendor.id)

        if vendors_to_be_scraped:
            search_and_group_products.delay(keyword, self.kwargs["office_pk"], vendors_to_be_scraped)
            return False, amazon_linked
        if vendors_to_be_waited:
            return True, amazon_linked
        return True, amazon_linked

    @sync_to_async
    def get_products_from_db(self, *args, **kwargs):
        queryset = self.get_queryset()
        requested_vendors = kwargs.get("requested_vendors", None)
        if requested_vendors:
            queryset = queryset.filter(product__vendor__slug__in=requested_vendors)

        try:
            page = self.paginate_queryset(queryset, self.request, view=self)
        except NotFound:
            page = []
        serializer = s.OfficeProductSerializer(page, many=True, context={"include_children": True})
        data = serializer.data
        # amazon search
        amazon_search_result = kwargs.get("amazon")
        if amazon_search_result:
            amazon_search = True
            amazon_total_size = amazon_search_result["total_size"]
            amazon_last_page = amazon_search_result["last_page"]
            amazon_page = amazon_search_result["page"]
            for amazon_product in amazon_search_result["products"]:
                product_data = amazon_product.to_dict()
                price = product_data.pop("price")
                data.append(
                    {
                        "id": None,
                        "product": product_data,
                        "price": price,
                        "office_product_category": None,
                        "is_favorite": False,
                        "is_inventory": False,
                    }
                )

        else:
            amazon_search = False
            amazon_total_size = 0
            amazon_last_page = True
            amazon_page = 0

        return self.get_paginated_response(
            data,
            amazon_search=amazon_search,
            amazon_total_size=amazon_total_size,
            amazon_page=amazon_page,
            amazon_last_page=amazon_last_page,
        )

    async def fetch_products(self, keyword, min_price, max_price, vendors=None, include_amazon=False):
        pagination_meta = self.request.data.get("meta", {})
        vendors_meta = {vendor_meta["vendor"]: vendor_meta for vendor_meta in pagination_meta.get("vendors", [])}
        session = apps.get_app_config("accounts").session
        office_vendors = await sync_to_async(self.get_linked_vendors)()
        tasks = []
        for office_vendor in office_vendors:
            vendor_slug = office_vendor.vendor.slug
            if vendor_slug == "amazon" and include_amazon is False:
                continue

            if vendors and vendor_slug not in vendors:
                continue

            if vendors_meta.keys() and vendor_slug not in vendors_meta.keys():
                continue

            if vendors_meta.get(vendor_slug, {}).get("last_page", False):
                continue
            try:
                scraper = ScraperFactory.create_scraper(
                    vendor=office_vendor.vendor,
                    session=session,
                    username=office_vendor.username,
                    password=office_vendor.password,
                )
            except VendorNotSupported:
                continue
            current_page = vendors_meta.get(vendor_slug, {}).get("page", 0)
            tasks.append(
                scraper.search_products(query=keyword, page=current_page + 1, min_price=min_price, max_price=max_price)
            )
        search_results = await asyncio.gather(*tasks, return_exceptions=True)
        return search_results

    async def post(self, request, *args, **kwargs):
        data = request.data
        keyword = data.get("q")
        keyword = keyword.strip()
        pagination_meta = data.get("meta", {})
        include_amazon = data.get("include_amazon", False)
        requested_vendors = data.get("vendors", [])

        if pagination_meta.get("last_page", False):
            return Response({"message": msgs.NO_SEARCH_PRODUCT_RESULT}, status=HTTP_400_BAD_REQUEST)

        # if len(keyword) <= 3:
        #     return Response({"message": msgs.SEARCH_QUERY_LIMIT}, status=HTTP_400_BAD_REQUEST)

        has_history, amazon_linked = await sync_to_async(self.has_keyword_history)(keyword)
        try:
            min_price = data.get("min_price", 0)
            max_price = data.get("max_price", 0)
            min_price = int(min_price)
            max_price = int(max_price)
        except ValueError:
            return Response({"message": msgs.SEARCH_PRODUCT_WRONG_PARAMETER}, status=HTTP_400_BAD_REQUEST)

        if has_history:
            amazon_result = None
            if amazon_linked and include_amazon:
                search_results = await self.fetch_products(
                    keyword, min_price, max_price, vendors=["amazon"], include_amazon=True
                )
                amazon_result = search_results[0]

            return await self.get_products_from_db(requested_vendors=requested_vendors, amazon=amazon_result)

        search_results = await self.fetch_products(
            keyword, min_price, max_price, vendors=requested_vendors, include_amazon=False
        )
        updated_vendor_meta, products = group_products_from_search_result(search_results)
        if "vendors" in pagination_meta:
            for updated_vendor_meta in updated_vendor_meta["vendors"]:
                vendor_meta = [
                    vendor_meta
                    for vendor_meta in pagination_meta["vendors"]
                    if vendor_meta["vendor"] == updated_vendor_meta["vendor"]
                ][0]
                vendor_meta["page"] = updated_vendor_meta["page"]
                vendor_meta["last_page"] = updated_vendor_meta["last_page"]

            pagination_meta["last_page"] = all(vendor_meta["last_page"] for vendor_meta in pagination_meta["vendors"])
        else:
            pagination_meta = updated_vendor_meta

        # exclude inventory products
        inventory_products = await sync_to_async(get_inventory_products)(self.kwargs["office_pk"])
        results = []
        for product_or_products in products:
            if isinstance(product_or_products, list):
                ret = []
                for product in product_or_products:
                    key = f"{product['product_id']}-{product['vendor']['id']}"
                    if key in inventory_products:
                        continue
                    ret.append(product)
            else:
                key = (
                    f"{product_or_products['product']['product_id']}-{product_or_products['product']['vendor']['id']}"
                )
                if key in inventory_products:
                    continue
                ret = product_or_products
            if ret:
                results.append(ret)

        return Response({"meta": pagination_meta, "products": results})


class ProductV2ViewSet(AsyncMixin, ModelViewSet):
    queryset = m.Product.objects.all()
    serializer_class = s.ProductV2Serializer
    pagination_class = SearchProductV2Pagination
    filterset_class = f.ProductV2Filter
    http_method_names = ["get"]

    def get_queryset(self):
        query = self.request.GET.get("search", "")
        office_pk = self.request.query_params.get("office_pk")
        selected_products = self.request.query_params.get("selected_products")
        selected_products = selected_products.split(",") if selected_products else []
        price_from = self.request.query_params.get("price_from")
        price_to= self.request.query_params.get("price_to")

        products, available_vendors = ProductHelper.get_products_v3(
            query=query,
            office=office_pk,
            fetch_parents=True,
            selected_products=selected_products,
            price_from=price_from,
            price_to=price_to
        )
        self.available_vendors = available_vendors
        
        return products
        # products = m.Product.objects.search(query)
        # product_ids = products.values_list("id", flat=True)
        # return ProductHelper.get_products_v2(
        #     office=office_pk, fetch_parents=True, selected_products=selected_products, product_ids=product_ids
        # )

    def get_serializer_context(self):
        serializer_context = super().get_serializer_context()
        office_pk = self.request.query_params.get("office_pk")
        vendors = self.request.query_params.get("vendors")
        if vendors:
            vendors = vendors.split(",")
        serializer_context = {**serializer_context, "office_pk": office_pk, "vendors": vendors}
        return serializer_context

    def list(self, request, *args, **kwargs):
        query = self.request.GET.get("search", "")
        queryset = self.filter_queryset(self.get_queryset())

        list1 = list(queryset)

        amazon_inc = self.request.query_params.get("vendors", "").count("amazon") > 0
        if amazon_inc:
            # Add on the fly results
            try:
                products_fly = AmazonSearchScraper()._search_products(query)
            except:
                products_fly = {"products":[]}
            # log += products_fly['log']
            if(len(products_fly['products']) > 0):
                list1.extend(products_fly['products'])
                self.available_vendors.append("amazon")

        count_per_page = int(self.request.query_params.get("per_page", 10))
        current_page = int(self.request.query_params.get("page", 1))
        pagination_obj = Paginator(list1, count_per_page)

        ret = {
            "vendor_slugs": getattr(self, "available_vendors", None),
            "products": [],
        }

        if current_page < 1 or pagination_obj.num_pages < current_page:
            return Response(
                {
                    "message": "The page number is incorrect!"
                },
                status=HTTP_400_BAD_REQUEST
            )

        page = pagination_obj.page(current_page)

        if page is not None:
            product_data = []
            for page_item in page:
                if isinstance(page_item, m.Product):
                    serializer = self.get_serializer(page_item)
                    serialized_data = serializer.data
                    serialized_data["searched_data"] = False
                    product_data.append(serializer.data)
                else:
                    page_item["searched_data"] = True
                    product_data.append(page_item)
            ret["products"] = product_data
            bottom = (current_page - 1) * count_per_page
            top = bottom + count_per_page

            return Response(
                {
                    "total": -1,
                    "from": bottom + 1,
                    "to": top,
                    "per_page": count_per_page,
                    "current_page": page.number,
                    "next_page": page.next_page_number() if page.has_next() else None,
                    "prev_page": page.previous_page_number() if page.has_previous() else None,
                    "data": ret,
                    # "log": log,
                }
            )            

        serializer = self.get_serializer(list1, many=True)
        ret["products"] = serializer.data
        return Response(ret)

    @action(detail=False, url_path="search/vendors")
    async def search_from_vendors(self, request, *args, **kwargs):
        # Currently, we support amazon search on-the-fly
        serializer = s.VendorProductSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        await OfficeProductHelper.get_products_from_vendors(
            vendor_slugs=["amazon"],
            office_id=self.kwargs.get("office_pk"),
            q=serializer.validated_data["q"],
            min_price=serializer.validated_data["min_price"],
            max_price=serializer.validated_data["max_price"],
        )

    @action(detail=False, url_path="suggest", methods=["get"])
    def get_product_suggestion(self, request, *args, **kwargs):
        suggested_products = ProductHelper.suggest_products(
            search=request.query_params.get("search"), office=request.query_params.get("office_pk")
        )[:5]
        return Response(s.SimpleProductSerializer(suggested_products, many=True).data)
