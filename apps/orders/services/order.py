from asgiref.sync import sync_to_async
from django.apps import apps

from apps.accounts.models import OfficeVendor
from apps.orders.models import OrderStatus, VendorOrder, VendorOrderProduct
from apps.orders.tasks import notify_order_creation
from apps.scrapers.scraper_factory import ScraperFactory
from apps.types.orders import CartProduct


class OrderService:
    @staticmethod
    def is_debug_mode():
        return True

    @sync_to_async
    def get_office_vendor(self, vendor_order) -> OfficeVendor:
        return (
            OfficeVendor.objects.select_related("vendor")
            .filter(office=vendor_order.order.office, vendor=vendor_order.vendor)
            .first()
        )

    @sync_to_async
    def get_vendor_order_products(self, vendor_order):
        return list(VendorOrderProduct.objects.select_related("product").filter(vendor_order=vendor_order))

    @staticmethod
    async def approve_vendor_order(vendor_order: VendorOrder):
        session = apps.get_app_config("accounts").session

        office_vendor = await OrderService.get_office_vendor(vendor_order=vendor_order)

        scraper = ScraperFactory.create_scraper(
            vendor=office_vendor.vendor,
            session=session,
            username=office_vendor.username,
            password=office_vendor.password,
        )
        products = await OrderService.get_vendor_order_products(vendor_order)

        vendor_order_result = await scraper.confirm_order(
            [
                CartProduct(
                    product_id=product.product.product_id,
                    product_unit=product.product.product_unit,
                    quantity=product.quantity,
                )
                for product in products
            ],
            fake=OrderService.is_debug_mode(),
        )

        vendor_order.vendor_order_id = vendor_order_result["order_id"]
        vendor_order.status = OrderStatus.PROCESSING
        await sync_to_async(vendor_order.save)()
        notify_order_creation.delay([vendor_order.id], approval_needed=False)
