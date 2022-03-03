import itertools
from typing import List, Optional, Union

from django.db.models import Model
from django.db.models.query import QuerySet

from apps.common.utils import (
    bulk_update,
    find_numeric_values_from_string,
    find_words_from_string,
)
from apps.orders.models import Product, ProductCategory

ProductID = Union[int, str]
ProductIDs = List[ProductID]


class ProductService:
    @staticmethod
    def group_products(product_ids: Optional[ProductID] = None):
        """Group products"""

        # we don't have to group products that are already grouped. so select ungrouped products
        products = Product.objects.filter(parent__isnull=True)
        if product_ids:
            products = products.filter(id__in=product_ids)

        vendor_slugs = products.order_by("vendor").values_list("vendor__slug", flat=True).distinct()
        if len(vendor_slugs) <= 1:
            # if the products are from one vendor, don't need to proceed further
            return None

        similar_product_ids_list: List[ProductIDs] = []

        # get the list of similar product ids by product category
        product_categories = ProductCategory.objects.all()
        for product_category in product_categories:
            similar_product_ids_list.extend(ProductService.group_products_by_category(products, product_category))

        updated_products = []
        for similar_product_ids in similar_product_ids_list:
            similar_products = products.filter(id__in=similar_product_ids)
            parent_products = similar_products.filter(child__isnull=False)

            if parent_products:
                parent_product = parent_products.first()
                for similar_product in similar_products.exclude(id=parent_product.id):
                    similar_product.parent = parent_product
                for other_parent_product in parent_products[1:]:
                    for child_product in other_parent_product.children.all():
                        child_product.parent = parent_product

                updated_products.extend(similar_products[1:])
            else:
                parent_product = similar_products[0]
                for similar_product in similar_products[1:]:
                    similar_product.parent = parent_product
                updated_products.extend(similar_products[1:])

        bulk_update(Product, updated_products, fields=["parent"])

    @staticmethod
    def group_products_by_category(products: QuerySet, product_category: ProductCategory) -> List[ProductIDs]:
        """
        Return the list of a group of product ids.
        Each element from the list is a list of product id, those products are very similar
        """
        if product_category.slug.lower() != "other":
            vendor_slugs = product_category.vendor_categories.keys()
            if len(vendor_slugs) <= 1:
                return []
        else:
            vendor_slugs = products.order_by("vendor").values_list("vendor__slug", flat=True).distinct()

        vendor_products = []
        for vendor_slug in vendor_slugs:
            vendor_products_names = products.filter(vendor__slug=vendor_slug, category=product_category).values(
                "id", "name"
            )
            if vendor_products_names:
                vendor_products.append(vendor_products_names)

        if len(vendor_products) <= 1:
            return []

        return ProductService.group_products_by_name(vendor_products)

    @staticmethod
    def group_products_by_name(product_names_list) -> List[ProductIDs]:
        n_similarity = 2
        threshold = 0.6
        vendors_count = len(product_names_list)
        similar_products_candidates = []

        while n_similarity <= vendors_count:
            products_combinations = itertools.combinations(product_names_list, n_similarity)
            for products_combination in products_combinations:
                for vendor_products in itertools.product(*products_combination):
                    vendor_product_ids = [vendor_product["id"] for vendor_product in vendor_products]
                    vendor_product_names = [vendor_product["name"] for vendor_product in vendor_products]
                    print(f"calculating {', '.join(vendor_product_names)}")
                    # when finding more than 3-length similar products we need to check that
                    # sub-set of products belongs to well-matched pairs.
                    # If well-matched set contains subset of products it is worth to check similarity
                    # otherwise, we don't have to calculate it.
                    if n_similarity > 2:
                        contains_well_matching_pair = any(
                            [
                                set(similar_products_candidate[1:]).issubset(tuple(vendor_product_ids))
                                for similar_products_candidate in similar_products_candidates
                            ]
                        )
                        if not contains_well_matching_pair:
                            continue

                    similarity = ProductService.get_similarity(*vendor_product_names)
                    if similarity > threshold:
                        similar_products_candidates.append((f"{similarity:.2f}", *vendor_product_ids))

            n_similarity += 1

        similar_product_ids_list: List[ProductIDs] = []
        matched_products = set()
        similar_products_candidates = sorted(similar_products_candidates, key=lambda x: (len(x), x[0]), reverse=True)
        for similar_products_candidate in similar_products_candidates:
            similar_products = set(similar_products_candidate[1:])
            if similar_products & matched_products:
                continue
            matched_products.update(similar_products)
            similar_product_ids_list.append(list(similar_products))

        return similar_product_ids_list

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
