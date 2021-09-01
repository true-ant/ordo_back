from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts import factories as f
from apps.accounts.models import User


class CompanyTests(APITestCase):
    def setUp(self) -> None:
        self.company = f.CompanyFactory()
        self.company_office_1 = f.OfficeFactory(company=self.company)
        self.company_office_2 = f.OfficeFactory(company=self.company)
        self.company_admin = f.UserFactory(role=User.Role.ADMIN)
        self.company_user = f.UserFactory(role=User.Role.USER)

        self.firm = f.CompanyFactory()
        self.firm_office = f.OfficeFactory(company=self.firm)
        self.firm_admin = f.UserFactory(role=User.Role.ADMIN)
        self.firm_user = f.UserFactory(role=User.Role.USER)

        f.CompanyMemberFactory(company=self.company, user=self.company_admin, email=self.company_admin.email)
        f.CompanyMemberFactory(company=self.company, user=self.company_user, email=self.company_user.email)
        f.CompanyMemberFactory(company=self.firm, user=self.firm_admin, email=self.firm_admin.email)
        f.CompanyMemberFactory(company=self.firm, user=self.firm_user, email=self.firm_user.email)

    def _check_edit_permission(self, *, method, link, data=None):
        """check create, update, delete permission"""

        def make_call(user=None):
            if user:
                self.client.force_authenticate(user)
            if method == "put":
                return self.client.put(link, data)
            elif method == "delete":
                return self.client.delete(link)
            elif method == "post":
                return self.client.post(link, data)

        # unauthorized user
        response = make_call()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # company admin
        response = make_call(self.company_admin)
        if method == "put":
            expected_status = status.HTTP_200_OK
        elif method == "post":
            expected_status = status.HTTP_201_CREATED
        else:
            expected_status = status.HTTP_204_NO_CONTENT
        self.assertEqual(response.status_code, expected_status)

        # company user
        response = make_call(self.company_user)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # firm admin
        response = make_call(self.firm_admin)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = make_call(self.firm_user)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def _check_view_permission(self, *, link):
        """check get, list permission"""
        pass
        # unauthorized user
        response = self.client.get(link)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # company admin
        self.client.force_authenticate(self.company_admin)
        response = self.client.get(link)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # company user
        self.client.force_authenticate(self.company_user)
        response = self.client.get(link)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # firm admin
        self.client.force_authenticate(self.firm_admin)
        response = self.client.get(link)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # firm user
        self.client.force_authenticate(self.firm_admin)
        response = self.client.get(link)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_company_get_permission(self):
        self._check_view_permission(
            link=reverse("companies-detail", kwargs={"pk": self.company.id}),
        )

    def test_company_create_permission(self):
        pass

    def test_company_update_permission(self):
        data = {"name": "updated company name"}
        self._check_edit_permission(
            method="put",
            link=reverse("companies-detail", kwargs={"pk": self.company.id}),
            data=data,
        )

    def test_company_delete_permission(self):
        self._check_edit_permission(
            method="delete",
            link=reverse("companies-detail", kwargs={"pk": self.company.id}),
        )

    def test_office_get_permission(self):
        self._check_view_permission(
            link=reverse("offices-detail", kwargs={"company_pk": self.company.id, "pk": self.company_office_1.id}),
        )

    def test_office_create_permission(self):
        data = {"name": "updated office name"}
        self._check_edit_permission(
            method="put",
            link=reverse("offices-detail", kwargs={"company_pk": self.company.id, "pk": self.company_office_1.id}),
            data=data,
        )

    def test_office_update_permission(self):
        data = {"name": "updated office name"}
        self._check_edit_permission(
            method="put",
            link=reverse("offices-detail", kwargs={"company_pk": self.company.id, "pk": self.company_office_1.id}),
            data=data,
        )

    def test_office_delete_permission(self):
        self._check_edit_permission(
            method="delete",
            link=reverse("offices-detail", kwargs={"company_pk": self.company.id, "pk": self.company_office_1.id}),
        )