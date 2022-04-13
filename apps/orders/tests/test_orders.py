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
from apps.accounts.models import User
from apps.orders.factories import OrderFactory, OrderProductFactory, ProductFactory


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
        link = reverse("company-spending", kwargs={"company_id": self.company.id})
        self._check_get_spend_permission(method="get", link=f"{link}?by=vendor")
        self._check_get_spend_permission(method="get", link=f"{link}?by=month")

    def test_get_spend_office(self):
        link = reverse("office-spending", kwargs={"office_id": self.company_office_1.id})
        self._check_get_spend_permission(method="get", link=f"{link}?by=vendor")
        self._check_get_spend_permission(method="get", link=f"{link}?by=month")


class CompanyOfficeSpendTests(APITestCase):
    def _create_orders(self, product: ProductFactory, office: OfficeFactory, vendor: VendorFactory):
        for i in range(12):
            order_date = datetime.date.today() - relativedelta(months=i)
            order = OrderFactory(
                office=office,
                vendor=vendor,
                total_amount=product.price,
                currency="USD",
                order_date=order_date,
                status="complete",
            )
            OrderProductFactory(
                order=order,
                product=product,
                quantity=1,
                unit_price=product.price,
                status="complete",
            )

    def setUp(self) -> None:
        self.company = CompanyFactory()
        self.vendor1_name = "HenrySchien"
        self.vendor2_name = "Net 32"
        self.vendor1 = VendorFactory(name=self.vendor1_name, slug="henry_schein", url="https://www.henryschein.com/")
        self.vendor2 = VendorFactory(name=self.vendor2_name, slug="net_32", url="https://www.net32.com/")
        self.office1 = OfficeFactory(company=self.company)
        self.office2 = OfficeFactory(company=self.company)
        self.admin = UserFactory(role=User.Role.ADMIN)
        CompanyMemberFactory(company=self.company, user=self.admin, email=self.admin.email)

        self.product1_price = Decimal("10.00")
        self.product2_price = Decimal("100.00")
        self.product1 = ProductFactory(
            vendor=self.vendor1,
            price=self.product1_price,
        )
        self.product2 = ProductFactory(
            vendor=self.vendor2,
            price=self.product2_price,
        )
        self.office1_vendor1 = OfficeVendorFactory(company=self.office1, vendor=self.vendor1)
        self.office1_vendor2 = OfficeVendorFactory(company=self.office1, vendor=self.vendor2)

        # office1 vendors
        self._create_orders(self.product1, self.office1, self.vendor1)

        # office2 vendors
        self._create_orders(self.product2, self.office2, self.vendor2)

    def test_company_get_spending_by_vendor(self):
        link = reverse("company-spending", kwargs={"company_id": self.company.id})
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
        link = reverse("company-spending", kwargs={"company_id": self.company.id})
        link = f"{link}?by=month"
        self.client.force_authenticate(self.admin)
        response = self.client.get(link)
        result = response.data
        for res in result:
            self.assertEqual(Decimal(res["total_amount"]), self.product1_price + self.product2_price)

    def test_office_get_spending_by_vendor(self):
        self.client.force_authenticate(self.admin)
        link = reverse("office-spending", kwargs={"office_id": self.office1.id})
        link = f"{link}?by=vendor"
        response = self.client.get(link)
        response_data = response.data[0]
        self.assertEqual(Decimal(response_data["total_amount"]), self.product1_price * 12)
        self.assertEqual(response_data["vendor"]["name"], self.vendor1_name)

        link = reverse("office-spending", kwargs={"office_id": self.office2.id})
        link = f"{link}?by=vendor"
        response = self.client.get(link)
        response_data = response.data[0]
        self.assertEqual(Decimal(response_data["total_amount"]), self.product2_price * 12)
        self.assertEqual(response_data["vendor"]["name"], self.vendor2_name)

    def test_office_get_spending_by_month(self):
        self.client.force_authenticate(self.admin)
        link = reverse("office-spending", kwargs={"office_id": self.office1.id})
        link = f"{link}?by=month"
        response = self.client.get(link)
        for res in response.data:
            self.assertEqual(Decimal(res["total_amount"]), self.product1_price)

        link = reverse("office-spending", kwargs={"office_id": self.office2.id})
        link = f"{link}?by=month"
        response = self.client.get(link)
        for res in response.data:
            self.assertEqual(Decimal(res["total_amount"]), self.product2_price)
