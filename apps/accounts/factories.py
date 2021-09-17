from factory import Sequence
from factory.django import DjangoModelFactory

from . import models as m


class UserFactory(DjangoModelFactory):
    class Meta:
        model = m.User

    username = Sequence(lambda n: f"test{n}")
    email = Sequence(lambda n: f"{n}@example.com")


class CompanyFactory(DjangoModelFactory):
    class Meta:
        model = m.Company


class VendorFactory(DjangoModelFactory):
    class Meta:
        model = m.Vendor


class OfficeFactory(DjangoModelFactory):
    class Meta:
        model = m.Office

    company = CompanyFactory()


class OfficeVendorFactory(DjangoModelFactory):
    class Meta:
        model = m.OfficeVendor

    vendor = VendorFactory()
    office = OfficeFactory()


class CompanyMemberFactory(DjangoModelFactory):
    class Meta:
        model = m.CompanyMember

    # company = SubFactory(CompanyFactory)
    # user = SubFactory(UserFactory)
    # office = SubFactory(OfficeFactory)
