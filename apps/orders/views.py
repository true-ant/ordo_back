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
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_204_NO_CONTENT, HTTP_400_BAD_REQUEST
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
        return (
            super()
            .get_queryset()
            .filter(Q(vendor_order__order__office__id=self.kwargs["office_pk"]) & Q(is_deleted=False))
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_deleted = True
        instance.save()
        return Response(status=HTTP_204_NO_CONTENT)


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


class CartViewSet(AsyncMixin, ModelViewSet):
    permission_classes = [IsAuthenticated]
    model = m.Cart
    serializer_class = s.CartSerializer
    queryset = m.Cart.objects.all()

    def get_queryset(self):
        return self.queryset.filter(office_id=self.kwargs["office_pk"], user=self.request.user).order_by(
            "-updated_at", "save_for_later"
        )

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
        queryset = self.get_queryset().filter(save_for_later=False)
        office = Office.objects.get(id=self.kwargs["office_pk"])
        q = reduce(
            operator.or_,
            [Q(office=office) & Q(vendor=item.product.vendor) for item in queryset],
        )
        office_vendors = OfficeVendor.objects.select_related("vendor").filter(q)

        is_checking = m.OrderProgressStatus.objects.filter(
            status=m.OrderProgressStatus.STATUS.IN_PROGRESS, office_vendor__in=office_vendors
        ).exists()

        # total_price = sum(cart.quantity * cart.product.price for cart in queryset)
        return queryset, office, list(office_vendors), is_checking

    @sync_to_async
    def _update_vendors_order_status(self, office_vendors, status):
        for office_vendor in office_vendors:
            office_vendor_order_progress, created = m.OrderProgressStatus.objects.get_or_create(
                office_vendor=office_vendor, defaults={"status": status}
            )
            if not created:
                office_vendor_order_progress.status = status
                office_vendor_order_progress.save()

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
        cart_products, office, office_vendors, is_checking = await self._pre_checkout_hook()
        if is_checking:
            return Response({"message": msgs.ORDER_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST)

        await self._update_vendors_order_status(office_vendors, status=m.OrderProgressStatus.STATUS.IN_PROGRESS)
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
                    scraper.checkout(
                        [
                            CartProduct(product_id=cart_product.product.product_id, quantity=cart_product.quantity)
                            for cart_product in cart_products
                            if cart_product.product.vendor.id == office_vendor.vendor.id
                        ]
                    )
                )
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            print(e)
            return Response({"message": "Bad request"}, status=HTTP_400_BAD_REQUEST)
        else:
            await self._create_order(office_vendors)
        finally:
            await self._update_vendors_order_status(office_vendors, status=m.OrderProgressStatus.STATUS.COMPLETE)

        return Response({"message": "okay"})


def get_checkout_status(office, vendors):
    q = reduce(
        operator.or_,
        [Q(office=office) & Q(vendor=vendor) for vendor in vendors],
    )
    office_vendors = OfficeVendor.objects.filter(q)

    queryset = m.OrderProgressStatus.objects.filter(
        status=m.OrderProgressStatus.STATUS.IN_PROGRESS, office_vendor__in=office_vendors
    ).select_related("updated_by")
    if queryset:
        is_checking = True
        updated_bys = [q.updated_by for q in queryset]
    else:
        is_checking = False
        updated_bys = []

    return office_vendors, is_checking, updated_bys


class OrderProgressGetStatusAPIView(APIView):
    def post(self, request):
        serializer = s.OrderVendorStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _, is_checking, _ = get_checkout_status(
            office=serializer.validated_data["office"],
            vendors=serializer.validated_data["vendors"],
        )
        return Response({"can_checkout": not is_checking})


class OrderProgressUpdateStatusAPIView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = s.OrderVendorStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        office = serializer.validated_data["office"]
        vendors = serializer.validated_data["vendors"]
        status = serializer.validated_data["status"]
        office_vendors, is_checking, updated_bys = get_checkout_status(office=office, vendors=vendors)
        if not is_checking or (
            is_checking
            and status == m.OrderProgressStatus.STATUS.COMPLETE
            and (not updated_bys or updated_bys[0] == request.user)
        ):
            with transaction.atomic():
                for office_vendor in office_vendors:
                    m.OrderProgressStatus.objects.update_or_create(
                        office_vendor=office_vendor,
                        defaults={
                            "status": serializer.validated_data.get("status"),
                            "updated_by": request.user,
                        },
                    )
            return Response({"message": "Status updated successfully"})
        else:
            return Response(
                {"can_checkout": not is_checking, "message": msgs.ORDER_IN_PROGRESS}, status=HTTP_400_BAD_REQUEST
            )
