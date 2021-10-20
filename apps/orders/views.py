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
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, ListModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
)
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet

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
        return (
            super()
            .get_queryset()
            .filter(Q(vendor_order__order__office__id=self.kwargs["office_pk"]) & Q(is_deleted=False))
            .annotate(
                category_order=Case(When(product__category__slug=category_ordering, then=Value(0)), default=Value(1))
            )
            .order_by("category_order", "product__category__slug", "product__product_id")
            .distinct("category_order", "product__category__slug", "product__product_id")
        )

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
        return OfficeVendor.objects.get(office_id=office_pk, vendor_id=vendor_pk)
    except OfficeVendor.DoesNotExist:
        pass


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

        if not serializer:
            return True

        updated_save_for_later = serializer.instance and "save_for_later" in serializer.validated_data

        if updated_save_for_later and serializer.validated_data["save_for_later"]:
            return True

        if updated_save_for_later and not serializer.validated_data["save_for_later"]:
            quantity = serializer.instance.quantity
        else:
            quantity = serializer.validated_data["quantity"]

        vendor_cart_product = await scraper.add_product_to_cart(CartProduct(product_id=product_id, quantity=quantity))
        serializer.validated_data["unit_price"] = vendor_cart_product["unit_price"]

    async def create(self, request, *args, **kwargs):
        data = request.data
        office_pk = self.kwargs["office_pk"]
        data["office"] = office_pk
        can_use_cart, _ = await sync_to_async(get_cart_status_and_order_status)(office=office_pk, user=request.user)
        if not can_use_cart:
            return Response({"message": msgs.CHECKOUT_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)

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
        can_use_cart, _ = await sync_to_async(get_cart_status_and_order_status)(
            office=self.kwargs["office_pk"], user=request.user
        )
        if not can_use_cart:
            return Response({"message": msgs.CHECKOUT_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(instance, request.data, partial=True)
        await sync_to_async(serializer.is_valid)(raise_exception=True)
        await self.update_vendor_cart(product_id, vendor, serializer)
        serializer_data = await sync_to_async(save_serailizer)(serializer)
        return Response(serializer_data)

    async def destroy(self, request, *args, **kwargs):
        instance, product_id, vendor = await self.get_object_with_related()
        can_use_cart, _ = await sync_to_async(get_cart_status_and_order_status)(
            office=self.kwargs["office_pk"], user=request.user
        )
        if not can_use_cart:
            return Response({"message": msgs.CHECKOUT_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)

        await self.update_vendor_cart(product_id, vendor)
        await sync_to_async(self.perform_destroy)(instance)
        return Response(status=HTTP_204_NO_CONTENT)

    @sync_to_async
    def _create_order(self, office_vendors, vendor_order_results, cart_products, data):
        order_date = timezone.now().date()
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
                objs = [
                    m.VendorOrderProduct(
                        vendor_order=vendor_order,
                        product=vendor_order_product.product,
                        quantity=vendor_order_product.quantity,
                        unit_price=vendor_order_product.unit_price,
                    )
                    for vendor_order_product in vendor_order_products
                ]
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
            for result in results:
                ret.update(result)
        except Exception as e:
            return Response({"message": f"{e}"}, status=HTTP_400_BAD_REQUEST)

        products = get_serializer_data(s.CartSerializer, cart_products, many=True)
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
            vendor_data = office_vendor.vendor.to_dict()
            # vendor_slug = vendor_data["slug"]
            scraper = ScraperFactory.create_scraper(
                vendor=vendor_data,
                session=session,
                username=office_vendor.username,
                password=office_vendor.password,
            )

            tasks.append(
                scraper.confirm_order(
                    [
                        CartProduct(product_id=cart_product.product.product_id, quantity=cart_product.quantity)
                        for cart_product in cart_products
                        if cart_product.product.vendor.id == office_vendor.vendor.id
                    ]
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        order_data = await self._create_order(office_vendors, results, cart_products, data)
        return Response(order_data)


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


class FavouriteProductViewSet(CreateModelMixin, DestroyModelMixin, ListModelMixin, GenericViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    queryset = m.FavouriteProduct.objects.all()
    serializer_class = s.FavouriteProductSerializer
