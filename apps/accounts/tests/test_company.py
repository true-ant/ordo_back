from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts import factories as f
from apps.accounts.models import User


class CompanyTests(APITestCase):
    def setUp(self) -> None:
        self.company = f.CompanyFactory()
        self.office1 = f.OfficeFactory(company=self.company)
        self.office2 = f.OfficeFactory(company=self.company)
        self.admin = f.UserFactory(role=User.Role.ADMIN)
        self.user = f.UserFactory(role=User.Role.USER)

        f.CompanyMemberFactory(company=self.company, user=self.admin, email=self.admin.email)
        f.CompanyMemberFactory(company=self.company, user=self.user, email=self.user.email)

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

        # admin
        response = make_call(self.admin)
        if method == "put":
            expected_status = status.HTTP_200_OK
        elif method == "post":
            expected_status = status.HTTP_201_CREATED
        else:
            expected_status = status.HTTP_204_NO_CONTENT
        self.assertEqual(response.status_code, expected_status)

        # user
        response = make_call(self.user)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def _check_view_permission(self, *, method, link):
        """check get, list permission"""
        pass
        # # unauthorized user
        # response = self.client.get(link)
        # self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # # admin
        # self.client.force_authenticate(self.admin)
        # response = self.client.get(link)
        # self.assertEqual(response.status_code, status.HTTP_200_OK)

        # # user
        # self.client.force_authenticate(self.user)
        # response = self.client.get(link)
        # self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_company_get_permission(self):
        pass

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
        pass

    def test_office_create_permission(self):
        data = {"name": "updated office name"}
        self._check_edit_permission(
            method="put",
            link=reverse("offices-detail", kwargs={"company_pk": self.company.id, "pk": self.office1.id}),
            data=data,
        )

    def test_office_update_permission(self):
        data = {"name": "updated office name"}
        self._check_edit_permission(
            method="put",
            link=reverse("offices-detail", kwargs={"company_pk": self.company.id, "pk": self.office1.id}),
            data=data,
        )

    def test_office_delete_permission(self):
        self._check_edit_permission(
            method="delete",
            link=reverse("offices-detail", kwargs={"company_pk": self.company.id, "pk": self.office1.id}),
        )
