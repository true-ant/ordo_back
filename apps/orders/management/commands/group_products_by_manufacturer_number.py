import datetime

from django.core.management import BaseCommand

from apps.orders.helpers import ProductHelper


class Command(BaseCommand):
    help = "Group products"

    def add_arguments(self, parser):
        """
        python manage.py group_products_by_manufacturer_number --since 2022-04-12T11:50:29.751119+00:00
        """
        parser.add_argument(
            "--since",
            help="iso format of time",
        )

    def handle(self, *args, **options):
        since = datetime.datetime.fromisoformat(options["since"]) if options["since"] else None
        ProductHelper.group_products_by_manufacturer_numbers(since)
