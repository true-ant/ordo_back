import csv
import os.path
import random
import tempfile
from io import StringIO

from django.core.management import call_command
from faker import Faker

from apps.audit.models import ProductParentHistory
from apps.orders.factories import ProductFactory
from apps.orders.models import Product

fake = Faker()

MODEL_FIELDS = ("parent_id", "id", "vendor_id", "manufacturer_number", "name")
FIELD_NAMES = (*MODEL_FIELDS, "subgroup_id", "keep")


def make_csv(dir_path, data):
    fname = os.path.join(dir_path, "output.tsv")
    with open(fname, "w") as f:
        writer = csv.DictWriter(
            f,
            dialect="excel-tab",
            fieldnames=FIELD_NAMES,
        )
        writer.writeheader()
        writer.writerows(data)
    return fname


def make_products():
    parent_product = ProductFactory(name=fake.pystr(), parent=None)
    groups = [ProductFactory.create_batch(3, parent=parent_product) for _ in range(3)]
    return parent_product, groups


def generate_data(groups):
    records = ((1, groups[:1]), (0, groups[1:]))
    data = []
    for keep, groups in records:
        for group in groups:
            subgroup_id = random.randint(1, 1000)
            for product in group:
                data.append(
                    {
                        "keep": keep,
                        "subgroup_id": subgroup_id,
                        **{fname: getattr(product, fname) for fname in MODEL_FIELDS},
                    }
                )
    return data


def test_ungroup_rollback(db):
    td = tempfile.mkdtemp()
    parent, groups = make_products()
    data = generate_data(groups)
    csv = make_csv(td, data)
    out = StringIO()
    call_command("apply_ungrouping", (csv,), stdout=out)
    operation_id = out.getvalue().strip()
    assert len(set(Product.objects.filter(parent_id__isnull=False).values_list("parent_id", flat=True))) == 3
    call_command("rollback_grouping_operation", (operation_id,))
    assert len(set(Product.objects.filter(parent_id__isnull=False).values_list("parent_id", flat=True))) == 1
    assert ProductParentHistory.objects.count() == 0
