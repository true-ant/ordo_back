from faker import Faker
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APIClient, APITestCase

from apps.accounts.factories import (
    CompanyFactory,
    CompanyMemberFactory,
    OfficeFactory,
    UserFactory,
)
from apps.accounts.models import User

fake = Faker()


class TestUserSignUpTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = CompanyFactory()
        cls.office = OfficeFactory(company=cls.company)
        cls.company_member_user = UserFactory()
        cls.company_member = CompanyMemberFactory(company=cls.company, office=cls.office, user=cls.company_member_user)
        cls.api_client = APIClient()
        cls.api_client.force_authenticate(cls.company_member_user)

    def test_member_create(self):
        resp = self.api_client.post(
            reverse("members-list", kwargs={"company_pk": self.company.pk}),
            data={"office": self.office.pk, "role": User.Role.USER, "email": fake.email()},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
