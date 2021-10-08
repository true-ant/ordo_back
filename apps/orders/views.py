import asyncio
import decimal
import operator
from datetime import datetime, timedelta
from decimal import Decimal
from functools import reduce

from asgiref.sync import sync_to_async
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models import Case, Count, F, Q, Sum, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
)
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.models import Company, CompanyMember, Office, OfficeVendor
from apps.common import messages as msgs
from apps.common.asyncdrf import AsyncMixin
from apps.common.pagination import StandardResultsSetPagination
from apps.scrapers.errors import VendorNotSupported
from apps.scrapers.scraper_factory import ScraperFactory
from apps.types.orders import CartProduct

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
                    "logo": f"https://{settings.AWS_S3_CUSTOM_DOMAIN}"
                    f"{settings.PUBLIC_MEDIA_LOCATION}{vendor['vendor_logo']}",
                    "order_counts": vendor["order_counts"],
                    "total_amount": vendor["order_total_amount"],
                }
                for vendor in vendors
            ],
        }
        return Response(ret)


class VendorOrderProductViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = m.VendorOrderProduct.objects.all()
    serializer_class = s.VendorOrderProductSerializer
    filterset_class = f.VendorOrderProductFilter
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        category_ordering = self.request.query_params.get("category_ordering")
        queryset = (
            super()
            .get_queryset()
            .filter(Q(vendor_order__order__office__id=self.kwargs["office_pk"]) & Q(is_deleted=False))
            .order_by("product__category__slug")
        )
        if category_ordering:
            queryset = queryset.annotate(
                category_order=Case(When(product__category__slug=category_ordering, then=Value(0)), default=Value(1))
            ).order_by("category_order", "product__category__slug")
        return queryset

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_deleted = True
        instance.save()
        return Response(status=HTTP_204_NO_CONTENT)


class CompanyOrderAPIView(APIView, StandardResultsSetPagination):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_pk):
        queryset = m.Order.objects.filter(office__company__id=company_pk)
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
                    "logo": f"https://{settings.AWS_S3_CUSTOM_DOMAIN}"
                    f"{settings.PUBLIC_MEDIA_LOCATION}{vendors[q['vendor_id']].vendor.logo}",
                    "office_associated_id": vendors[q["vendor_id"]].id,
                },
                "total_amount": q["total_amount"],
            }
            for q in qs
        ]


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
    queryset = m.Product.objects.all()

    @sync_to_async
    def _get_linked_vendors(self, request, office_id, vendor_id=None):
        CompanyMember.objects.filter(user=request.user).first()
        # TODO: Check permission
        # office_vendors = OfficeVendor.objects.select_related("vendor").filter(office__company=company_member.company)
        office_vendors = OfficeVendor.objects.select_related("vendor").filter(office_id=office_id)
        if vendor_id:
            office_vendors = office_vendors.filter(vendor_id=vendor_id)
        return list(office_vendors)

    @action(detail=False, methods=["post"], url_path="search")
    async def search_product(self, request, *args, **kwargs):
        data = request.data
        office_id = data.get("office_id", "")
        q = data.get("q", "")
        pagination_meta = data.get("meta", {})
        min_price = data.get("min_price", 0)
        max_price = data.get("max_price", 0)

        if not office_id:
            return Response({"message": msgs.OFFICE_ID_MISSING}, status=HTTP_400_BAD_REQUEST)

        if pagination_meta.get("last_page", False):
            return Response({"message": msgs.NO_SEARCH_PRODUCT_RESULT}, status=HTTP_400_BAD_REQUEST)

        if len(q) <= 3:
            return Response({"message": msgs.SEARCH_QUERY_LIMIT}, status=HTTP_400_BAD_REQUEST)
        try:
            min_price = int(min_price)
            max_price = int(max_price)
        except ValueError:
            return Response({"message": msgs.SEARCH_PRODUCT_WRONG_PARAMETER}, status=HTTP_400_BAD_REQUEST)

        vendors_meta = {vendor_meta["vendor"]: vendor_meta for vendor_meta in pagination_meta.get("vendors", [])}
        session = apps.get_app_config("accounts").session
        office_vendors = await self._get_linked_vendors(request, office_id)
        tasks = []
        for office_vendor in office_vendors:
            vendor_slug = office_vendor.vendor.slug
            if vendors_meta.keys() and vendor_slug not in vendors_meta.keys():
                continue

            if vendors_meta.get(vendor_slug, {}).get("last_page", False):
                continue
            try:
                scraper = ScraperFactory.create_scraper(
                    vendor=office_vendor.vendor.to_dict(),
                    session=session,
                    username=office_vendor.username,
                    password=office_vendor.password,
                )
            except VendorNotSupported:
                continue
            current_page = vendors_meta.get(vendor_slug, {}).get("page", 0)
            tasks.append(
                scraper.search_products(query=q, page=current_page + 1, min_price=min_price, max_price=max_price)
            )

        search_results = await asyncio.gather(*tasks, return_exceptions=True)

        # filter
        products = []
        meta = {
            "total_size": 0,
            "vendors": [],
        }
        for search_result in search_results:
            if not isinstance(search_result, dict):
                continue
            meta["total_size"] += search_result["total_size"]
            meta["vendors"].append(
                {
                    "vendor": search_result["vendor_slug"],
                    "page": search_result["page"],
                    "last_page": search_result["last_page"],
                }
            )
            products.extend([product.to_dict() for product in search_result["products"]])

        meta["last_page"] = all([vendor_search["last_page"] for vendor_search in meta["vendors"]])

        return Response({"meta": meta, "products": products})

    @sync_to_async
    def _validate_product_detail_serializer(self, request):
        serializer = s.ProductReadDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    @action(detail=False, methods=["post"], url_path="detail")
    async def get_product_detail_from_vendor(self, request, *args, **kwargs):
        validated_data = await self._validate_product_detail_serializer(request)
        office_vendor = await self._get_linked_vendors(
            request, validated_data["office_id"].id, validated_data["vendor"].id
        )
        office_vendor = office_vendor[0]
        session = apps.get_app_config("accounts").session
        scraper = ScraperFactory.create_scraper(
            vendor=validated_data["vendor"].to_dict(),
            session=session,
            username=office_vendor.username,
            password=office_vendor.password,
        )

        product = await scraper.get_product(
            product_id=validated_data["product_id"], product_url=validated_data["product_url"], perform_login=True
        )
        return Response(product.to_dict())


def get_office_vendor(office_pk, vendor_pk):
    try:
        return m.OfficeVendor.objects.get(office_id=office_pk, vendor_id=vendor_pk)
    except m.OfficeVendor.DoesNotExist:
        pass


def get_cart(office_pk):
    cart_products = (
        m.Cart.objects.filter(office_id=office_pk, save_for_later=False)
        .order_by("-updated_at")
        .select_related("office", "product__vendor")
    )
    office = cart_products[0].office if cart_products else None
    vendors = [cart_product.product.vendor for cart_product in cart_products]
    return cart_products, office, vendors


def get_checkout_status(office, vendors):
    q = reduce(
        operator.or_,
        [Q(office=office) & Q(vendor=vendor) for vendor in vendors],
    )
    office_vendors = OfficeVendor.objects.filter(q).select_related("vendor")

    queryset = m.OrderProgressStatus.objects.filter(
        checkout_status=m.OrderProgressStatus.CHECKOUT_STATUS.IN_PROGRESS,
        office_vendor__in=office_vendors,
    ).select_related("updated_by")
    if queryset:
        is_checking = True
        updated_bys = [q.updated_by for q in queryset]
    else:
        is_checking = False
        updated_bys = []

    return list(office_vendors), is_checking, updated_bys


def update_checkout_status(office_vendors, user, checkout_status, order_status=None):
    defaults = {
        "checkout_status": checkout_status,
        "updated_by": user,
    }
    if order_status:
        defaults["order_status"] = order_status
    with transaction.atomic():
        for office_vendor in office_vendors:
            m.OrderProgressStatus.objects.update_or_create(
                office_vendor=office_vendor,
                defaults=defaults,
            )


def save_serailizer(serializer):
    serializer.save()
    return serializer.data


class CartViewSet(AsyncMixin, ModelViewSet):
    permission_classes = [IsAuthenticated]
    model = m.Cart
    serializer_class = s.CartSerializer
    queryset = m.Cart.objects.all()

    def get_queryset(self):
        return self.queryset.filter(office_id=self.kwargs["office_pk"]).order_by("-updated_at", "save_for_later")

    async def update_vendor_cart(self, product_id, vendor, serializer=None):
        office_vendor = await sync_to_async(get_office_vendor)(office_pk=self.kwargs["office_pk"], vendor_pk=vendor.id)
        session = apps.get_app_config("accounts").session
        scraper = ScraperFactory.create_scraper(
            vendor=vendor.to_dict(),
            session=session,
            username=office_vendor.username,
            password=office_vendor.password,
        )
        await scraper.login()
        await scraper.remove_product_from_cart(product_id=product_id, use_bulk=False)
        if serializer:
            vendor_product_detail = await scraper.add_product_to_cart(
                CartProduct(product_id=product_id, quantity=serializer.validated_data["quantity"])
            )
            serializer.validated_data["unit_price"] = vendor_product_detail["price"]

    async def create(self, request, *args, **kwargs):
        data = request.data
        data["office"] = self.kwargs["office_pk"]
        serializer = self.get_serializer(data=data)
        await sync_to_async(serializer.is_valid)(raise_exception=True)
        product_id = serializer.validated_data["product"]["product_id"]
        vendor = serializer.validated_data["product"]["vendor"]
        await self.update_vendor_cart(
            product_id,
            vendor,
            serializer,
        )
        serializer_data = await sync_to_async(save_serailizer)(serializer)
        return Response(serializer_data, status=HTTP_201_CREATED)

    @sync_to_async
    def get_object_with_related(self):
        instance = self.get_object()
        return instance, instance.product.product_id, instance.product.vendor

    async def update(self, request, *args, **kwargs):
        instance, product_id, vendor = await self.get_object_with_related()
        serializer = self.get_serializer(instance, request.data, partial=True)
        await sync_to_async(serializer.is_valid)(raise_exception=True)
        await self.update_vendor_cart(product_id, vendor, serializer)
        serializer_data = await sync_to_async(save_serailizer)(serializer)
        return Response(serializer_data)

    async def destroy(self, request, *args, **kwargs):
        instance, product_id, vendor = await self.get_object_with_related()
        await self.update_vendor_cart(product_id, vendor)
        await sync_to_async(self.perform_destroy)(instance)
        return Response(status=HTTP_204_NO_CONTENT)

    @sync_to_async
    def _create_order(self, office_vendors):
        with transaction.atomic():
            m.Order.objects.create(office_id=self.kwargs["office_pk"], created_by=self.request.user, status="PENDING")
            # for office_vendor in office_vendors:
            #     m.VendorOrder.objects.create(
            #         order=order,
            #         vendor=vendor,
            #         vendor_order_id="vendor",
            #         total_amount=1,
            #         total_items=1,
            #         currency="USD",
            #         order_date=timezone.now()
            #         status="PENDING"
            #     )

    @action(detail=False, url_path="checkout", methods=["get"], permission_classes=[p.OrderCheckoutPermission])
    async def checkout(self, request, *args, **kwargs):
        cart_products, office, vendors = await sync_to_async(get_cart)(office_pk=self.kwargs["office_pk"])
        if not cart_products:
            return Response({"can_checkout": False, "message": msgs.EMPTY_CART}, status=HTTP_400_BAD_REQUEST)

        office_vendors, is_checking, updated_bys = await sync_to_async(get_checkout_status)(
            office=office, vendors=vendors
        )
        if is_checking:
            return Response({"message": msgs.ORDER_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)

        await sync_to_async(update_checkout_status)(
            office_vendors=office_vendors,
            user=request.user,
            checkout_status=m.OrderProgressStatus.CHECKOUT_STATUS.IN_PROGRESS,
        )
        try:
            session = apps.get_app_config("accounts").session
            tasks = []
            for office_vendor in office_vendors:
                scraper = ScraperFactory.create_scraper(
                    vendor=office_vendor.vendor.to_dict(),
                    session=session,
                    username=office_vendor.username,
                    password=office_vendor.password,
                )
                tasks.append(
                    scraper.create_order(
                        [
                            CartProduct(product_id=cart_product.product.product_id, quantity=cart_product.quantity)
                            for cart_product in cart_products
                            if cart_product.product.vendor.id == office_vendor.vendor.id
                        ]
                    )
                )
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            return Response({"message": f"{e}"}, status=HTTP_400_BAD_REQUEST)

        return Response(results)

    @action(detail=False, url_path="confirm-order", methods=["post"], permission_classes=[p.OrderCheckoutPermission])
    async def confirm_order(self, request, *args, **kwargs):
        return Response({})
        # cart_products, office, vendors = await sync_to_async(get_cart)(
        #     office_pk=self.kwargs["office_pk"], user=self.request.user
        # )
        #
        # if not cart_products:
        #     return Response({"can_checkout": False, "message": msgs.EMPTY_CART}, status=HTTP_400_BAD_REQUEST)
        #
        # office_vendors, is_checking, updated_bys = await sync_to_async(get_checkout_status)(
        #     office=office, vendors=vendors
        # )
        # if is_checking:
        #     return Response({"message": msgs.ORDER_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)
        #
        # await sync_to_async(update_checkout_status)(
        #     office_vendors=office_vendors,
        #     user=request.user,
        #     checkout_status=m.OrderProgressStatus.CHECKOUT_STATUS.IN_PROGRESS,
        # )


class CheckoutAvailabilityAPIView(APIView):
    permission_classes = [p.OrderCheckoutPermission]

    def get(self, request, *args, **kwargs):
        cart_products, office, vendors = get_cart(office_pk=kwargs.get("office_pk"))
        if not cart_products:
            return Response({"can_checkout": False, "message": msgs.EMPTY_CART}, status=HTTP_400_BAD_REQUEST)

        _, is_checking, _ = get_checkout_status(
            office=office,
            vendors=vendors,
        )
        return Response({"can_checkout": not is_checking})


class CheckoutCompleteAPIView(APIView):
    permission_classes = [p.OrderCheckoutPermission]

    def get(self, request, *args, **kwargs):
        cart_products, office, vendors = get_cart(office_pk=kwargs.get("office_pk"))
        if not cart_products:
            return Response({"message": msgs.EMPTY_CART}, status=HTTP_400_BAD_REQUEST)

        office_vendors, is_checking, updated_bys = get_checkout_status(office=office, vendors=vendors)
        if not is_checking:
            return Response({"message": msgs.CHECKOUT_COMPLETE})

        if len(updated_bys) > 1 or updated_bys[0] != request.user:
            return Response({"message": msgs.UNKNOWN_ISSUE}, status=HTTP_400_BAD_REQUEST)

        update_checkout_status(
            office_vendors=office_vendors,
            user=request.user,
            checkout_status=m.OrderProgressStatus.CHECKOUT_STATUS.COMPLETE,
        )
        return Response({"message": "Status updated successfully"})
