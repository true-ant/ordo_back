import csv
import uuid
from itertools import groupby

from django.core.management import BaseCommand

from apps.audit.models import ProductParentHistory
from apps.orders.models import Product


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
                if int(row["keep"]) == 1:
                    continue
                yield row

    def handle(self, *args, **options):
        # ID of this execution id, used for rollback
        operation_id = uuid.uuid4()
        csvfile = options["csvfile"]
        history = []
        for parent_id, items in groupby(self.items(csvfile), key=lambda x: x["parent_id"]):
            parent_items = list(items)
            for g2, subgroup in groupby(parent_items, key=lambda x: x["subgroup_id"]):
                subgroup_items = list(subgroup)
                name = subgroup_items[0]["name"]
                mnum = subgroup_items[0]["manufacturer_number"]
                # Create new parent category, set name to first child product's name
                parent = Product.objects.create(name=name, manufacturer_number=mnum, is_special_offer=False)
                child_ids = [int(e["id"]) for e in subgroup_items]
                # Put all child objects under newly created parent
                Product.objects.filter(id__in=child_ids).update(parent=parent)
                # Record parent change information
                for product_id in child_ids:
                    history.append(
                        ProductParentHistory(
                            operation_id=operation_id,
                            product=product_id,
                            old_parent=int(parent_id),
                            new_parent=parent.id,
                        )
                    )
        ProductParentHistory.objects.bulk_create(history)
        print(str(operation_id), file=self.stdout)
