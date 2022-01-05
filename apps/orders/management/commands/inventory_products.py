from django.core.management import BaseCommand

from apps.orders.models import OfficeProduct, VendorOrderProduct


class Command(BaseCommand):
    help = "Fetch Ultradent products and store them into a table"

    def handle(self, *args, **options):
        product_ids = VendorOrderProduct.objects.values_list("vendor_order__order__office", "product")
        for office_id, product_id in product_ids:
            obj, created = OfficeProduct.objects.update_or_create(
                office_id=office_id,
                product_id=product_id,
                defaults={
                    "is_inventory": True,
                },
            )
            print(f"{obj} is {'created' if created else 'updated'}")
