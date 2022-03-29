from django.core.management import BaseCommand

from apps.common.utils import bulk_update
from apps.orders.models import OfficeProduct, VendorOrderProduct


class Command(BaseCommand):
    def handle(self, *args, **options):
        office_products_to_be_updated = []
        office_products = OfficeProduct.objects.filter(product__vendor__isnull=False, is_inventory=True)
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
            if not vendor_order_products:
                continue
            last_order_date = vendor_order_products[0]["vendor_order__order_date"]
            if office_product.last_order_date is None or office_product.last_order_date < last_order_date:
                office_product.last_order_date = vendor_order_products[0]["vendor_order__order_date"]
                office_products_to_be_updated.append(office_product)

        bulk_update(OfficeProduct, office_products_to_be_updated, fields=["last_order_date"])
        print(f"{len(office_products_to_be_updated)} products updated")
