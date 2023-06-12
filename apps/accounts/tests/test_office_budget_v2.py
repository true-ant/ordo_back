import datetime
import decimal
from typing import List, Literal
from unittest.mock import patch

from faker import Faker
from pydantic import BaseModel, validator
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.accounts.factories import (
    BudgetFactory,
    CompanyFactory,
    CompanyMemberFactory,
    OfficeFactory,
    UserFactory,
)
from apps.accounts.models import BasisType, CompanyMember, User
from apps.accounts.tests.utils import VersionedAPIClient, last_year_months
from apps.common.month import Month

fake = Faker()


class RemainingBudget(BaseModel):
    dental: float
    office: float


BudgetType = Literal["production", "collection"]


class SubaccountOutput(BaseModel):
    slug: str
    spend: decimal.Decimal
    percentage: decimal.Decimal


class ChartBudget(BaseModel):
    month: Month
    dental_budget: decimal.Decimal
    dental_spend: decimal.Decimal
    office_budget: decimal.Decimal
    office_spend: decimal.Decimal

    @validator("month", pre=True)
    def normalize_month(cls, value):
        return Month.from_string(value)

    class Config:
        arbitrary_types_allowed = True


class ChartBudgetV2(BaseModel):
    month: Month
    subaccounts: List[SubaccountOutput]

    @validator("month", pre=True)
    def normalize_month(cls, value):
        return Month.from_string(value)

    class Config:
        arbitrary_types_allowed = True


class BudgetOutputV2(BaseModel):
    id: int
    office: int
    basis: int
    month: datetime.date
    adjusted_production: decimal.Decimal
    collection: decimal.Decimal
    subaccounts: List[SubaccountOutput]


class SingleOfficeBudgetV2TestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = CompanyFactory()
        cls.office = OfficeFactory(company=cls.company)
        cls.company_member_user = UserFactory()
        cls.company_member = CompanyMemberFactory(company=cls.company, office=cls.office, user=cls.company_member_user)
        cls.office_budget = BudgetFactory(office=cls.office)
        cls.api_client = VersionedAPIClient(version="2.0")
        cls.api_client.force_authenticate(cls.company_member_user)

    def test_company_member(self):
        url = reverse("members-list", kwargs={"company_pk": self.company.pk})
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        member_data = data["data"][0]
        office_data = member_data["office"]
        budget = BudgetOutputV2(**office_data["budget"])
        assert budget

    def test_company(self):
        url = reverse("companies-detail", kwargs={"pk": self.company.pk})
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        office_data = data["data"]["offices"][0]
        budget = BudgetOutputV2(**office_data["budget"])
        assert budget

    def test_budgets_list(self):
        url = reverse("budgets-list", kwargs={"company_pk": self.company.pk, "office_pk": self.office.pk})
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        budget_data = data["data"][0]
        budget = BudgetOutputV2(**budget_data)
        assert budget

    def test_budgets_detail(self):
        url = reverse(
            "budgets-detail",
            kwargs={"company_pk": self.company.pk, "office_pk": self.office.pk, "pk": self.office_budget.pk},
        )
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        budget_data = data["data"]
        budget = BudgetOutputV2(**budget_data)
        assert budget

    def test_update_budget(self):
        url = reverse(
            "budgets-detail",
            kwargs={"company_pk": self.company.pk, "office_pk": self.office.pk, "pk": self.office_budget.pk},
        )
        update_data = {
            "basis": BasisType.COLLECTION,
            "collection": decimal.Decimal("152319.74"),
            "subaccounts": [
                {
                    "slug": "dental",
                    "percentage": decimal.Decimal("4.5"),
                },
                {
                    "slug": "office",
                    "percentage": decimal.Decimal("0.9"),
                },
                {"slug": "misc", "percentage": decimal.Decimal("100")},
            ],
        }
        self.api_client.put(url, data=update_data, format="json")
        url = reverse(
            "budgets-detail",
            kwargs={"company_pk": self.company.pk, "office_pk": self.office.pk, "pk": self.office_budget.pk},
        )

        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        budget_data = data["data"]
        budget = BudgetOutputV2(**budget_data)
        for field_name, value in update_data.items():
            if field_name == "subaccounts":
                sdata = {o.slug: o for o in budget.subaccounts}
                udata = {o["slug"]: o for o in update_data["subaccounts"]}
                assert sdata.keys() == udata.keys()
                for k in sdata.keys():
                    if k == "misc":
                        continue
                    else:
                        assert sdata[k].percentage == udata[k]["percentage"]
            else:
                assert getattr(budget, field_name) == update_data[field_name]

    def test_get_current_month_budget(self):
        url = reverse(
            "budgets-get-current-month-budget", kwargs={"company_pk": self.company.pk, "office_pk": self.office.pk}
        )
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        budget_data = data["data"]
        budget = BudgetOutputV2(**budget_data)
        assert budget

    def test_user_self(self):
        url = reverse("users-detail", kwargs={"pk": "me"})
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        user_data = data["data"]
        company_data = user_data["company"]
        office_data = company_data["offices"][0]
        budget_data = office_data["budget"]
        budget = BudgetOutputV2(**budget_data)
        assert budget


class ChartDataTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = CompanyFactory()
        cls.office = OfficeFactory(company=cls.company)
        cls.company_member_user = UserFactory()
        cls.company_member = CompanyMemberFactory(company=cls.company, office=cls.office, user=cls.company_member_user)
        for month in last_year_months():
            cls.office_budget = BudgetFactory(office=cls.office, month=month)
        cls.api_client = VersionedAPIClient(version="2.0")
        cls.api_client.force_authenticate(cls.company_member_user)

    def test_chart_data(self):
        url = reverse("budgets-get-chart-data", kwargs={"company_pk": self.company.pk, "office_pk": self.office.pk})
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        for budget_data in data["data"]:
            budget = ChartBudgetV2(**budget_data)
            assert budget


class TestUserSignUpTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = CompanyFactory()
        cls.office = OfficeFactory(company=cls.company)
        cls.company_member = CompanyMemberFactory(
            company=cls.company,
            office=cls.office,
            invite_status=CompanyMember.InviteStatus.INVITE_SENT,
            user=None,
        )
        for month in last_year_months():
            cls.office_budget = BudgetFactory(office=cls.office, month=month)
        cls.api_client = VersionedAPIClient(version="2.0")

    def test_user_signup_with_token(self):
        url = reverse("signup")
        first_name = fake.first_name()
        last_name = fake.last_name()
        with patch("apps.accounts.tasks.send_welcome_email.run") as mock:
            resp = self.api_client.post(
                url,
                data={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": self.company_member.email,
                    "password": fake.password(),
                    "company_name": self.company.name,
                    "token": self.company_member.token,
                },
                format="json",
            )
        assert resp.status_code == 200
        assert mock.called_once_with(user_id=User.objects.get(email=self.company_member.email).pk)
        data = resp.json()
        budget_data = data["data"]["company"]["offices"][0]["budget"]
        budget = BudgetOutputV2(**budget_data)
        assert budget

    def test_user_signup_without_token(self):
        url = reverse("signup")
        first_name = fake.first_name()
        last_name = fake.last_name()
        email = f"{first_name}.{last_name}@example.com"
        with patch("apps.accounts.tasks.send_welcome_email.run") as mock:
            resp = self.api_client.post(
                url,
                data={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "password": fake.password(),
                    "company_name": fake.company(),
                },
                format="json",
            )
        assert resp.status_code == 200
        assert mock.called_once_with(user_id=User.objects.get(email=email).pk)
        data = resp.json()
        offices = data["data"]["company"]["offices"]
        assert len(offices) == 0
