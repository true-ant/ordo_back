import datetime
import decimal
import math
from typing import Literal

from faker import Faker
from pydantic import BaseModel, root_validator
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APIClient, APITestCase

from apps.accounts.factories import (
    CompanyFactory,
    CompanyMemberFactory,
    OfficeFactory,
    UserFactory,
    OfficeBudgetFactory,
)
from apps.accounts.models import User
from apps.accounts.tests.factories import AdminUserFactory

fake = Faker()


class RemainingBudget(BaseModel):
    dental: float
    office: float


BudgetType = Literal["production", "collection"]

class BudgetOutput(BaseModel):
    id: int
    office: int
    remaining_budget: RemainingBudget
    dental_budget_type: BudgetType
    dental_total_budget: decimal.Decimal
    dental_percentage: decimal.Decimal
    dental_budget: decimal.Decimal
    dental_spend: decimal.Decimal
    office_budget_type: BudgetType
    office_total_budget: decimal.Decimal
    office_percentage: decimal.Decimal
    office_budget: decimal.Decimal
    office_spend: decimal.Decimal
    adjusted_production: decimal.Decimal
    collection: decimal.Decimal
    miscellaneous_spend: decimal.Decimal
    month: datetime.date

    @root_validator()
    def check_remaning(cls, values):
        rb: RemainingBudget = values["remaining_budget"]
        assert math.isclose(rb.dental, values["dental_budget"] - values["dental_spend"])
        assert math.isclose(rb.office, values["office_budget"] - values["office_spend"])
        return values


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





class ProductManagementTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = CompanyFactory()
        cls.office = OfficeFactory(company=cls.company)
        cls.company_member = CompanyMemberFactory(company=cls.company, office=cls.office)
        cls.office_budget = OfficeBudgetFactory(office=cls.office)
        cls.admin = AdminUserFactory()
        cls.api_client = APIClient()
        cls.api_client.force_authenticate(cls.admin)

    def test_company_member(self):
        url = reverse("members-list", kwargs={"company_pk": self.company.pk})
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        member_data = data["data"][0]
        office_data = member_data["office"]
        budget = BudgetOutput(**office_data["budget"])
        assert budget
