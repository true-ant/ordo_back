from asgiref.sync import sync_to_async
from django.apps import apps
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import OfficeVendor
from apps.common.choices import ProductStatus
from apps.orders.models import OrderStatus, VendorOrder, VendorOrderProduct
from apps.orders.tasks import notify_order_creation
from apps.scrapers.scraper_factory import ScraperFactory
from apps.types.orders import CartProduct
from config.utils import get_client_session


class OrderService:
    @staticmethod
    def is_debug_mode(stage):
        return "localhost" in stage or "127.0.0.1" in stage
        # return settings.MAKE_FAKE_ORDER

    @staticmethod
    def is_force_redundancy():
        return True
    @sync_to_async
    def get_office_vendor(self, vendor_order) -> OfficeVendor:
        return (
            OfficeVendor.objects.select_related("vendor")
            .filter(office=vendor_order.order.office, vendor=vendor_order.vendor)
            .first()
        )

    @sync_to_async
    def get_vendor_order_products(self, vendor_order, validated_data):
        rejected_items = validated_data.get("rejected_items", [])
        rejected_items = {
            str(rejected_item["order_product_id"]): rejected_item["rejected_reason"]
            for rejected_item in rejected_items
        }
        vendor_order_products = VendorOrderProduct.objects.select_related("product").filter(vendor_order=vendor_order)

        rejected_vendor_order_products = []
        approved_vendor_order_products = []
        for vendor_order_product in vendor_order_products:
            if str(vendor_order_product.id) in rejected_items:
                vendor_order_product.rejected_reason = rejected_items[str(vendor_order_product.id)]
                vendor_order_product.status = ProductStatus.REJECTED
                rejected_vendor_order_products.append(vendor_order_product)
            else:
                approved_vendor_order_products.append(vendor_order_product)

        if rejected_vendor_order_products:
            VendorOrderProduct.objects.bulk_update(
                rejected_vendor_order_products, fields=["rejected_reason", "status"]
            )

        return approved_vendor_order_products

    @staticmethod
    async def approve_vendor_order(approved_by, vendor_order: VendorOrder, validated_data, stage: str):
        session = await get_client_session()

        products = await OrderService.get_vendor_order_products(vendor_order, validated_data)

        if products:
            office_vendor = await OrderService.get_office_vendor(vendor_order=vendor_order)

            scraper = ScraperFactory.create_scraper(
                vendor=office_vendor.vendor,
                session=session,
                username=office_vendor.username,
                password=office_vendor.password,
            )
            vendor_order_result = await scraper.confirm_order(
                [
                    CartProduct(
                        product_id=product.product.product_id,
                        product_unit=product.product.product_unit,
                        quantity=product.quantity,
                    )
                    for product in products
                ],
                fake=OrderService.is_debug_mode(stage=stage),
            )

            vendor_order.vendor_order_id = vendor_order_result["order_id"]
            vendor_order.status = OrderStatus.OPEN
        else:
            vendor_order.status = OrderStatus.CLOSED

        vendor_order.approved_at = timezone.now()
        vendor_order.approved_by = approved_by
        await sync_to_async(vendor_order.save)()

        if products:
            # TODO: this logics should be refactored
            notify_order_creation.delay([vendor_order.id], approval_needed=False)

    @staticmethod
    def reject_vendor_order(approved_by, vendor_order: VendorOrder, validated_data):
        with transaction.atomic():
            vendor_order.status = OrderStatus.CLOSED
            vendor_order.approved_at = timezone.now()
            vendor_order.approved_by = approved_by
            vendor_order.rejected_reason = validated_data["rejected_reason"]
            vendor_order.save()

            vendor_order_products = vendor_order.order_products.all()
            for vendor_order_product in vendor_order_products:
                vendor_order_product.status = ProductStatus.REJECTED
                vendor_order_product.rejected_reason = VendorOrderProduct.RejectReason.NOT_NEEDED

            VendorOrderProduct.objects.bulk_update(vendor_order_products, ["rejected_reason", "status"])
