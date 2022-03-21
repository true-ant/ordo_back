import glob

from django.core.management import BaseCommand

from apps.common.utils import get_file_name_and_ext
from apps.orders.helpers import ProductHelper


class Command(BaseCommand):
    """
    python manage.py import_products
    """

    help = "Import products from csv files to table"

    def add_arguments(self, parser):
        parser.add_argument(
            "--directory",
            type=str,
            help="The path to directory contains product csv files",
            default="products",
        )
        parser.add_argument(
            "--vendors",
            type=str,
            help="import products from vendors",
        )
        parser.add_argument("--verbose", type=bool, help="debug mode", default=False)

    def load_products(self, directory, vendors, verbose=False):
        for file_name in sorted(glob.glob(f"{directory}/*.csv")):
            print(f"Read product data from {file_name}")
            vendor, _ = get_file_name_and_ext(file_name)
            if vendors and vendor not in vendors:
                continue
            ProductHelper.import_products_from_csv(file_path=file_name, vendor_slug=vendor, verbose=verbose)

    def handle(self, *args, **options):
        vendors = options["vendors"]
        if vendors:
            vendors = vendors.split(",")
        else:
            vendors = []
        self.load_products(options["directory"], vendors, options["verbose"])
