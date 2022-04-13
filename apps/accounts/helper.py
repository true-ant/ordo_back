import datetime
from decimal import Decimal
from typing import Union

from django.db.models import F, Prefetch
from django.utils import timezone
from month import Month

from apps.accounts.models import Office, OfficeBudget
from apps.common.utils import bulk_create


class OfficeBudgetHelper:
    @staticmethod
    def update_spend(office: Union[int, str, Office], date: datetime.date, amount: Decimal):
        # TODO: expand this function to update 2 kinds of budgets
        if not isinstance(office, Office):
            office = Office.objects.get(id=office)

        month = Month(year=date.year, month=date.month)
        office_budget = office.budgets.filter(month=month).first()
        if office_budget:
            office_budget.dental_spend = F("dental_spend") + amount
            office_budget.save()

    @staticmethod
    def update_budget_with_previous_month():
        # TODO: update budget for active offices
        current_month = Month.from_date(timezone.now().date())
        previous_month = current_month.prev_month()
        office_budgets = OfficeBudget.objects.filter(month=previous_month)
        offices = Office.objects.prefetch_related(
            Prefetch("budgets", queryset=office_budgets, to_attr="previous_budget")
        ).exclude(budgets__month=current_month)
        office_budgets_to_created = []
        for office in offices:
            office_budget = office.previous_budget
            if not office_budget:
                continue
            office_budget[0].id = None
            office_budget[0].dental_spend = 0
            office_budget[0].office_spend = 0
            office_budget[0].month = current_month
            office_budgets_to_created.append(office_budget[0])

        bulk_create(OfficeBudget, office_budgets_to_created)
