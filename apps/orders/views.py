import asyncio
import decimal
import operator
import os
import tempfile
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal
from functools import reduce
from typing import Union

from asgiref.sync import sync_to_async
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.db import transaction
from django.db.models import Case, Count, F, Q, Sum, Value, When
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_201_CREATED, HTTP_400_BAD_REQUEST
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.models import Company, Office, OfficeVendor
from apps.common import messages as msgs
from apps.common.asyncdrf import AsyncMixin
from apps.common.pagination import SearchProductPagination, StandardResultsSetPagination
from apps.common.utils import group_products_from_search_result
from apps.scrapers.errors import VendorNotConnected, VendorNotSupported, VendorSiteError
from apps.scrapers.scraper_factory import ScraperFactory
from apps.types.orders import CartProduct
from apps.types.scraper import SmartID

from . import filters as f
from . import models as m
from . import permissions as p
from . import serializers as s
from .tasks import (
    notify_order_creation,
    search_and_group_products,
    update_product_detail,
)


class OrderViewSet(AsyncMixin, ModelViewSet):
    queryset = m.Order.objects.all()
    permission_classes = [IsAuthenticated]
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

    @action(detail=False, methods=["get"], url_path="stats")
    def get_orders_stats(self, request, *args, **kwargs):
        office_id = self.kwargs["office_pk"]

        total_items = 0
        total_amount = 0
        average_amount = 0

        month = self.request.query_params.get("month", "")
        try:
            requested_date = datetime.strptime(month, "%Y-%m")
        except ValueError:
            requested_date = timezone.now().date()

        month_first_day = requested_date.replace(day=1)
        next_month_first_day = (requested_date + timedelta(days=32)).replace(day=1)

        queryset = (
            m.Order.objects.filter(
                Q(order_date__gte=month_first_day) & Q(order_date__lt=next_month_first_day) & Q(office_id=office_id)
            )
            .annotate(month_total_items=Sum("total_items", distinct=True))
            .annotate(month_total_amount=Sum("total_amount", distinct=True))
        )
        orders_count = queryset.count()
        if orders_count:
            total_items = queryset[0].month_total_items
            total_amount = queryset[0].month_total_amount
            average_amount = (total_amount / orders_count).quantize(Decimal(".01"), rounding=decimal.ROUND_UP)

        vendors = (
            m.VendorOrder.objects.filter(
                Q(order_date__gte=month_first_day)
                & Q(order_date__lt=next_month_first_day)
                & Q(order__office_id=office_id)
            )
            .order_by("vendor_id")
            .values("vendor_id")
            .annotate(order_counts=Count("vendor_id"))
            .annotate(order_total_amount=Sum("total_amount"))
            .annotate(vendor_name=F("vendor__name"))
            .annotate(vendor_logo=F("vendor__logo"))
        )

        ret = {
            "order": {
                "order_counts": orders_count,
                "total_items": total_items,
                "total_amount": total_amount,
                "average_amount": average_amount,
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


class VendorOrderProductViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = m.VendorOrderProduct.objects.all()
    serializer_class = s.VendorOrderProductSerializer
    filterset_class = f.VendorOrderProductFilter
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        category_ordering = self.request.query_params.get("category_ordering")
        return (
            super()
            .get_queryset()
            .filter(vendor_order__order__office__id=self.kwargs["office_pk"])
            .annotate(
                category_order=Case(When(product__category__slug=category_ordering, then=Value(0)), default=Value(1))
            )
            .order_by("category_order", "product__category__slug", "product__product_id")
            .distinct("category_order", "product__category__slug", "product__product_id")
        )


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
    permission_classes = [p.CompanyOfficeReadPermission]

    def get(self, request, company_pk):
        company = get_object_or_404(Company, id=company_pk)
        self.check_object_permissions(request, company)
        queryset = m.VendorOrder.objects.select_related("vendor").filter(order__office__company=company)
        data = get_spending(request.query_params.get("by", "vendor"), queryset, company)
        serializer = s.TotalSpendSerializer(data, many=True)
        return Response(serializer.data)


class OfficeSpendAPIView(APIView):
    permission_classes = [p.CompanyOfficeReadPermission]

    def get(self, request, office_pk):
        office = get_object_or_404(Office, id=office_pk)
        self.check_object_permissions(request, office)
        queryset = m.VendorOrder.objects.select_related("vendor").filter(order__office=office)
        data = get_spending(request.query_params.get("by", "vendor"), queryset, office.company)
        serializer = s.TotalSpendSerializer(data, many=True)
        return Response(serializer.data)


class ProductCategoryViewSet(ModelViewSet):
    queryset = m.ProductCategory.objects.all()
    serializer_class = s.ProductCategorySerializer
    permission_classes = [p.CompanyOfficeReadPermission]

    @action(detail=False, url_path="inventory", methods=["post"])
    def get_inventory(self, request):
        serializer = s.OfficeReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendors = m.Vendor.objects.all()
        serializer = self.serializer_class(
            self.queryset,
            context={
                "office": serializer.validated_data["office_id"],
                "vendors": vendors,
            },
            many=True,
        )
        return Response(serializer.data)


class ProductViewSet(AsyncMixin, ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = s.ProductSerializer
    filterset_class = f.ProductFilter
    queryset = m.Product.objects.all()

    @action(detail=False, methods=["get"], url_path="suggestion")
    def product_suggestion(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())[:5]
        serializer = s.ProductSuggestionSerializer(queryset, many=True)
        return Response(serializer.data)


def get_office_vendor(office_pk, vendor_pk):
    try:
        return OfficeVendor.objects.get(office_id=office_pk, vendor_id=vendor_pk)
    except OfficeVendor.DoesNotExist:
        return


def get_cart(office_pk):
    cart_products = (
        m.Cart.objects.filter(office_id=office_pk, save_for_later=False)
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


class CartViewSet(AsyncMixin, ModelViewSet):
    permission_classes = [IsAuthenticated]
    model = m.Cart
    serializer_class = s.CartSerializer
    queryset = m.Cart.objects.all()

    def get_queryset(self):
        return self.queryset.filter(office_id=self.kwargs["office_pk"]).order_by(
            "product__vendor", "-updated_at", "-save_for_later"
        )

    async def update_vendor_cart(self, product_id, vendor, serializer=None):
        office_vendor = await sync_to_async(get_office_vendor)(office_pk=self.kwargs["office_pk"], vendor_pk=vendor.id)
        if office_vendor is None:
            raise VendorNotConnected()
        session = apps.get_app_config("accounts").session
        scraper = ScraperFactory.create_scraper(
            vendor=vendor,
            session=session,
            username=office_vendor.username,
            password=office_vendor.password,
        )
        try:
            await scraper.remove_product_from_cart(product_id=product_id, use_bulk=False, perform_login=True)
        except Exception as e:
            raise VendorSiteError(f"{e}")

        if not serializer:
            return True

        updated_save_for_later = serializer.instance and "save_for_later" in serializer.validated_data

        if updated_save_for_later and serializer.validated_data["save_for_later"]:
            return True

        if updated_save_for_later and not serializer.validated_data["save_for_later"]:
            quantity = serializer.instance.quantity
        else:
            quantity = serializer.validated_data["quantity"]

        try:
            vendor_cart_product = await scraper.add_product_to_cart(
                CartProduct(product_id=product_id, product_unit=serializer, quantity=quantity),
                perform_login=True,
            )
            serializer.validated_data["unit_price"] = vendor_cart_product["unit_price"]
        except Exception as e:
            raise VendorSiteError(f"{e}")

    async def create(self, request, *args, **kwargs):
        data = request.data
        office_pk = self.kwargs["office_pk"]
        data["office"] = office_pk
        can_use_cart, _ = await sync_to_async(get_cart_status_and_order_status)(office=office_pk, user=request.user)
        if not can_use_cart:
            return Response({"message": msgs.CHECKOUT_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=data)
        await sync_to_async(serializer.is_valid)(raise_exception=True)
        product_id = serializer.validated_data["office_product"]["product"]["product_id"]
        product_url = serializer.validated_data["office_product"]["product"]["url"]
        vendor = serializer.validated_data["office_product"]["product"]["vendor"]
        product_category = serializer.validated_data["office_product"]["product"]["category"]
        #     try:
        #         await self.update_vendor_cart(
        #             product_id,
        #             vendor,
        #             serializer,
        #         )
        if not product_category:
            update_product_detail.delay(product_id, product_url, office_pk, vendor.id)
            # except VendorSiteError as e:
            #     return Response(
            #         {
            #             "message": f"{msgs.VENDOR_SITE_ERROR} - {e}"
            #         },
            #         status=HTTP_500_INTERNAL_SERVER_ERROR
            #     )
            # except VendorNotConnected:
            #     return Response({"message": "Vendor not connected"}, status=HTTP_400_BAD_REQUEST)
        serializer_data = await sync_to_async(save_serailizer)(serializer)
        return Response(serializer_data, status=HTTP_201_CREATED)

    #
    # @sync_to_async
    # def get_object_with_related(self):
    #     instance = self.get_object()
    #     return instance, instance.product.product_id, instance.product.vendor
    #
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
    def _create_order(self, office_vendors, vendor_order_results, cart_products, data):
        order_date = timezone.now().date()
        inventory_products_ids = []
        with transaction.atomic():
            order = m.Order.objects.create(
                office_id=self.kwargs["office_pk"],
                created_by=self.request.user,
                order_date=order_date,
                status="PENDING",
            )
            total_amount = 0
            total_items = 0

            for office_vendor, vendor_order_result in zip(office_vendors, vendor_order_results):
                if not isinstance(vendor_order_result, dict):
                    continue

                vendor = office_vendor.vendor
                vendor_order_id = vendor_order_result.get("order_id", "")
                vendor_total_amount = vendor_order_result.get("total_amount", 0)
                total_amount += vendor_total_amount
                vendor_order_products = cart_products.filter(product__vendor=vendor)
                total_items += (vendor_total_items := vendor_order_products.count())
                vendor_order = m.VendorOrder.objects.create(
                    order=order,
                    vendor=office_vendor.vendor,
                    vendor_order_id=vendor_order_id,
                    total_amount=vendor_total_amount,
                    total_items=vendor_total_items,
                    currency="USD",
                    order_date=order_date,
                    status="PENDING",
                )
                objs = []
                for vendor_order_product in vendor_order_products:
                    inventory_products_ids.append(vendor_order_product.product.id)
                    objs.append(
                        m.VendorOrderProduct(
                            vendor_order=vendor_order,
                            product=vendor_order_product.product,
                            quantity=vendor_order_product.quantity,
                            unit_price=vendor_order_product.unit_price,
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

        cart_products.delete()
        notify_order_creation.delay(order.id, inventory_products_ids)
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
            session = apps.get_app_config("accounts").session
            tasks = []
            for office_vendor in office_vendors:
                scraper = ScraperFactory.create_scraper(
                    vendor=office_vendor.vendor,
                    session=session,
                    username=office_vendor.username,
                    password=office_vendor.password,
                )
                tasks.append(
                    scraper.create_order(
                        [
                            CartProduct(
                                product_id=cart_product.product.product_id,
                                product_unit=cart_product.product.product_unit,
                                quantity=cart_product.quantity,
                            )
                            for cart_product in cart_products
                            if cart_product.product.vendor.id == office_vendor.vendor.id
                        ]
                    )
                )
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                ret.update(result)
        except Exception as e:
            return Response({"message": f"{e}"}, status=HTTP_400_BAD_REQUEST)

        products = await sync_to_async(get_serializer_data)(s.CartSerializer, cart_products, many=True)
        return Response({"products": products, "order_details": ret})

    @action(detail=False, url_path="confirm-order", methods=["post"], permission_classes=[p.OrderCheckoutPermission])
    async def confirm_order(self, request, *args, **kwargs):
        data = request.data["data"]
        cart_products, office_vendors = await sync_to_async(get_cart)(office_pk=self.kwargs["office_pk"])

        if not cart_products:
            return Response({"can_checkout": False, "message": msgs.EMPTY_CART}, status=HTTP_400_BAD_REQUEST)

        session = apps.get_app_config("accounts").session
        tasks = []
        for office_vendor in office_vendors:
            # vendor_slug = vendor_data["slug"]
            scraper = ScraperFactory.create_scraper(
                vendor=office_vendor.vendor,
                session=session,
                username=office_vendor.username,
                password=office_vendor.password,
            )

            tasks.append(
                scraper.confirm_order(
                    [
                        CartProduct(
                            product_id=cart_product.product.product_id,
                            product_unit=cart_product.product.product_unit,
                            quantity=cart_product.quantity,
                        )
                        for cart_product in cart_products
                        if cart_product.product.vendor.id == office_vendor.vendor.id
                    ],
                    fake=True,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        order_data = await self._create_order(office_vendors, results, cart_products, data)
        return Response(order_data)

    @action(detail=False, url_path="add-multiple-products", methods=["post"])
    async def add_multiple_products(self, request, *args, **kwargs):
        products = request.data
        office_pk = self.kwargs["office_pk"]
        can_use_cart, _ = await sync_to_async(get_cart_status_and_order_status)(office=office_pk, user=request.user)
        if not can_use_cart:
            return Response({"message": msgs.CHECKOUT_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)
        if not isinstance(products, list):
            return Response({"message": msgs.PAYLOAD_ISSUE}, status=HTTP_400_BAD_REQUEST)
        result = []
        for product in products:
            product["office"] = office_pk
            serializer = self.get_serializer(data=product)
            await sync_to_async(serializer.is_valid)(raise_exception=True)
            product_id = serializer.validated_data["office_product"]["product"]["product_id"]
            product_url = serializer.validated_data["office_product"]["product"]["url"]
            vendor = serializer.validated_data["office_product"]["product"]["vendor"]
            product_category = serializer.validated_data["office_product"]["product"]["category"]
            #     try:
            #         await self.update_vendor_cart(
            #             product_id,
            #             vendor,
            #             serializer,
            #         )
            if not product_category:
                update_product_detail.delay(product_id, product_url, office_pk, vendor.id)
                # except VendorSiteError as e:
                #     return Response(
                #         {"message": f"{msgs.VENDOR_SITE_ERROR} - {e}"},
                #         status=HTTP_500_INTERNAL_SERVER_ERROR
                #     )
                # except VendorNotConnected:
                #     return Response({"message": "Vendor not connected"}, status=HTTP_400_BAD_REQUEST)
            serializer_data = await sync_to_async(save_serailizer)(serializer)
            result.append(serializer_data)
        return Response(result, status=HTTP_201_CREATED)


class CheckoutAvailabilityAPIView(APIView):
    permission_classes = [p.OrderCheckoutPermission]

    def get(self, request, *args, **kwargs):
        cart_products, office_vendors = get_cart(office_pk=kwargs.get("office_pk"))
        if not cart_products:
            return Response({"message": msgs.EMPTY_CART}, status=HTTP_400_BAD_REQUEST)

        can_use_cart, _ = get_cart_status_and_order_status(office=office_vendors[0].office, user=request.user)
        return Response({"can_use_cart": can_use_cart})


class CheckoutUpdateStatusAPIView(APIView):
    permission_classes = [p.OrderCheckoutPermission]

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


class OfficeProductViewSet(ModelViewSet):
    queryset = m.OfficeProduct.objects.all()
    serializer_class = s.OfficeProductSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticated]
    filterset_class = f.OfficeProductFilter

    def get_serializer_context(self):
        ret = super().get_serializer_context()
        ret["include_children"] = True
        ret["filter_inventory"] = self.request.query_params.get("inventory", False)
        return ret

    def get_queryset(self):
        category_ordering = self.request.query_params.get("category_ordering")
        return (
            super()
            .get_queryset()
            .filter(Q(office__id=self.kwargs["office_pk"]), Q(product__parent__isnull=True))
            .annotate(
                category_order=Case(When(office_category__slug=category_ordering, then=Value(0)), default=Value(1))
            )
            .order_by("category_order", "office_category__slug")
        )

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)


class SearchProductAPIView(AsyncMixin, APIView, SearchProductPagination):
    # queryset = m.OfficeProduct.objects.all()
    # serializer_class = s.OfficeProductSerializer
    # pagination_class = SearchProductPagination
    # permission_classes = [IsAuthenticated]

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
            & (Q(product__name__icontains=keyword) | Q(product__tags__keyword__iexact=keyword))
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
        return queryset

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
        vendors_slugs = [vendor_meta["vendor"] for vendor_meta in pagination_meta.get("vendors", [])]
        for office_vendor in office_vendors:
            if (
                office_vendor.vendor.slug == "ultradent"
                or vendors_slugs
                and office_vendor.vendor.slug not in vendors_slugs
            ):
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
            return False
        if vendors_to_be_waited:
            return True
        return True

    @sync_to_async
    def get_products_from_db(self):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset, self.request, view=self)
        serializer = s.OfficeProductSerializer(page, many=True, context={"include_children": True})
        return self.get_paginated_response(serializer.data)

    async def fetch_products(self, keyword, min_price, max_price):
        pagination_meta = self.request.data.get("meta", {})
        vendors_meta = {vendor_meta["vendor"]: vendor_meta for vendor_meta in pagination_meta.get("vendors", [])}
        session = apps.get_app_config("accounts").session
        office_vendors = await sync_to_async(self.get_linked_vendors)()
        tasks = []
        for office_vendor in office_vendors:
            vendor_slug = office_vendor.vendor.slug
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

        return await asyncio.gather(*tasks, return_exceptions=True)

    async def post(self, request, *args, **kwargs):
        data = request.data
        keyword = data.get("q")
        pagination_meta = data.get("meta", {})

        if pagination_meta.get("last_page", False):
            return Response({"message": msgs.NO_SEARCH_PRODUCT_RESULT}, status=HTTP_400_BAD_REQUEST)

        if len(keyword) <= 3:
            return Response({"message": msgs.SEARCH_QUERY_LIMIT}, status=HTTP_400_BAD_REQUEST)

        has_history = await sync_to_async(self.has_keyword_history)(keyword)
        if has_history:
            return await self.get_products_from_db()

        try:
            min_price = data.get("min_price", 0)
            max_price = data.get("max_price", 0)
            min_price = int(min_price)
            max_price = int(max_price)
        except ValueError:
            return Response({"message": msgs.SEARCH_PRODUCT_WRONG_PARAMETER}, status=HTTP_400_BAD_REQUEST)

        search_results = await self.fetch_products(keyword, min_price, max_price)
        meta, products = group_products_from_search_result(search_results)

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

        return Response({"meta": meta, "products": results})
