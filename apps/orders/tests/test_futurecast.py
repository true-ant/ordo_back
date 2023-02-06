import datetime
import math

from dateutil.relativedelta import relativedelta
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
from apps.orders.factories import (
    ProcedureCategoryLinkFactory,
    ProcedureCodeFactory,
    ProcedureFactory,
)


class FutureCastAPITests(APITestCase):
    def setUp(self) -> None:
        self.company = CompanyFactory()
        self.company_office = OfficeFactory(company=self.company)
        self.office = OfficeFactory(company=self.company)
        self.admin = UserFactory(role=User.Role.ADMIN)
        CompanyMemberFactory(company=self.company, user=self.admin, email=self.admin.email)
        # Summary category
        self.category1 = ProcedureCategoryLinkFactory(
            summary_slug="Whitening", linked_slugs=["whitening"], category_order=2, is_favorite=True
        )
        self.category2 = ProcedureCategoryLinkFactory(
            summary_slug="Bone Graft",
            linked_slugs=["surgical-supplies", "anesthetics"],
            category_order=4,
            is_favorite=False,
        )
        # Procedure Code for summary category category1
        self.proccode1 = ProcedureCodeFactory(proccode="D9972", summary_category=self.category1)
        self.proccode2 = ProcedureCodeFactory(proccode="D9973", summary_category=self.category1)
        # Procedure Code for summary category category2
        self.proccode3 = ProcedureCodeFactory(proccode="D4263", summary_category=self.category2)
        # Available procedure history for thisMonth
        proc1 = ProcedureFactory(
            start_date=datetime.date.today(), count=5, procedurecode=self.proccode1, office=self.office, type="month"
        )
        proc2 = ProcedureFactory(
            start_date=datetime.date.today(), count=3, procedurecode=self.proccode2, office=self.office, type="month"
        )
        proc3 = ProcedureFactory(
            start_date=datetime.date.today(), count=3, procedurecode=self.proccode3, office=self.office, type="month"
        )

        # Unavailable procedure history for thisMonth, but available for last 3 months
        proc4 = ProcedureFactory(
            start_date=datetime.date.today() - relativedelta(months=1),
            count=13,
            procedurecode=self.proccode1,
            office=self.office,
            type="month",
        )
        proc5 = ProcedureFactory(
            start_date=datetime.date.today() - relativedelta(months=2),
            count=20,
            procedurecode=self.proccode2,
            office=self.office,
            type="month",
        )
        self.expected_order_count1 = proc1.count + proc2._count
        self.expected_order_count2 = proc3.count
        self.expected_order_avg_count1 = math.floor((proc4.count + proc5.count) / 3)
        self.expected_order_avg_count2 = 0

    def test_summary_category(self):
        self.client.force_authenticate(self.admin)
        link = reverse(
            "procedures-summary_category", kwargs={"company_pk": self.company.id, "office_pk": self.office.id}
        )
        link = f"{link}?type=month&date_range=thisMonth"
        response = self.client.get(link)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = response.data
        self.assertEqual(len(result), 2)  # Number of summary category
        self.assertEqual(result[0].order, 2)
        self.assertEqual(result[0].slug, self.category1.slug)
        self.assertEqual(result[0].is_favorite, True)
        self.assertEqual(result[0].count, self.expected_order_count1)
        self.assertEqual(result[0].avg_count, self.expected_order_avg_count1)
        self.assertEqual(result[1].order, 4)
        self.assertEqual(result[1].slug, self.category2.slug)
        self.assertEqual(result[1].is_favorite, False)
        self.assertEqual(result[1].count, self.expected_order_count2)
        self.assertEqual(result[1].avg_count, self.expected_order_avg_count2)
