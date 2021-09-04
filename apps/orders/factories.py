from factory import Sequence
from factory.django import DjangoModelFactory

from apps.accounts.factories import OfficeFactory, VendorFactory

from . import models as m


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = m.Product

    vendor = VendorFactory()
    product_id = Sequence(lambda n: f"test{n}")
    name = Sequence(lambda n: f"Product {n}")


class OrderFactory(DjangoModelFactory):
    class Meta:
        model = m.Order

    office = OfficeFactory()
    vendor = VendorFactory()
    order_id = Sequence(lambda n: f"order_{n}")


class OrderProductFactory(DjangoModelFactory):
    class Meta:
        model = m.OrderProduct
