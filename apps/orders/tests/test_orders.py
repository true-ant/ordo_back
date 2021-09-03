from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.factories import (
    CompanyFactory,
    CompanyMemberFactory,
    OfficeFactory,
    UserFactory,
)
from apps.accounts.models import User


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
