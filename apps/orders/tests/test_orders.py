import datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.factories import (
    CompanyFactory,
    CompanyMemberFactory,
    OfficeFactory,
    OfficeVendorFactory,
    UserFactory,
    VendorFactory,
)
from apps.accounts.models import Office, User, Vendor
from apps.orders.factories import (
    OrderFactory,
    OrderProductFactory,
    ProductFactory,
    VendorOrderFactory,
)
from apps.orders.models import Product


class DashboardAPIPermissionTests(APITestCase):
    def setUp(self) -> None:
        self.company = CompanyFactory()
        self.company_office_1 = OfficeFactory(company=self.company)
        self.company_office_2 = OfficeFactory(company=self.company)
        self.company_admin = UserFactory(role=User.Role.ADMIN)
        self.company_user = UserFactory(role=User.Role.USER)

        self.firm = CompanyFactory()
        self.firm_office = OfficeFactory(company=self.firm)
        self.firm_admin = UserFactory(role=User.Role.ADMIN)
        self.firm_user = UserFactory(role=User.Role.USER)

        CompanyMemberFactory(company=self.company, user=self.company_admin, email=self.company_admin.email)
        CompanyMemberFactory(company=self.company, user=self.company_user, email=self.company_user.email)
        CompanyMemberFactory(company=self.firm, user=self.firm_admin, email=self.firm_admin.email)
        CompanyMemberFactory(company=self.firm, user=self.firm_user, email=self.firm_user.email)

    def _check_get_spend_permission(self, method, link):
        def make_call(user=None):
            self.client.force_authenticate(user)
            if method == "get":
                return self.client.get(link)
            elif method == "put":
                return self.client.put(link, {})
            elif method == "delete":
                return self.client.delete(link)
            elif method == "post":
                return self.client.post(link, {})

        response = make_call()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        expected_status = status.HTTP_200_OK if method == "get" else status.HTTP_405_METHOD_NOT_ALLOWED

        # company admin
        response = make_call(self.company_admin)
        self.assertEqual(response.status_code, expected_status)

        # company user
        response = make_call(self.company_user)
        self.assertEqual(response.status_code, expected_status)

        expected_status = status.HTTP_403_FORBIDDEN if method == "get" else status.HTTP_405_METHOD_NOT_ALLOWED
        # firm admin
        response = make_call(self.firm_admin)
        self.assertEqual(response.status_code, expected_status)

        # firm user
        response = make_call(self.firm_user)
        self.assertEqual(response.status_code, expected_status)

    def test_get_spend_company(self):
        link = reverse("company-spending", kwargs={"company_pk": self.company.id})
        self._check_get_spend_permission(method="get", link=f"{link}?by=vendor")
        self._check_get_spend_permission(method="get", link=f"{link}?by=month")

    def test_get_spend_office(self):
        link = reverse("office-spending", kwargs={"office_pk": self.company_office_1.id})
        self._check_get_spend_permission(method="get", link=f"{link}?by=vendor")
        self._check_get_spend_permission(method="get", link=f"{link}?by=month")


class CompanyOfficeSpendTests(APITestCase):
    @classmethod
    def _create_orders(cls, product: Product, office: Office, vendor: Vendor):
        for i in range(12):
            order_date = datetime.date.today() - relativedelta(months=i)
            order = OrderFactory(
                office=office,
                total_amount=product.price,
                # currency="USD",
                order_date=order_date,
                status="complete",
            )
            vendor_order = VendorOrderFactory(vendor=vendor, order=order, total_amount=product.price)
            OrderProductFactory(
                vendor_order=vendor_order,
                product=product,
                quantity=1,
                unit_price=product.price,
                status="complete",
            )

    @classmethod
    def setUpTestData(cls) -> None:
        cls.company = CompanyFactory()
        cls.vendor1_name = "HenrySchien"
        cls.vendor2_name = "Net 32"
        cls.vendor1 = VendorFactory(name=cls.vendor1_name, slug="henry_schein", url="https://www.henryschein.com/")
        cls.vendor2 = VendorFactory(name=cls.vendor2_name, slug="net_32", url="https://www.net32.com/")
        cls.office1 = OfficeFactory(company=cls.company)
        cls.office2 = OfficeFactory(company=cls.company)
        cls.admin = UserFactory(role=User.Role.ADMIN)
        CompanyMemberFactory(company=cls.company, user=cls.admin, email=cls.admin.email)

        cls.product1_price = Decimal("10.00")
        cls.product2_price = Decimal("100.00")
        cls.product1 = ProductFactory(
            vendor=cls.vendor1,
            price=cls.product1_price,
        )
        cls.product2 = ProductFactory(
            vendor=cls.vendor2,
            price=cls.product2_price,
        )
        cls.office1_vendor1 = OfficeVendorFactory(office=cls.office1, vendor=cls.vendor1)
        cls.office1_vendor2 = OfficeVendorFactory(office=cls.office2, vendor=cls.vendor2)

        # office1 vendors
        cls._create_orders(cls.product1, cls.office1, cls.vendor1)

        # office2 vendors
        cls._create_orders(cls.product2, cls.office2, cls.vendor2)

    def test_company_get_spending_by_vendor(self):
        link = reverse("company-spending", kwargs={"company_pk": self.company.id})
        link = f"{link}?by=vendor"
        self.client.force_authenticate(self.admin)
        response = self.client.get(link)
        result = sorted(response.data, key=lambda x: x["total_amount"])
        for res, price, name in zip(
            result, [self.product1_price, self.product2_price], [self.vendor1_name, self.vendor2_name]
        ):
            self.assertEqual(Decimal(res["total_amount"]), price * 12)
            self.assertEqual(res["vendor"]["name"], name)

    def test_company_get_spending_by_month(self):
        # TODO: there is instability in this test case
        link = reverse("company-spending", kwargs={"company_pk": self.company.id})
        link = f"{link}?by=month"
        self.client.force_authenticate(self.admin)
        response = self.client.get(link)
        result = response.data
        for res in result:
            self.assertEqual(Decimal(res["total_amount"]), self.product1_price + self.product2_price)

    def test_office_get_spending_by_vendor(self):
        self.client.force_authenticate(self.admin)
        link = reverse("office-spending", kwargs={"office_pk": self.office1.id})
        link = f"{link}?by=vendor"
        response = self.client.get(link)
        response_data = response.data[0]
        self.assertEqual(Decimal(response_data["total_amount"]), self.product1_price * 12)
        self.assertEqual(response_data["vendor"]["name"], self.vendor1_name)

        link = reverse("office-spending", kwargs={"office_pk": self.office2.id})
        link = f"{link}?by=vendor"
        response = self.client.get(link)
        response_data = response.data[0]
        self.assertEqual(Decimal(response_data["total_amount"]), self.product2_price * 12)
        self.assertEqual(response_data["vendor"]["name"], self.vendor2_name)

    def test_office_get_spending_by_month(self):
        self.client.force_authenticate(self.admin)
        link = reverse("office-spending", kwargs={"office_pk": self.office1.id})
        link = f"{link}?by=month"
        response = self.client.get(link)
        for res in response.data:
            self.assertEqual(Decimal(res["total_amount"]), self.product1_price)

        link = reverse("office-spending", kwargs={"office_pk": self.office2.id})
        link = f"{link}?by=month"
        response = self.client.get(link)
        for res in response.data:
            self.assertEqual(Decimal(res["total_amount"]), self.product2_price)
