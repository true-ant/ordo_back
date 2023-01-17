import factory
from factory.django import DjangoModelFactory

from apps.accounts.factories import OfficeFactory, VendorFactory

from . import models as m


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = m.Product

    vendor = factory.SubFactory(VendorFactory)
    product_id = factory.Sequence(lambda n: f"test{n}")
    name = factory.Sequence(lambda n: f"Product {n}")


class OrderFactory(DjangoModelFactory):
    class Meta:
        model = m.Order

    office = factory.SubFactory(OfficeFactory)
    # vendor = factory.SubFactory(VendorFactory)
    # order_id = factory.Sequence(lambda n: f"order_{n}")


class OrderProductFactory(DjangoModelFactory):
    class Meta:
        model = m.VendorOrderProduct


class VendorOrderFactory(DjangoModelFactory):
    class Meta:
        model = m.VendorOrder

    vendor = factory.SubFactory(VendorFactory)
    order = factory.SubFactory(OrderFactory)
    total_amount = 1
    order_date = factory.Faker("date")
