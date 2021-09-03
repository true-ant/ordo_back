from factory import Sequence
from factory.django import DjangoModelFactory

from apps.accounts.factories import OfficeVendorFactory

from . import models as m


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = m.Product


class OrderFactory(DjangoModelFactory):
    class Meta:
        model = m.Order

    office_vendor = OfficeVendorFactory()
    order_id = Sequence(lambda n: f"order_{n}")


class OrderProductFactory(DjangoModelFactory):
    class Meta:
        model = m.Vendor
