import asyncio as aio
import csv
import itertools
from collections import defaultdict
from decimal import Decimal
from functools import reduce
from itertools import chain
from operator import or_
from typing import Dict, List, Optional, TypedDict, Union

import pandas as pd
from asgiref.sync import sync_to_async
from django.apps import apps
from django.db import transaction
from django.db.models import (
    Case,
    F,
    Model,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from slugify import slugify

from apps.accounts.models import Office as OfficeModel
from apps.accounts.models import OfficeVendor as OfficeVendorModel
from apps.accounts.models import Vendor as VendorModel
from apps.common.utils import (
    bulk_create,
    bulk_update,
    concatenate_strings,
    convert_string_to_price,
    find_numeric_values_from_string,
    find_words_from_string,
    get_file_name_and_ext,
    sort_and_write_to_csv,
)
from apps.orders.models import OfficeProduct as OfficeProductModel
from apps.orders.models import Product as ProductModel
from apps.orders.models import ProductCategory as ProductCategoryModel
from apps.orders.models import ProductImage as ProductImageModel
from apps.vendor_clients import BaseClient
from apps.vendor_clients.errors import VendorAuthenticationFailed
from apps.vendor_clients.types import Product, VendorCredential

SmartID = Union[int, str]
ProductID = SmartID
ProductIDs = List[ProductID]


class ParentProduct(TypedDict):
    product: ProductModel
    children_ids: ProductIDs


class OfficeProductHelper:
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
    def update_products_prices(products_prices: Dict[str, Decimal], office_id: str):
        product_ids = products_prices.keys()
        products = ProductModel.objects.in_bulk(product_ids)
        office_products = OfficeProductModel.objects.select_related("product").filter(
            office_id=office_id, product_id__in=product_ids
        )

        with transaction.atomic():
            updated_product_ids = []
            for office_product in office_products:
                office_product.price = products_prices[office_product.product.id]
                updated_product_ids.append(office_product.product.id)

            bulk_update(model_class=OfficeProductModel, objs=office_products, fields=["price"])

            creating_products = []
            for product_id in product_ids:
                if product_id in updated_product_ids:
                    continue
                creating_products.append(
                    OfficeProductModel(
                        office_id=office_id,
                        product=products[product_id],
                        price=products_prices[product_id],
                    )
                )

            bulk_create(OfficeProductModel, creating_products)

    @staticmethod
    async def get_product_prices_by_ids(products: List[str], office: Union[str, OfficeModel]) -> Dict[str, Decimal]:
        products = await sync_to_async(ProductModel.objects.in_bulk)(products)
        return await OfficeProductHelper.get_product_prices(products, office)

    @staticmethod
    async def get_product_prices(
        products: Dict[str, ProductModel], office: Union[str, OfficeModel]
    ) -> Dict[str, Decimal]:
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

        # fetch prices from vendors
        products_to_be_fetched = {}
        for product_id, product in products.items():
            # TODO: should be exclude products that has no vendor
            if product_id not in product_prices_from_db.keys():
                products_to_be_fetched[product_id] = await sync_to_async(product.to_dict)()

        if products_to_be_fetched:
            product_prices_from_vendors = await OfficeProductHelper.get_product_prices_from_vendors(
                products_to_be_fetched, office_id
            )
            return {**product_prices_from_db, **product_prices_from_vendors}

        return product_prices_from_db

    @staticmethod
    def get_products_prices_from_db(products: Dict[str, ProductModel], office_id: str) -> Dict[str, Decimal]:
        # fetch prices from database
        product_prices: Dict[str, Decimal] = {}
        office_products = OfficeProductModel.objects.filter(
            product_id__in=products.keys(), office_id=office_id
        ).values("product_id", "price")
        for office_product in office_products:
            if office_product["price"]:
                product_prices[office_product["product_id"]] = office_product["price"]

        return product_prices

    @staticmethod
    async def get_product_prices_from_vendors(products: Dict[str, Product], office_id: str) -> Dict[str, Decimal]:
        product_prices_from_vendors = {}
        if products:
            vendor_slugs = set([product["vendor"] for product_id, product in products.items()])
            vendors_credentials = await sync_to_async(OfficeProductHelper.get_office_vendors)(
                vendor_slugs=vendor_slugs, office_id=office_id
            )
            product_prices_from_vendors = await VendorHelper.get_products_prices(products, vendors_credentials)
            await sync_to_async(OfficeProductHelper.update_products_prices)(product_prices_from_vendors, office_id)

        return product_prices_from_vendors

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
            vendor_client = BaseClient.make_handler(
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
    def get_vendor_clients(vendors_credentials: Dict[str, VendorCredential]) -> List[BaseClient]:
        clients = []
        for vendor_slug, vendors_credential in vendors_credentials.items():
            clients.append(
                BaseClient.make_handler(
                    vendor_slug=vendor_slug,
                    session=apps.get_app_config("accounts").session,
                    username=vendors_credential["username"],
                    password=vendors_credential["password"],
                )
            )
        return clients

    @staticmethod
    async def get_products_prices(
        products: Dict[str, Product], vendors_credentials: Dict[str, VendorCredential]
    ) -> Dict[str, Decimal]:
        vendor_products_2_products_mapping = defaultdict(dict)
        vendor_slugs = set()
        for product_id, product in products.items():
            vendor_slugs.add(product["vendor"])
            vendor_products_2_products_mapping[product["vendor"]][product["product_id"]] = product_id

        tasks = []
        clients = VendorHelper.get_vendor_clients(vendors_credentials)
        for vendor_slug, client in zip(vendor_slugs, clients):
            vendor_products = list(filter(lambda x: x["vendor"] == vendor_slug, products.values()))
            tasks.append(client.get_products_prices(vendor_products))
        prices_results = await aio.gather(*tasks, return_exceptions=True)

        ret: Dict[str, Decimal] = {}
        for vendor_slug, prices_result in zip(vendor_slugs, prices_results):
            if not isinstance(prices_results, dict):
                continue
            for vendor_product_id, price in prices_result.items():
                ret[vendor_products_2_products_mapping[vendor_slug][vendor_product_id]] = price

        return ret

    @staticmethod
    async def search_products(
        vendors_credentials: Dict[str, VendorCredential],
        query: str,
        page: int = 0,
        min_price: int = 0,
        max_price: int = 0,
    ):
        clients = VendorHelper.get_vendor_clients(vendors_credentials)
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
    def import_products_from_csv(file_path, vendor_slug, verbose: bool = True):
        df = ProductHelper.read_products_from_csv(file_path, output_duplicates=verbose)
        df_index = 0
        batch_size = 500
        df_len = len(df)

        vendor = VendorModel.objects.get(slug=vendor_slug)

        category_mapping = ProductHelper.get_vendor_category_mapping()

        while df_len > df_index:
            sub_df = df[df_index : df_index + batch_size]
            product_objs = []
            for index, row in sub_df.iterrows():
                category = slugify(row.pop("category"))
                product_category = category_mapping[vendor_slug].get(category)
                if product_category is None:
                    product_category = category_mapping["other"]

                try:
                    product_price = convert_string_to_price(row["price"])
                except Exception:
                    product_price = None

                product_objs.append(
                    ProductModel(
                        vendor=vendor,
                        product_id=row["product_id"],
                        name=row["name"],
                        product_unit=row["product_unit"],
                        url=row["url"],
                        category=product_category,
                        price=product_price,
                    )
                )

            product_objs = bulk_create(model_class=ProductModel, objs=product_objs)
            print(f"{vendor}: {len(product_objs)} products created")
            product_image_objs = []
            for product, product_images in zip(product_objs, sub_df["images"]):
                product_images = product_images.split(";")
                for product_image in product_images:
                    product_image_objs.append(ProductImageModel(product=product, image=product_image))

            bulk_create(model_class=ProductImageModel, objs=product_image_objs)
            df_index += batch_size

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
            products = products.filter(category__in=include_category_slugs)

        if exclude_category_slugs:
            products = products.exclude(category__in=exclude_category_slugs)

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
                        concatenate_strings(product_ids, delimeter=";"),
                        concatenate_strings(vendor_products, delimeter=";"),
                        concatenate_strings(product_names, delimeter=";"),
                        concatenate_strings(product_urls, delimeter=";"),
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
                product_ids = row["product_ids"].split(";")
            else:
                vendor_products = row["vendor_products"].split(";")
                vendor_products = [
                    Q(vendor__slug=vendor_product.split("-")[0]) & Q(product_id=vendor_product.split("-", 1)[1])
                    for vendor_product in vendor_products
                ]
                q = reduce(or_, vendor_products)
                product_ids = list(ProductModel.objects.filter(q).values_list("id", flat=True))

            product_names = row["product_names"].split(";")
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
    def get_products(office: Union[OfficeModel, SmartID], product_ids: Optional[List[SmartID]] = None):
        if isinstance(office, OfficeModel):
            office_pk = office.id
        else:
            office_pk = office

        office_products = OfficeProductModel.objects.filter(product=OuterRef("pk"), office_id=office_pk)
        products = ProductModel.objects.filter(parent__isnull=True)
        if product_ids is not None:
            products = products.filter(id__in=product_ids)

        return (
            products.annotate(office_product_price=Subquery(office_products.values("price")[:1]))
            .annotate(
                product_price=Case(
                    When(office_product_price__isnull=False, then=F("office_product_price")),
                    When(price__isnull=False, then=F("price")),
                    default=Value(None),
                )
            )
            .order_by("product_price")
        )


class OfficeVendorHelper:
    @staticmethod
    def get_connected_vendor_ids(office: Union[int, str, OfficeModel]) -> List[str]:
        if not isinstance(office, OfficeModel):
            office = OfficeModel.objects.get(id=office)

        return office.connected_vendors.values_list("vendor_id", flat=True)
