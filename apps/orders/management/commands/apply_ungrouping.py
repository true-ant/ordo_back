import csv
import uuid
from collections import defaultdict
from itertools import groupby
from typing import NamedTuple

from django.core.management import BaseCommand

from apps.audit.models import ProductParentHistory
from apps.orders.models import Product


class MappingResults(NamedTuple):
    db_products: dict[int, Product]
    parent_to_children: dict[int, set[Product]]
    subgroup_to_product_ids: dict[int, set[int]]

    def find_parent_subgroup(self, parent_name):
        for subgroup_id, subgroup_product_ids in self.subgroup_to_product_ids.items():
            subgroup_product_names = {self.db_products[product_id].name for product_id in subgroup_product_ids}
            if parent_name in subgroup_product_names:
                return subgroup_id

    def find_parent_to_subgroup_matchings(self):
        parent2subgroup = {}
        all_found = True
        # Find matching parents in existing subgroups
        for parent_id, product_ids in self.parent_to_children.items():
            parent_name = self.db_products[parent_id].name

            # See which subgroup contains name which is equal to parent.name
            subgroup_id = self.find_parent_subgroup(parent_name)
            if subgroup_id:
                parent2subgroup[parent_id] = subgroup_id
            else:
                all_found = False
        return parent2subgroup, all_found


class Command(BaseCommand):
    """
    Given analysis script split existing product groups into
    multiple groups and record activity to make rollback
    possible
    """

    def add_arguments(self, parser):
        parser.add_argument("csvfile")

    def items(self, csvfile):
        """
        Go through analysis csv file and skip rows having keep equal to 1
        """
        with open(csvfile) as f:
            reader = csv.DictReader(f, dialect="excel-tab")
            for row in reader:
                yield row

    def calculate_parent_mappings(self, manufacturer_number, csv_items) -> MappingResults:
        parent_to_children = defaultdict(set)
        subgroup_to_product_ids = defaultdict(set)

        db_products: dict[int, Product] = {
            p.id: p for p in Product.objects.filter(manufacturer_number=manufacturer_number).exclude(parent_id=None)
        }

        csv_product_ids = {int(e["id"]) for e in csv_items}
        assert csv_product_ids == {k for k, v in db_products.items() if v.parent_id}

        # Creating dict parent_id -> list[Product]
        for product in db_products.values():
            if product.parent_id:
                parent_to_children[product.parent_id].add(product)

        # Parent products
        for parent_product in Product.objects.filter(id__in={p.parent_id for p in db_products.values()}):
            db_products[parent_product.id] = parent_product

        # Creating dict subgroup_id -> list[product_id]
        for e in csv_items:
            subgroup_to_product_ids[int(e["subgroup_id"])].add(int(e["id"]))
        return MappingResults(db_products, parent_to_children, subgroup_to_product_ids)

    def handle(self, *args, **options):
        # ID of this execution id, used for rollback
        operation_id = uuid.uuid4()
        csvfile = options["csvfile"]
        history = []
        all_items = list(self.items(csvfile))
        all_items.sort(key=lambda x: (x["manufacturer_number"], x["subgroup_id"]))

        for manufacturer_number, items in groupby(all_items, key=lambda x: x["manufacturer_number"]):
            items = list(items)
            mr = self.calculate_parent_mappings(manufacturer_number, items)
            parent2subgroup, all_found = mr.find_parent_to_subgroup_matchings()
            if not all_found:
                continue

            # Creating new parent products
            existing_subgroups = set(parent2subgroup.values())
            subgroups_to_create = set(mr.subgroup_to_product_ids.keys()) - existing_subgroups

            for subgroup_id in subgroups_to_create:
                # Get first item from set
                subgroup_items = iter(mr.subgroup_to_product_ids[subgroup_id])
                subgroup_item = next(subgroup_items)
                name = mr.db_products[subgroup_item].name
                parent_product = Product.objects.create(
                    name=name, manufacturer_number=manufacturer_number, is_special_offer=False
                )
                parent2subgroup[parent_product.id] = subgroup_id
                mr.parent_to_children[parent_product.id] = set()

            for parent_id, products in mr.parent_to_children.items():
                subgroup_id = parent2subgroup[parent_id]
                subgroup_product_ids = mr.subgroup_to_product_ids[subgroup_id]
                product_ids = {p.id for p in products}
                to_add = subgroup_product_ids - product_ids
                to_remove = product_ids - subgroup_product_ids
                for product_id in to_add:
                    product = mr.db_products[product_id]
                    old_parent = product.parent_id
                    product.parent_id = parent_id
                    product.save(update_fields=["parent_id"])
                    history.append(
                        ProductParentHistory(
                            operation_id=operation_id,
                            product=product_id,
                            old_parent=old_parent,
                            new_parent=parent_id,
                        )
                    )
                for product_id in to_remove:
                    product = mr.db_products[product_id]
                    old_parent = product.parent_id
                    product.parent_id = None
                    product.save(update_fields=["parent_id"])
                    history.append(
                        ProductParentHistory(
                            operation_id=operation_id,
                            product=product_id,
                            old_parent=old_parent,
                            new_parent=None,
                        )
                    )
        ProductParentHistory.objects.bulk_create(history)
        print(str(operation_id), file=self.stdout)
