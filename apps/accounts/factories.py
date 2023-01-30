import factory
from factory.django import DjangoModelFactory

from . import models as m


class UserFactory(DjangoModelFactory):
    class Meta:
        model = m.User

    username = factory.LazyAttribute(lambda o: o.email)
    email = factory.Sequence(lambda n: f"{n}@example.com")


class CompanyFactory(DjangoModelFactory):
    class Meta:
        model = m.Company


class VendorFactory(DjangoModelFactory):
    class Meta:
        model = m.Vendor


class OfficeFactory(DjangoModelFactory):
    class Meta:
        model = m.Office

    company = factory.SubFactory(CompanyFactory)


class OfficeVendorFactory(DjangoModelFactory):
    class Meta:
        model = m.OfficeVendor

    vendor = factory.SubFactory(VendorFactory)
    office = factory.SubFactory(OfficeFactory)


class CompanyMemberFactory(DjangoModelFactory):
    class Meta:
        model = m.CompanyMember

    company = factory.SubFactory(CompanyFactory)
    user = factory.SubFactory(UserFactory)
    office = factory.LazyAttribute(lambda o: OfficeFactory(company=o.company))
