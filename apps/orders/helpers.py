import asyncio as aio
import csv
import datetime
import itertools
from collections import defaultdict
from decimal import Decimal
from functools import reduce
from itertools import chain
from operator import or_
from typing import Dict, List, Optional, TypedDict, Union

import pandas as pd
from aiohttp import ClientSession
from asgiref.sync import sync_to_async
from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models import (
    Case,
    Count,
    Exists,
    F,
    Model,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.utils import timezone
from slugify import slugify

from apps.accounts.models import Office as OfficeModel
from apps.accounts.models import OfficeVendor as OfficeVendorModel
from apps.accounts.models import Vendor as VendorModel
from apps.common.utils import (
    bulk_create,
    bulk_update,
    concatenate_list_as_string,
    concatenate_strings,
    convert_string_to_price,
    find_numeric_values_from_string,
    find_words_from_string,
    get_file_name_and_ext,
    remove_character_between_numerics,
    sort_and_write_to_csv,
)
from apps.orders.models import OfficeProduct as OfficeProductModel
from apps.orders.models import Product as ProductModel
from apps.orders.models import ProductCategory as ProductCategoryModel
from apps.orders.models import ProductImage as ProductImageModel
from apps.vendor_clients.async_clients import BaseClient as BaseAsyncClient
from apps.vendor_clients.errors import VendorAuthenticationFailed
from apps.vendor_clients.sync_clients import BaseClient as BaseSyncClient
from apps.vendor_clients.types import Product, ProductPrice, VendorCredential

SmartID = Union[int, str]
ProductID = SmartID
ProductIDs = List[ProductID]
CSV_DELIMITER = "!@#$%"


class ParentProduct(TypedDict):
    product: ProductModel
    children_ids: ProductIDs


class OfficeProductHelper:
    @staticmethod
    def get_available_sibling_products(office: Union[SmartID, OfficeModel], product: Union[SmartID, ProductModel]):
        if isinstance(product, str):
            product = ProductModel.objects.get(id=product)
        if isinstance(office, OfficeModel):
            office_id = office.id
        else:
            office_id = office

        office_products = OfficeProductModel.objects.filter(Q(office_id=office_id))
        if product.parent:
            sibling_products = (
                product.parent.children.select_related("vendor")
                .prefetch_related(Prefetch("office_products", queryset=office_products, to_attr="office_product"))
                .exclude(id=product.id)
            )
            ret = []
            for product in sibling_products:
                if product.vendor.slug in ("net_32", "implant_direct", "edge_endo", "dental_city"):
                    if product.price is None or product.price == 0:
                        continue
                else:
                    if product.office_product and product.office_product[0].product_vendor_status:
                        pass

                ret.append(product)
            return ret
        return ProductModel.objects.none()

    @staticmethod
    def get_associated_office_product(
        office: Union[SmartID, OfficeModel],
        product: Union[SmartID, ProductModel],
        is_inventory: Optional[bool] = None,
    ) -> Optional[OfficeProductModel]:
        if isinstance(office, OfficeModel):
            office = office.id

        q = Q(product_id=product) & Q(office_id=office)
        if is_inventory is not None:
            q &= Q(is_inventory=is_inventory)

        office_product = OfficeProductModel.objects.filter(q).first()
        if office_product:
            return office_product

    @staticmethod
    def get_product_price(
        office: Union[SmartID, OfficeModel], product: Union[SmartID, ProductModel]
    ) -> Optional[Decimal]:
        if isinstance(product, ProductModel):
            if product.price:
                return product.price

            product = product.id

        if isinstance(office, OfficeModel):
            office = office.id

        office_product = OfficeProductModel.objects.filter(product_id=product, office_id=office).first()
        if office_product:
            return office_product.price

    @staticmethod
    def get_office_vendors(office_id: str, vendor_slugs: List[str]) -> Dict[str, VendorCredential]:
        q = [Q(office_id=office_id) & Q(vendor__slug=vendor_slug) for vendor_slug in vendor_slugs]
        office_vendors = OfficeVendorModel.objects.filter(reduce(or_, q)).values(
            "vendor__slug", "username", "password"
        )
        return {
            office_vendor["vendor__slug"]: {
                "username": office_vendor["username"],
                "password": office_vendor["password"],
            }
            for office_vendor in office_vendors
        }

    @staticmethod
    def update_products_prices(products_prices: Dict[str, ProductPrice], office_id: str):
        """Store product prices to table"""
        print("update_products_prices")
        last_price_updated = timezone.now()
        product_ids = products_prices.keys()
        products = ProductModel.objects.in_bulk(product_ids)
        office_products = OfficeProductModel.objects.select_related("product").filter(
            office_id=office_id, product_id__in=product_ids
        )

        with transaction.atomic():
            updated_product_ids = []
            for office_product in office_products:
                office_product.price = products_prices[office_product.product.id]["price"]
                office_product.product_vendor_status = products_prices[office_product.product.id][
                    "product_vendor_status"
                ]
                office_product.last_price_updated = last_price_updated
                updated_product_ids.append(office_product.product.id)

            bulk_update(
                model_class=OfficeProductModel,
                objs=office_products,
                fields=["price", "product_vendor_status", "last_price_updated"],
            )

            # update product price
            products_to_be_updated = []
            for product_id, product in products.items():
                if product.vendor.slug not in settings.NON_FORMULA_VENDORS:
                    continue
                product.price = products_prices[product_id]["price"]
                product.product_vendor_status = products_prices[product_id]["product_vendor_status"]
                product.last_price_updated = last_price_updated
                products_to_be_updated.append(product)

            bulk_update(
                model_class=ProductModel,
                objs=products_to_be_updated,
                fields=["price", "product_vendor_status", "last_price_updated"],
            )

            creating_products = []
            for product_id in product_ids:
                if product_id in updated_product_ids:
                    continue
                creating_products.append(
                    OfficeProductModel(
                        office_id=office_id,
                        product=products[product_id],
                        price=products_prices[product_id]["price"],
                        last_price_updated=last_price_updated,
                        product_vendor_status=products_prices[product_id]["product_vendor_status"],
                    )
                )

            bulk_create(OfficeProductModel, creating_products)

    @staticmethod
    async def get_product_prices_by_ids(
        products: List[str], office: Union[SmartID, OfficeModel]
    ) -> Dict[str, ProductPrice]:
        products = await sync_to_async(ProductModel.objects.in_bulk)(products)
        return await OfficeProductHelper.get_product_prices(products, office)

    @staticmethod
    async def get_product_prices(
        products: Dict[SmartID, ProductModel], office: Union[SmartID, OfficeModel]
    ) -> Dict[str, ProductPrice]:
        """
        This return prices for products
        1. fetch prices from database
        2. for products whose prices do not exist, we try to fetch prices from vendors
        """
        # TODO: add more error handling
        if isinstance(office, OfficeModel):
            office_id = office.id
        else:
            office_id = office

        product_prices_from_db = await sync_to_async(OfficeProductHelper.get_products_prices_from_db)(
            products, office_id
        )
        print("after from_db")
        # product_prices_from_db = defaultdict(dict)

        # product_prices_from_db = defaultdict(dict)


        # fetch prices from vendors
        products_to_be_fetched = {}
        for product_id, product in products.items():
            # TODO: should be exclude products that has no vendor
            if product_id not in product_prices_from_db.keys():
                product_data = await sync_to_async(product.to_dict)()
                if product_data["vendor"] not in (
                    "implant_direct",
                    "edge_endo",
                    # "net_32",
                    # "dental_city",
                ):
                    products_to_be_fetched[product_id] = product_data
        if products_to_be_fetched:
            product_prices_from_vendors = await OfficeProductHelper.get_product_prices_from_vendors(
                products_to_be_fetched, office_id
            )
            return {**product_prices_from_db, **product_prices_from_vendors}

        return product_prices_from_db

    @staticmethod
    def get_products_prices_from_db(products: Dict[str, ProductModel], office_id: str) -> Dict[str, ProductPrice]:
        product_ids_from_formula_vendors = []
        product_ids_from_non_formula_vendors = []
        for product_id, product in products.items():
            if product.vendor.slug in settings.FORMULA_VENDORS:
                product_ids_from_formula_vendors.append(product_id)
            else:
                product_ids_from_non_formula_vendors.append(product_id)

        product_prices = defaultdict(dict)

        # get prices of products from formula vendors
        price_least_update_date = timezone.now() - datetime.timedelta(days=settings.PRODUCT_PRICE_UPDATE_CYCLE)
        office_products = (
            OfficeProductModel.objects.annotate(
                outdated=Case(
                    When(
                        Q(last_price_updated__lt=price_least_update_date) | Q(last_price_updated__isnull=True),
                        then=True,
                    ),
                    default=False,
                )
            )
            .filter(product_id__in=product_ids_from_formula_vendors, office_id=office_id, outdated=True)
            .values("product_id", "price", "product_vendor_status")
        )
        for office_product in office_products:
            product_prices[office_product["product_id"]]["price"] = office_product["price"]
            product_prices[office_product["product_id"]]["product_vendor_status"] = office_product[
                "product_vendor_status"
            ]

        # get prices of products from non-informula vendors
        for product_id in product_ids_from_non_formula_vendors:
            recent_price = products[product_id].recent_price
            if recent_price:
                product_prices[product_id]["price"] = recent_price
                product_prices[product_id]["product_vendor_status"] = ""

        return product_prices

    @staticmethod
    async def get_product_prices_from_vendors(products: Dict[str, Product], office_id: str) -> Dict[str, ProductPrice]:
        print("get_product_prices_from_vendors")
        product_prices_from_vendors = {}
        if products:

            vendor_slugs = set([product["vendor"] for product_id, product in products.items()])
            vendors_credentials = await sync_to_async(OfficeProductHelper.get_office_vendors)(
                vendor_slugs=vendor_slugs, office_id=office_id
            )
            product_prices_from_vendors = await VendorHelper.get_products_prices(
                products=products, vendors_credentials=vendors_credentials, use_async_client=True
            )
            print("============== update ==============")
            await sync_to_async(OfficeProductHelper.update_products_prices)(product_prices_from_vendors, office_id)

        return product_prices_from_vendors

    @staticmethod
    def get_vendor_product_ids(office_id: str, vendor_slug: str):
        office_products = OfficeProductModel.objects.filter(Q(office_id=office_id) & Q(product_id=OuterRef("pk")))
        return list(
            ProductModel.objects.annotate(office_product_price=Subquery(office_products.values("price")[:1]))
            .annotate(
                product_price=Case(
                    When(office_product_price__isnull=False, then=F("office_product_price")),
                    When(price__isnull=False, then=F("price")),
                    default=Value(None),
                )
            )
            .filter(vendor__slug=vendor_slug, product_price__isnull=True)
            .values_list("id", flat=True)
        )

    @staticmethod
    async def get_all_product_prices_from_vendors(office_id: str, vendor_slugs: List[str]):
        for vendor_slug in vendor_slugs:
            vendor_product_ids = await sync_to_async(OfficeProductHelper.get_vendor_product_ids)(
                office_id, vendor_slug
            )
            print("get_all_product_prices_from_vendors")
            print(vendor_product_ids)
            for i in range(0, len(vendor_product_ids), 100):
                product_prices_from_vendors = await OfficeProductHelper.get_product_prices_by_ids(
                    vendor_product_ids[i * 100 : (i + 1) * 100], office_id
                )
                await aio.sleep(10)
                print(product_prices_from_vendors)
        print("======== DONE fetch =========")

    @staticmethod
    async def get_products_from_vendors(
        vendor_slugs: List[str], q: str, min_price: int = 0, max_price: int = 0, office_id: Optional[str] = None
    ):
        pass
        # if office_id:
        #     vendors_credentials = await sync_to_async(OfficeProductHelper.get_office_vendors)(
        #         vendor_slugs=vendor_slugs, office_id=office_id
        #     )
        # product_prices_from_vendors = await VendorHelper.search_products(
        #     vendors_credentials, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price")


class VendorHelper:
    CONSUMER_NUMBERS = 5

    @staticmethod
    async def validate_user_credential(
        vendor_slug: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):

        try:
            vendor_client = BaseAsyncClient.make_handler(
                vendor_slug=vendor_slug,
                session=apps.get_app_config("accounts").session,
                username=username,
                password=password,
            )
            await vendor_client.login()
            return True
        except VendorAuthenticationFailed:
            return False

    @staticmethod
    def get_vendor_async_clients(
        vendors_credentials: Dict[str, VendorCredential], session: ClientSession
    ) -> Dict[str, BaseAsyncClient]:
        clients = {}
        for vendor_slug, vendors_credential in vendors_credentials.items():
            clients[vendor_slug] = BaseAsyncClient.make_handler(
                vendor_slug=vendor_slug,
                session=session,
                username=vendors_credential["username"],
                password=vendors_credential["password"],
            )
        return clients

    @staticmethod
    def get_vendor_sync_clients(vendors_credentials: Dict[str, VendorCredential]) -> Dict[str, BaseAsyncClient]:
        clients = {}
        for vendor_slug, vendors_credential in vendors_credentials.items():
            clients[vendor_slug] = BaseSyncClient.make_handler(
                vendor_slug=vendor_slug,
                username=vendors_credential["username"],
                password=vendors_credential["password"],
            )
        return clients

    @staticmethod
    async def get_products_prices(
        products: Dict[str, Product], vendors_credentials: Dict[str, VendorCredential], use_async_client=True
    ) -> Dict[str, ProductPrice]:
        vendor_products_2_products_mapping = defaultdict(dict)
        vendor_slugs = set()
        for product_id, product in products.items():
            vendor_slugs.add(product["vendor"])
            vendor_products_2_products_mapping[product["vendor"]][product["product_id"]] = product_id

        tasks = []
        if use_async_client:
            session = getattr(apps.get_app_config("accounts"), "session", None)
            aio_session = None
            if session is None:
                aio_session = ClientSession()

            clients = VendorHelper.get_vendor_async_clients(vendors_credentials, session or aio_session)
        else:
            clients = VendorHelper.get_vendor_sync_clients(vendors_credentials)
        for vendor_slug in vendor_slugs:
            vendor_products = list(filter(lambda x: x["vendor"] == vendor_slug, products.values()))
            tasks.append(clients[vendor_slug].get_products_prices(vendor_products))
        prices_results = await aio.gather(*tasks, return_exceptions=True)

        ret: Dict[str, ProductPrice] = {}
        for vendor_slug, prices_result in zip(vendor_slugs, prices_results):
            if not isinstance(prices_result, dict):
                continue
            for vendor_product_id, price in prices_result.items():
                ret[vendor_products_2_products_mapping[vendor_slug][vendor_product_id]] = price

        if use_async_client:
            if aio_session is not None:
                await aio_session.close()
        return ret

    @staticmethod
    async def search_products(
        vendors_credentials: Dict[str, VendorCredential],
        query: str,
        page: int = 0,
        min_price: int = 0,
        max_price: int = 0,
    ):
        clients = VendorHelper.get_vendor_async_clients(vendors_credentials)
        tasks = []
        for client in clients:
            if hasattr(client, "search_products"):
                tasks.append(client.search_products(query=query, page=page, min_price=min_price, max_price=max_price))

        if tasks:
            search_results = await aio.gather(*tasks, return_exceptions=True)

        return search_results


class ProductHelper:
    @staticmethod
    def get_vendor_category_mapping() -> Dict[str, Dict[str, ProductCategoryModel]]:
        """Return the vendor category vs our product category mapping
        {
            "vendor slug": {
                "vendor category": "our product category",
            }
        }
        Example:
        {
            "henry_schein": {
                "anesthetics": "anesthetics",
            }
        }
        """
        ret = defaultdict(dict)
        product_categories = ProductCategoryModel.objects.all()
        for product_category in product_categories:
            if product_category.vendor_categories is None:
                ret["other"] = product_category
                continue

            for vendor_slug, vendor_categories in product_category.vendor_categories.items():
                for vendor_category in vendor_categories:
                    ret[vendor_slug][vendor_category] = product_category

        return ret

    @staticmethod
    def read_products_from_csv(file_path, output_duplicates: bool = True) -> pd.DataFrame:
        df = pd.read_csv(file_path, na_filter=False, low_memory=False, dtype=str)
        duplicated_products = df[df["product_id"].duplicated()]
        file_name, ext = get_file_name_and_ext(file_path)
        if output_duplicates:
            sort_and_write_to_csv(duplicated_products, columns=["category"], file_name=f"{file_name}_duplicated.csv")
        return df.drop_duplicates(subset=["product_id"], keep="first")

    @staticmethod
    def import_products_from_csv(file_path, vendor_slug, fields: Optional[List[str]] = None, verbose: bool = True):
        df = ProductHelper.read_products_from_csv(file_path, output_duplicates=verbose)
        df_index = 0
        batch_size = 500
        df_len = len(df)

        vendor = VendorModel.objects.get(slug=vendor_slug)
        category_mapping = ProductHelper.get_vendor_category_mapping()

        while df_len > df_index:
            sub_df = df[df_index : df_index + batch_size]
            product_objs_to_be_created = []
            product_objs_to_be_updated = []
            for index, row in sub_df.iterrows():
                category = row.get("category", "")
                category = slugify(category)
                product_category = category_mapping[vendor_slug].get(category)
                if product_category is None:
                    product_category = category_mapping["other"]

                try:
                    product_price = convert_string_to_price(row["price"])
                except Exception:
                    product_price = None

                manufacturer_number_origin = row.get("manufacturer_number")
                manufacturer_number = manufacturer_number_origin.replace("-", "") if manufacturer_number_origin else ""
                if fields:
                    product = ProductModel.objects.filter(product_id=row["product_id"], vendor=vendor).first()
                    if product:
                        for field in fields:
                            if field == "price":
                                value = product_price
                            elif field == "manufacturer_number":
                                value = manufacturer_number
                            elif field == "manufacturer_number_origin":
                                value = manufacturer_number_origin
                            else:
                                value = row[field]

                            if getattr(product, field) != value:
                                setattr(product, field, value)
                                product_objs_to_be_updated.append(product)
                    else:
                        print(f"Cannot find out {row['product_id']}")
                        # product_name = row.get("name")
                        # product_unit = row.get("product_unit")
                        # url = row.get("url")
                        # if product_name is None:
                        #     continue
                        # product_objs_to_be_created.append(
                        #     ProductModel(
                        #         vendor=vendor,
                        #         product_id=row["product_id"],
                        #         name=product_name,
                        #         product_unit=product_unit,
                        #         url=url,
                        #         category=product_category,
                        #         price=product_price,
                        #         manufacturer_number=manufacturer_number,
                        #         manufacturer_number_origin=manufacturer_number_origin,
                        #     )
                        # )
                else:
                    product_objs_to_be_created.append(
                        ProductModel(
                            vendor=vendor,
                            product_id=row["product_id"],
                            name=row["name"],
                            product_unit=row["product_unit"],
                            url=row["url"],
                            category=product_category,
                            price=product_price,
                            manufacturer_number=manufacturer_number,
                            manufacturer_number_origin=manufacturer_number_origin,
                        )
                    )

            if fields:
                bulk_update(model_class=ProductModel, objs=product_objs_to_be_updated, fields=fields)
                print(f"{vendor}: {len(product_objs_to_be_updated)} products updated")

            if product_objs_to_be_created:
                product_objs = bulk_create(model_class=ProductModel, objs=product_objs_to_be_created)
                print(f"{vendor}: {len(product_objs_to_be_created)} products created")
                product_image_objs = []
                for product, product_images in zip(product_objs, sub_df["images"]):
                    product_images = product_images.split(";")
                    for product_image in product_images:
                        product_image_objs.append(ProductImageModel(product=product, image=product_image))

                bulk_create(model_class=ProductImageModel, objs=product_image_objs)
            df_index += batch_size

    @staticmethod
    def import_promotion_products_from_csv(file_path: str, vendor_slug: str):
        df = ProductHelper.read_products_from_csv(file_path, output_duplicates=False)
        df_index = 0
        batch_size = 500
        df_len = len(df)

        vendor = VendorModel.objects.get(slug=vendor_slug)
        while df_len > df_index:
            sub_df = df[df_index : df_index + batch_size]
            product_objs = []
            for index, row in sub_df.iterrows():
                product = ProductModel.objects.filter(product_id=row["product_id"], vendor=vendor).first()
                if product:
                    product.is_special_offer = True
                    price = convert_string_to_price(row.get("price"))
                    if price:
                        product.special_price = price
                    if vendor_slug == "patterson":
                        product.promotion_description = row["promo"] or row["FreeGood"]
                    else:
                        product.promotion_description = row["promo"]
                    product_objs.append(product)
                else:
                    print(f"Missing product {row['product_id']} - {row['name']}")

            bulk_update(
                model_class=ProductModel,
                objs=product_objs,
                fields=["is_special_offer", "special_price", "promotion_description"],
            )
            print(f"Updated {len(product_objs)}s products")
            df_index += batch_size

    @staticmethod
    def group_products_by_manufacturer_numbers(since: Optional[datetime.datetime] = None):
        """group products by using manufacturer_number. this number is identical for products"""
        products = ProductModel.objects.filter(manufacturer_number__isnull=False)
        if since:
            products = products.filter(updated_at__gt=since)
        manufacturer_numbers = set(
            products.order_by("manufacturer_number")
            .values("manufacturer_number")
            .annotate(products_count=Count("vendor"))
            .filter(products_count__gte=2)
            .values_list("manufacturer_number", flat=True)
        )
        products_to_be_updated = []
        # parent_products_to_be_created = []
        for i, manufacturer_number in enumerate(manufacturer_numbers):
            print(f"Calculating {i}th: {manufacturer_number}")
            similar_products = ProductModel.objects.filter(
                manufacturer_number=manufacturer_number, vendor__isnull=False
            )

            # remove already existing parent products
            similar_product_ids = similar_products.values_list("id", flat=True)
            parent_products = ProductModel.objects.filter(child__id__in=similar_product_ids).distinct()
            product_names = sorted(list(similar_products.values_list("name", flat=True)), key=lambda x: len(x))
            display_text = concatenate_list_as_string(similar_product_ids, delimiter=",")

            parent_products_count = parent_products.count()
            if parent_products_count == 1:
                parent_product = parent_products.first()
                print(f"Parent product already existed {parent_product.id} {parent_product.name}: {display_text}")
                parent_product.manufacturer_number = manufacturer_number
                parent_product.save()
            else:
                if parent_products_count >= 2:
                    parent_product_ids = parent_products.values_list("id", flat=True)
                    display_text = f"{concatenate_list_as_string(parent_product_ids, delimiter=',')}: {display_text}"
                    print(f"Existed 2 parents {display_text}")
                    ProductModel.objects.filter(id__in=parent_product_ids).delete()

                parent_product = ProductModel.objects.create(
                    name=product_names[0], manufacturer_number=manufacturer_number
                )

            for product in similar_products:
                product.parent = parent_product
                products_to_be_updated.append(product)

                # parent_products_to_be_created.append(
                #     ParentProduct(
                #         product=ProductModel(name=product_names[0], manufacturer_number=manufacturer_number),
                #         children_ids=similar_product_ids,
                #     )
                # )

        print("updating databases...")
        bulk_update(model_class=ProductModel, objs=products_to_be_updated, fields=["parent"])
        # ProductHelper.create_parent_products(parent_products_to_be_created)

    @staticmethod
    def group_products(
        product_ids: Optional[ProductID] = None,
        include_category_slugs: Optional[List[str]] = None,
        exclude_category_slugs: Optional[List[str]] = None,
        commit: bool = True,
    ):
        """Group products"""
        products = ProductModel.objects.all()
        if product_ids:
            products = products.filter(id__in=product_ids)

        vendor_slugs = products.order_by("vendor").values_list("vendor__slug", flat=True).distinct()
        if len(vendor_slugs) <= 1:
            # if the products are from one vendor, don't need to proceed further
            return None

        # get the list of similar product ids by product category
        product_categories = ProductCategoryModel.objects.order_by("name")
        if include_category_slugs:
            product_categories = product_categories.filter(slug__in=include_category_slugs)

        if exclude_category_slugs:
            product_categories = product_categories.exclude(slug__in=exclude_category_slugs)

        for product_category in product_categories:
            # In the future, we shouldn't perform group again for already grouped products,
            # but for now, we can perform this operation for all products
            ProductModel.objects.filter(vendor__isnull=True, category=product_category).delete()

            print(f"calculating {product_category.name}")
            ProductHelper.group_products_by_category(products, product_category, commit)

    @staticmethod
    def group_products_by_category(
        products: QuerySet, product_category: Optional[ProductCategoryModel] = None, commit: bool = True
    ) -> List[ProductIDs]:
        """
        Return the list of a group of product ids.
        Each element from the list is a list of product id, those products are very similar
        """
        if product_category is None or product_category.slug.lower() == "other":
            vendor_slugs = products.order_by("vendor").values_list("vendor__slug", flat=True).distinct()
        else:
            vendor_slugs = product_category.vendor_categories.keys()
            if len(vendor_slugs) <= 1:
                return []

        vendors_products = {}
        product_ids_by_vendors = []
        for vendor_slug in vendor_slugs:
            vendor_products = products.filter(vendor__slug=vendor_slug).values("id", "vendor", "name")
            if product_category:
                vendor_products = vendor_products.filter(category=product_category)

            for vendor_product in vendor_products:
                vendors_products[vendor_product["id"]] = {
                    "vendor": vendor_product["vendor"],
                    "name": vendor_product["name"],
                }

            if vendor_products:
                product_ids_by_vendors.append(vendor_products.values_list("id", flat=True))

        if len(product_ids_by_vendors) <= 1:
            return []

        similar_product_ids_list: List[ProductIDs] = ProductHelper.group_products_by_name(
            vendors_products, product_ids_by_vendors
        )
        parent_product_objs: List[ParentProduct] = []

        print("updating database")
        if commit:
            for similar_product_ids in similar_product_ids_list:
                similar_products = products.filter(id__in=similar_product_ids)
                parent_products = similar_products.filter(child__isnull=False)

                if parent_products:
                    # at least one of similar products has already children.
                    # in this case we should add other products as children of that parent product.
                    # If there are more than multiple parents, we should merge them into one

                    parent_product_ids = parent_products.values_list("id", flat=True)
                    parent_product = parent_products.first()
                    existing_children_products = ProductModel.objects.filter(parent_id__in=parent_product_ids)

                    new_similar_products = []
                    similar_products = similar_products.exclude(child__isnull=False)
                    for similar_product in chain.from_iterable([similar_products, existing_children_products]):
                        similar_product.parent = parent_product
                        new_similar_products.append(similar_product)

                    bulk_update(ProductModel, new_similar_products, fields=["parent"])

                    # delete other parents
                    parent_products.exclude(id=parent_product.id).delete()

                else:
                    parent_product_objs.append(
                        ParentProduct(
                            product=ProductModel(
                                name=similar_products[0].name,
                                category=similar_products[0].category,
                            ),
                            children_ids=similar_product_ids,
                        )
                    )

            ProductHelper.create_parent_products(parent_product_objs)

    @staticmethod
    def group_products_by_name(products, product_ids_by_vendors) -> List[ProductIDs]:
        # TODO: This algorith should be updated. like this way
        """
        1. find out 2-length similar products like current one
        2. from the 3-length product comparison, current approach seems bad,
            even though we don't calculate similarity for all pairs
        3. group_by_vendors, run combination, products just like 2-length comparison, that will be faster.
        """
        threshold = 0.7
        n_similarity = 2
        vendors_count = len(product_ids_by_vendors)
        similar_products_candidates = defaultdict(list)

        # find out all 2-length similar products
        products_combinations = itertools.combinations(product_ids_by_vendors, n_similarity)
        for products_combination in products_combinations:
            for product_ids in itertools.product(*products_combination):
                vendor_product_names = [products[product_id]["name"] for product_id in product_ids]
                similarity = ProductHelper.get_similarity(*vendor_product_names)

                if similarity > threshold:
                    display_text = "; ".join(
                        [f'{products[product_id]["vendor"]}-{product_id}' for product_id in product_ids]
                    )
                    print(f"{similarity:.2f}: {display_text}")
                    similar_products_candidates[n_similarity].append([f"{similarity:.2f}", *product_ids])

        # when finding more than 3-length similar products we need to check from candidates pairs
        n_similarity = 3
        while n_similarity <= vendors_count:
            print(f"calculating {n_similarity}=======")
            n_threshold = threshold ** (n_similarity - 1)
            n_1_similarity_products_pairs_length = len(similar_products_candidates[n_similarity - 1])
            if not n_1_similarity_products_pairs_length:
                break

            well_matching_pair_ids = set()
            for i in range(n_1_similarity_products_pairs_length - 1):
                ith_similar_products_pair = similar_products_candidates[n_similarity - 1][i][1:]
                ith_similar_product_ids = set(ith_similar_products_pair)
                ith_similar_product_vendors = set(
                    [products[product_id]["vendor"] for product_id in ith_similar_products_pair]
                )
                print(f"comparing with {i}th element ")
                for j in range(i + 1, n_1_similarity_products_pairs_length):
                    jth_similar_products_pair = similar_products_candidates[n_similarity - 1][j][1:]
                    jth_similar_product_ids = set(jth_similar_products_pair)
                    jth_similar_product_vendors = set(
                        [products[product_id]["vendor"] for product_id in jth_similar_products_pair]
                    )
                    if not ith_similar_product_ids.intersection(jth_similar_product_ids):
                        continue

                    proucts_difference = ith_similar_product_ids - jth_similar_product_ids
                    if len(proucts_difference) > 1:
                        continue

                    ith_vendor_difference = ith_similar_product_vendors - jth_similar_product_vendors
                    jth_vendor_difference = jth_similar_product_vendors - ith_similar_product_vendors

                    if ith_vendor_difference == jth_vendor_difference:
                        continue

                    if tuple(ith_similar_product_ids | jth_similar_product_ids) in well_matching_pair_ids:
                        continue

                    similar_products_pair = ith_similar_product_ids | jth_similar_product_ids
                    well_matching_pair_ids.add(tuple(similar_products_pair))
                    vendor_product_names = [products[product_id]["name"] for product_id in similar_products_pair]
                    similarity = ProductHelper.get_similarity(*vendor_product_names)

                    if similarity > n_threshold:
                        display_text = "; ".join(
                            [f'{products[product_id]["vendor"]}-{product_id}' for product_id in similar_products_pair]
                        )
                        print(f"{similarity:.2f}: {display_text}")
                        similar_products_candidates[n_similarity].append([f"{similarity:.2f}", *similar_products_pair])

            n_similarity += 1

        similar_products_candidates = chain.from_iterable([value for _, value in similar_products_candidates.items()])
        similar_products_list = ProductHelper.clean_well_matching_paris(similar_products_candidates)
        return [similar_products[1:] for similar_products in similar_products_list]

    @staticmethod
    def clean_well_matching_paris(well_matching_pairs):
        """
        This will remove partly-duplicated product paris if the well_matching_paris contains
        [(1, vendorA_productID, vendorB_productID), (0.9, vendorA_productID, vendorB_productID)]
        the second pair is not needed.
        """
        cleaned_well_matching_paris = []
        included_product_ids = set()
        well_matching_pairs = sorted(well_matching_pairs, key=lambda x: (len(x), x[0]), reverse=True)
        for well_matching_pair in well_matching_pairs:
            well_matching_product_pair_ids = set(well_matching_pair[1:])
            if included_product_ids & well_matching_product_pair_ids:
                continue
            included_product_ids |= well_matching_product_pair_ids
            cleaned_well_matching_paris.append(well_matching_pair)
        return cleaned_well_matching_paris

    @staticmethod
    def get_similarity(*products, key=None):
        total_words = set()
        matched_words = set()
        total_numeric_values = set()
        matched_numeric_values = set()
        excluded_words = {"of", "and", "with"}

        for product_i, product in enumerate(products):
            if isinstance(product, dict):
                product_name = product[key]
            elif isinstance(product, Model):
                product_name = getattr(product, key)
            else:
                product_name = product

            product_numeric_values = set(map(str.lower, find_numeric_values_from_string(product_name)))
            product_words = set(map(str.lower, find_words_from_string(product_name)))
            product_words = product_words - product_numeric_values
            product_words -= excluded_words
            total_words.update(product_words)
            total_numeric_values.update(product_numeric_values)
            if product_i == 0:
                matched_words = product_words
                matched_numeric_values = product_numeric_values
            else:
                matched_words &= product_words
                matched_numeric_values &= product_numeric_values

        if len(total_numeric_values):
            percentage = 0.4 * len(matched_words) / len(total_words) + 0.6 * len(matched_numeric_values) / len(
                total_numeric_values
            )
        else:
            percentage = len(matched_words) / len(total_words)
        return percentage

    @staticmethod
    def export_similar_products_to_csv(
        to: str = "output.csv",
        include_category_slugs: Optional[List[str]] = None,
        exclude_category_slugs: Optional[List[str]] = None,
    ):
        """export grouped products to csv format"""
        products = ProductModel.objects.filter(vendor__isnull=True).order_by("category__name")
        if include_category_slugs:
            products = products.filter(category__slug__in=include_category_slugs)

        if exclude_category_slugs:
            products = products.exclude(category__slug__in=exclude_category_slugs)

        # TODO: this might be slower than using pandas
        with open(to, "w") as f:
            csvwriter = csv.writer(f)
            csvwriter.writerow(["category", "product_ids", "vendor_products", "product_names", "product_urls"])
            for product in products:
                children_products = product.children.values("id", "product_id", "vendor__slug", "name", "url")
                product_ids = []
                vendor_products = []
                product_names = []
                product_urls = []
                for children_product in children_products:
                    product_ids.append(f'{children_product["id"]}')
                    vendor_products.append(f'{children_product["vendor__slug"]}-{children_product["product_id"]}')
                    product_names.append(children_product["name"])
                    product_urls.append(children_product["url"])

                csvwriter.writerow(
                    [
                        product.category.slug,
                        concatenate_strings(product_ids, delimeter=CSV_DELIMITER),
                        concatenate_strings(vendor_products, delimeter=CSV_DELIMITER),
                        concatenate_strings(product_names, delimeter=CSV_DELIMITER),
                        concatenate_strings(product_urls, delimeter=CSV_DELIMITER),
                    ]
                )

    @staticmethod
    def import_products_similarity(file_name: str, use_by: str = "id"):
        print(f"reading {file_name}..")
        df = pd.read_csv(file_name)

        parent_product_objs: List[ParentProduct] = []
        product_categories = ProductCategoryModel.objects.all()
        product_categories = {category.slug: category for category in product_categories}
        for _, row in df.iterrows():
            category = product_categories[row["category"]]
            if use_by == "id":
                product_ids = row["product_ids"].split(CSV_DELIMITER)
            else:
                vendor_products = row["vendor_products"].split(CSV_DELIMITER)
                vendor_products = [
                    Q(vendor__slug=vendor_product.split("-")[0]) & Q(product_id=vendor_product.split("-", 1)[1])
                    for vendor_product in vendor_products
                ]
                q = reduce(or_, vendor_products)
                product_ids = list(ProductModel.objects.filter(q).values_list("id", flat=True))

            product_names = row["product_names"].split(CSV_DELIMITER)
            parent_product_objs.append(
                ParentProduct(
                    product=ProductModel(
                        name=product_names[0],
                        category=category,
                    ),
                    children_ids=product_ids,
                )
            )
        print("updating databases..")
        ProductHelper.create_parent_products(parent_product_objs)

    @staticmethod
    def create_parent_products(parent_product_objs: List[ParentProduct]):
        if parent_product_objs:
            parent_products = bulk_create(
                ProductModel, [parent_product_obj["product"] for parent_product_obj in parent_product_objs]
            )
            for parent_product_instance, parent_product_obj in zip(parent_products, parent_product_objs):
                children_products = ProductModel.objects.filter(id__in=parent_product_obj["children_ids"])
                for children_product in children_products:
                    children_product.parent = parent_product_instance
                bulk_update(ProductModel, children_products, fields=["parent"])

    @staticmethod
    def get_products(
        office: Union[OfficeModel, SmartID],
        fetch_parents: bool = True,
        product_ids: Optional[List[SmartID]] = None,
        products: Optional[QuerySet] = None,
        selected_products: Optional[List[SmartID]] = None,
    ):
        """
        fetch_parents:  True:   fetch parent products
                        False:  fetch all products
        selected_products: list of product id, product ids in this list will be ordered first
        """
        if isinstance(office, OfficeModel):
            office_pk = office.id
        else:
            office_pk = office

        # get products from vendors that are linked to the office account
        if products is None:
            products = ProductModel.objects.select_related("vendor", "category")

        connected_vendor_ids = OfficeVendorHelper.get_connected_vendor_ids(office_pk)
        if fetch_parents:
            products = products.filter(parent__isnull=True)

            if product_ids is not None:
                products = products.filter(Q(id__in=product_ids) | Q(child__id__in=product_ids)).distinct()

            products = products.filter(
                Q(vendor_id__in=connected_vendor_ids)
                | (Q(vendor__isnull=True) & Q(child__vendor_id__in=connected_vendor_ids))
            ).distinct()
        else:
            if product_ids is not None:
                products = products.filter(Q(id__in=product_ids))

            products = products.filter(Q(vendor_id__in=connected_vendor_ids))

        if selected_products is None:
            selected_products = []

        # TODO: this should be optimized
        office_products = OfficeProductModel.objects.filter(Q(office_id=office_pk))
        price_least_update_date = timezone.now() - datetime.timedelta(days=settings.PRODUCT_PRICE_UPDATE_CYCLE)
        office_product_price = OfficeProductModel.objects.filter(
            Q(office_id=office_pk) & Q(product_id=OuterRef("pk")) & Q(last_price_updated__gte=price_least_update_date)
        ).values("price")

        # we treat parent product as inventory product if it has inventory children product
        inventory_office_product = OfficeProductModel.objects.filter(
            Q(office_id=office_pk) & Q(is_inventory=True) & Q(product_id=OuterRef("pk"))
        )

        return (
            products.prefetch_related(Prefetch("office_products", queryset=office_products, to_attr="office_product"))
            .annotate(office_product_price=Subquery(office_product_price[:1]))
            .annotate(is_inventory=Exists(inventory_office_product))
            # .annotate(last_order_date=Subquery(inventory_office_products.values("last_order_date")[:1]))
            # .annotate(last_order_price=Subquery(inventory_office_products.values("price")[:1]))
            # .annotate(product_vendor_status=Subquery(office_products.values("product_vendor_status")[:1]))
            .annotate(
                product_price=Case(
                    When(price__isnull=False, then=F("price")),
                    When(office_product_price__isnull=False, then=F("office_product_price")),
                    default=Value(None),
                )
            )
            .annotate(
                selected_product=Case(
                    When(id__in=selected_products, then=Value(0)),
                    default=Value(1),
                )
            )
            .order_by("selected_product", "-is_inventory", "product_price")
        )

    @staticmethod
    def get_products_v2(
        office: Union[OfficeModel, SmartID],
        fetch_parents: bool = True,
        product_ids: Optional[List[SmartID]] = None,
        products: Optional[QuerySet] = None,
        selected_products: Optional[List[SmartID]] = None,
    ):
        """
        fetch_parents:  True:   fetch parent products
                        False:  fetch all products
        selected_products: list of product id, product ids in this list will be ordered first
        """
        if isinstance(office, OfficeModel):
            office_pk = office.id
        else:
            office_pk = office

        # get products from vendors that are linked to the office account
        if products is None:
            products = ProductModel.objects.all()

        connected_vendor_ids = OfficeVendorHelper.get_connected_vendor_ids(office_pk)
        products = products.exclude(parent__isnull=True)

        if product_ids is not None:
            products = products.filter(Q(id__in=product_ids))

        products = products.filter(Q(vendor_id__in=connected_vendor_ids))

        if selected_products is None:
            selected_products = []

        parent_product_ids = products.values_list("parent_id", flat=True)
        products = ProductModel.objects.filter(id__in=parent_product_ids).select_related("vendor", "category")

        # TODO: this should be optimized
        office_products = OfficeProductModel.objects.filter(Q(office_id=office_pk))
        office_product = OfficeProductModel.objects.filter(Q(office_id=office_pk) & Q(product_id=OuterRef("pk")))

        # we treat parent product as inventory product if it has inventory children product
        inventory_office_product = OfficeProductModel.objects.filter(
            Q(office_id=office_pk) & Q(is_inventory=True) & Q(product_id=OuterRef("pk"))
        )

        return (
            products.prefetch_related(Prefetch("office_products", queryset=office_products, to_attr="office_product"))
            .annotate(office_product_price=Subquery(office_product.values("price")[:1]))
            .annotate(is_inventory=Exists(inventory_office_product))
            # .annotate(last_order_date=Subquery(inventory_office_products.values("last_order_date")[:1]))
            # .annotate(last_order_price=Subquery(inventory_office_products.values("price")[:1]))
            # .annotate(product_vendor_status=Subquery(office_products.values("product_vendor_status")[:1]))
            .annotate(
                product_price=Case(
                    When(price__isnull=False, then=F("price")),
                    When(office_product_price__isnull=False, then=F("office_product_price")),
                    default=Value(None),
                )
            )
            .annotate(
                selected_product=Case(
                    When(id__in=selected_products, then=Value(0)),
                    default=Value(1),
                )
            )
            .order_by("selected_product", "-is_inventory", "product_price")
        )

    @staticmethod
    def get_products_v3(
        query: str,
        office: Union[OfficeModel, SmartID],
        fetch_parents: bool = True,
        selected_products: Optional[List[SmartID]] = None,
    ):
        if isinstance(office, OfficeModel):
            office_pk = office.id
        else:
            office_pk = office

        connected_vendor_ids = OfficeVendorHelper.get_connected_vendor_ids(office_pk)
        products = ProductModel.objects.filter(Q(vendor_id__in=connected_vendor_ids))
        products = products.search(query)
        available_vendors = [
            vendor
            for vendor in products.values_list("vendor__slug", flat=True).order_by("vendor__slug").distinct()
            if vendor
        ]
        if selected_products is None:
            selected_products = []

        parent_product_ids = products.filter(parent__isnull=False).values_list("parent_id", flat=True)
        product_ids = products.filter(parent__isnull=True).values_list("id", flat=True)
        products = ProductModel.objects.filter(Q(id__in=parent_product_ids) | Q(id__in=product_ids)).select_related(
            "vendor", "category"
        )

        # TODO: this should be optimized
        office_products = OfficeProductModel.objects.filter(Q(office_id=office_pk))
        price_least_update_date = timezone.now() - datetime.timedelta(days=settings.PRODUCT_PRICE_UPDATE_CYCLE)
        office_product_price = OfficeProductModel.objects.filter(
            Q(office_id=office_pk) & Q(product_id=OuterRef("pk")) & Q(last_price_updated__gte=price_least_update_date)
        ).values("price")

        # we treat parent product as inventory product if it has inventory children product
        inventory_office_product = OfficeProductModel.objects.filter(
            Q(office_id=office_pk) & Q(is_inventory=True) & Q(product_id=OuterRef("pk"))
        )

        return (
            products.prefetch_related(Prefetch("office_products", queryset=office_products, to_attr="office_product"))
            .annotate(office_product_price=Subquery(office_product_price[:1]))
            .annotate(is_inventory=Exists(inventory_office_product))
            # .annotate(last_order_date=Subquery(inventory_office_products.values("last_order_date")[:1]))
            # .annotate(last_order_price=Subquery(inventory_office_products.values("price")[:1]))
            # .annotate(product_vendor_status=Subquery(office_products.values("product_vendor_status")[:1]))
            .annotate(
                product_price=Case(
                    When(price__isnull=False, then=F("price")),
                    When(office_product_price__isnull=False, then=F("office_product_price")),
                    default=Value(None),
                )
            )
            .annotate(
                selected_product=Case(
                    When(id__in=selected_products, then=Value(0)),
                    default=Value(1),
                )
            )
            .annotate(
                group=Case(
                    When(vendor__isnull=True, then=Value(0)),
                    default=Value(1),
                )
            )
            .order_by("selected_product", "-is_inventory", "group", "product_price")
        ), available_vendors

    @staticmethod
    def suggest_products(search: str, office: Union[OfficeModel, SmartID]):
        if isinstance(office, OfficeModel):
            office = office.id
        # we treat parent product as inventory product if it has inventory children product
        sub_query_filter = Q(is_inventory=True) & Q(product_id=OuterRef("pk"))
        if office:
            sub_query_filter &= Q(office_id=office)
        inventory_products = OfficeProductModel.objects.filter(sub_query_filter)

        product_id_search = remove_character_between_numerics(search, character="-")
        product_filter = Q(parent__isnull=True) & (
            Q(name__icontains=search)
            | Q(product_id__icontains=search)
            | Q(product_id__icontains=product_id_search)
            | Q(child__product_id=product_id_search)
        )
        return (
            ProductModel.objects.filter(product_filter)
            .annotate(is_inventory=Exists(inventory_products))
            .distinct()
            .order_by("-is_inventory")
        )


class OfficeVendorHelper:
    @staticmethod
    def get_connected_vendor_ids(office: Union[int, str, OfficeModel]) -> List[str]:
        if not isinstance(office, OfficeModel):
            office = OfficeModel.objects.get(id=office)

        return office.connected_vendors.values_list("vendor_id", flat=True)
