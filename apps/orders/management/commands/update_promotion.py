import glob
import csv
import os
import json
from django.core.management import BaseCommand

from apps.common.utils import get_file_name_and_ext
from apps.orders.helpers import ProductHelper


class Command(BaseCommand):
    """
    python manage.py update_promotion
    """

    help = "Update promotions for all vendors"
    dir_name = "./promotions"
    

    def add_arguments(self, parser):
        parser.add_argument("--verbose", type=bool, help="debug mode", default=False)

    def remove_csv_files(self):
        test = os.listdir(self.dir_name)
        for item in test:
            if item.endswith(".csv") or item.endswith(".json"):
                os.remove(os.path.join(self.dir_name, item))

    def create_csv_results(self):
        test = os.listdir(self.dir_name)

        # Run promotion scripts
        for item in test:
            if item.endswith(".py"):
                os.system(f"python {os.path.join(self.dir_name, item)}")

        # Convert json files into csv files
        for item in test:
            if item.endswith(".json"):
                with open(
                    os.path.join(self.dir_name, item), "r", encoding="utf-8-sig"
                ) as f:
                    data = json.load(f)

                with open(os.path.join(self.dir_name, item.replace(".json", ".csv")), "w") as f:
                    csvwriter = csv.writer(f)
                    csvwriter.writerow(["product_id", "promo"])
                    for store_promotions in data:
                        for product_id in store_promotions["ids"]:
                            csvwriter.writerow([product_id, store_promotions["promocode"]])

    def load_products(self, directory):
        for file_name in sorted(glob.glob(f"{directory}/*.csv")):
            print(f"Read product data from {file_name}")
            vendor, _ = get_file_name_and_ext(file_name)
            ProductHelper.import_promotion_products_from_csv(file_path=file_name, vendor_slug=vendor)

    def handle(self, *args, **options):
        self.remove_csv_files()
        self.create_csv_results()
        self.load_products(directory="promotions")
