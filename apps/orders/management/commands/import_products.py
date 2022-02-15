import glob
import os
from collections import defaultdict
from decimal import Decimal

import pandas as pd
from django.core.management import BaseCommand
from slugify import slugify

from apps.accounts.models import Vendor
from apps.orders.models import Product, ProductCategory, ProductImage


class Command(BaseCommand):
    help = "Import products from csv files to table"

    def add_arguments(self, parser):
        parser.add_argument(
            "--directory",
            type=str,
            help="The path to directory contains product csv files",
            default="products",
        )

    def load_products_from_vendor(self, file_path):
        print("=" * 100)
        file_name = file_path.split(os.path.sep)[-1]
        vendor_slug = file_name.split(".")[0]
        vendor = Vendor.objects.filter(slug=vendor_slug).first()
        if vendor is None:
            return None

        print(f"{vendor}: Importing products")
        df = pd.read_csv(file_path, na_filter=False)

        df_index = 0
        batch_size = 500
        df_len = len(df)

        while df_len > df_index:
            sub_df = df[df_index : df_index + batch_size]
            product_objs = []
            for index, row in sub_df.iterrows():
                category = slugify(row.pop("category"))
                product_category = self.product_categories.get(vendor_slug, {}).get(category)
                if product_category is None:
                    product_category = self.product_categories["other"]

                product_price = row.pop("price")
                if product_price:
                    product_price = product_price.replace(",", "")
                    product_price = product_price.strip("$")
                else:
                    product_price = 0
                    print(f"{vendor}: {row['name']} {row['url']} has no price from {vendor}")

                product_objs.append(
                    Product(
                        vendor=vendor,
                        product_id=row["product_id"],
                        name=row["name"],
                        product_unit=row["product_unit"],
                        description=row["description"],
                        url=row["url"],
                        category=product_category,
                        price=Decimal(product_price),
                    )
                )

            product_objs = Product.objects.bulk_create(product_objs)
            print(f"{vendor}: {batch_size} products created")

            product_image_objs = []
            for product, product_images in zip(product_objs, sub_df["images"]):
                product_images = product_images.split(";")
                for product_image in product_images:
                    product_image_objs.append(ProductImage(product=product, image=product_image))

            ProductImage.objects.bulk_create(product_image_objs)
            df_index += batch_size

    def load_product_category(self):
        product_categories = ProductCategory.objects.all()

        self.product_categories = defaultdict(dict)

        for product_category in product_categories:
            if product_category.vendor_categories is None:
                self.product_categories["other"] = product_category
                continue
            for vendor_slug, vendor_categories in product_category.vendor_categories.items():
                for vendor_category in vendor_categories:
                    self.product_categories[vendor_slug][vendor_category] = product_category

    def load_products(self, directory):
        for file_name in glob.glob(f"{directory}/*.csv"):
            print(f"Read product data from {file_name}")
            self.load_products_from_vendor(file_name)

    def handle(self, *args, **options):
        self.load_product_category()
        self.load_products(options["directory"])
