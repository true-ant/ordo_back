from django.core.management import BaseCommand

from apps.common.utils import bulk_update
from apps.orders.models import OfficeProduct, VendorOrderProduct


class Command(BaseCommand):
    def handle(self, *args, **options):
        # TODO: distinct
        office_products = OfficeProduct.objects.filter(
            product__vendor__isnull=False, is_inventory=True, last_order_date__isnull=True
        )
        for office_product in office_products:
            vendor_order_products = (
                VendorOrderProduct.objects.select_related(
                    "vendor_order",
                )
                .filter(
                    product=office_product.product,
                    vendor_order__order__office=office_product.office,
                )
                .order_by("-vendor_order__order_date")
                .values("vendor_order__order_date")
            )
            if vendor_order_products:
                office_product.last_order_date = vendor_order_products[0]["vendor_order__order_date"]

        bulk_update(OfficeProduct, office_products, fields=["last_order_date"])
