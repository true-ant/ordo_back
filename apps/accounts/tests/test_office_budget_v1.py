import datetime
import decimal
import math
from typing import Literal

from dateutil.relativedelta import relativedelta
from django.utils import timezone
from pydantic import BaseModel, root_validator, validator
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APIClient, APITestCase

from apps.accounts.factories import (
    CompanyFactory,
    CompanyMemberFactory,
    OfficeBudgetFactory,
    OfficeFactory,
    UserFactory,
)
from apps.common.month import Month


class RemainingBudget(BaseModel):
    dental: float
    office: float


BudgetType = Literal["production", "collection"]


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


class SingleOfficeBudgetTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = CompanyFactory()
        cls.office = OfficeFactory(company=cls.company)
        cls.company_member_user = UserFactory()
        cls.company_member = CompanyMemberFactory(company=cls.company, office=cls.office, user=cls.company_member_user)
        cls.office_budget = OfficeBudgetFactory(office=cls.office)
        cls.api_client = APIClient()
        cls.api_client.force_authenticate(cls.company_member_user)

    def test_company_member(self):
        url = reverse("members-list", kwargs={"company_pk": self.company.pk})
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        member_data = data["data"][0]
        office_data = member_data["office"]
        budget = BudgetOutput(**office_data["budget"])
        assert budget

    def test_company(self):
        url = reverse("companies-detail", kwargs={"pk": self.company.pk})
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        office_data = data["data"]["offices"][0]
        budget = BudgetOutput(**office_data["budget"])
        assert budget

    def test_budgets_list(self):
        url = reverse("budgets-list", kwargs={"company_pk": self.company.pk, "office_pk": self.office.pk})
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        budget_data = data["data"][0]
        budget = BudgetOutput(**budget_data)
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
        budget = BudgetOutput(**budget_data)
        assert budget

    def test_get_current_month_budget(self):
        url = reverse(
            "budgets-get-current-month-budget", kwargs={"company_pk": self.company.pk, "office_pk": self.office.pk}
        )
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        budget_data = data["data"]
        budget = BudgetOutput(**budget_data)
        assert budget


class ChartDataTestCase(APITestCase):
    @staticmethod
    def last_year():
        this_month = timezone.now().date().replace(day=1)
        start_month = this_month - relativedelta(months=11)
        current = start_month
        while current <= this_month:
            yield current
            current += relativedelta(months=1)

    @classmethod
    def setUpTestData(cls):
        cls.company = CompanyFactory()
        cls.office = OfficeFactory(company=cls.company)
        cls.company_member_user = UserFactory()
        cls.company_member = CompanyMemberFactory(company=cls.company, office=cls.office, user=cls.company_member_user)
        for month in cls.last_year():
            cls.office_budget = OfficeBudgetFactory(office=cls.office, month=month)
        cls.api_client = APIClient()
        cls.api_client.force_authenticate(cls.company_member_user)

    def test_chart_data(self):
        url = reverse("budgets-get-chart-data", kwargs={"company_pk": self.company.pk, "office_pk": self.office.pk})
        resp = self.api_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        for budget_data in data["data"]:
            budget = ChartBudget(**budget_data)
            assert budget
