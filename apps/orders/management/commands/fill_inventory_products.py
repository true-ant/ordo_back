from django.core.management import BaseCommand

from apps.common.utils import bulk_update
from apps.orders.models import OfficeProduct, VendorOrderProduct


class Command(BaseCommand):
    def handle(self, *args, **options):
        # TODO: distinct
        vendor_order_products = VendorOrderProduct.objects.select_related(
            "vendor_order", "vendor_order__order", "product"
        )
        office_products = []
        for vendor_order_product in vendor_order_products:
            office = vendor_order_product.vendor_order.order.office
            product = vendor_order_product.product
            order_date = vendor_order_product.vendor_order.order_date
            office_product = OfficeProduct.objects.filter(office=office, product=product).first()
            if office_product:
                office_product.last_order_date = order_date
                office_products.append(office_product)
        bulk_update(OfficeProduct, office_products, fields=["last_order_date"])
