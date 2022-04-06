from django.core.management import BaseCommand

from apps.orders.helpers import ProductHelper


class Command(BaseCommand):
    help = "Group products"

    def handle(self, *args, **options):
        ProductHelper.group_products_by_manufacturer_numbers()
