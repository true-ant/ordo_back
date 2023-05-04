import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Union

from django.db.models import F, Prefetch, Sum
from django.utils import timezone

from apps.accounts.models import Office, OfficeBudget
from apps.accounts.models import OfficeVendor as OfficeVendorModel
from apps.accounts.models import ShippingMethod as ShippingMethodModel
from apps.accounts.models import Vendor as VendorModel
from apps.common.choices import BUDGET_SPEND_TYPE
from apps.common.month import Month
from apps.common.utils import bulk_create
from apps.orders.models import Order
from services.opendental import OpenDentalClient


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
    def move_spend_category(
        office: Union[int, str, Office],
        date: datetime.date,
        amount: Decimal,
        from_category: BUDGET_SPEND_TYPE,
        to_category: BUDGET_SPEND_TYPE,
    ):
        """This function will move spend from one category to other category"""
        if from_category and to_category and from_category != to_category:
            month = Month.from_date(date)
            if not isinstance(office, Office):
                office_budget = OfficeBudget.objects.filter(office_id=office, month=month).first()
            else:
                office_budget = OfficeBudget.objects.filter(office=office, month=month).first()

            if office_budget:
                if from_category == BUDGET_SPEND_TYPE.DENTAL_SUPPLY_SPEND_BUDGET:
                    office_budget.dental_spend = F("dental_spend") - amount
                elif from_category == BUDGET_SPEND_TYPE.FRONT_OFFICE_SUPPLY_SPEND_BUDGET:
                    office_budget.office_spend = F("office_spend") - amount
                elif from_category == BUDGET_SPEND_TYPE.MISCELLANEOUS_SPEND_BUDGET:
                    office_budget.miscellaneous_spend = F("miscellaneous_spend") - amount

                if to_category == BUDGET_SPEND_TYPE.DENTAL_SUPPLY_SPEND_BUDGET:
                    office_budget.dental_spend = F("dental_spend") + amount
                elif to_category == BUDGET_SPEND_TYPE.FRONT_OFFICE_SUPPLY_SPEND_BUDGET:
                    office_budget.office_spend = F("office_spend") + amount
                elif to_category == BUDGET_SPEND_TYPE.MISCELLANEOUS_SPEND_BUDGET:
                    office_budget.miscellaneous_spend = F("miscellaneous_spend") + amount
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

    @staticmethod
    def update_office_budgets():
        # TODO: create budgets for active offices from Open Dental, if not, from previous month
        current_month = Month.from_date(timezone.now().date())
        previous_month = current_month.prev_month()
        last_day_of_prev_month = date.today().replace(day=1) - timedelta(days=1)
        start_day_of_prev_month = date.today().replace(day=1) - timedelta(days=last_day_of_prev_month.day)
        prev_month_office_budgets = OfficeBudget.objects.filter(month=previous_month)
        offices = Office.objects.prefetch_related(
            Prefetch("budgets", queryset=prev_month_office_budgets, to_attr="previous_budget")
        ).exclude(budgets__month=current_month)
        office_budgets_to_created = []
        for office in offices:
            dental_api = office.dental_api
            prev_month_office_budget = office.previous_budget
            if not dental_api:
                if not prev_month_office_budget:
                    continue
                prev_month_office_budget[0].id = None
                prev_month_office_budget[0].dental_spend = 0
                prev_month_office_budget[0].office_spend = 0
                prev_month_office_budget[0].month = current_month
                office_budgets_to_created.append(prev_month_office_budget[0])
                print(f"{office.name} from previous month")
            else:
                dental_api_key = dental_api.key
                new_budget = OfficeBudget()
                prev_adjusted_production, prev_collections = OfficeBudgetHelper.load_prev_month_production_collection(
                    start_day_of_prev_month, last_day_of_prev_month, dental_api_key
                )
                budget_from_opendental = prev_adjusted_production
                prev_dental_percentage = 5.0
                prev_office_percentage = 0.5
                budget_type = "production"
                if prev_month_office_budget[0]:
                    prev_dental_percentage = prev_month_office_budget[0].dental_percentage
                    prev_office_percentage = prev_month_office_budget[0].office_percentage
                    if prev_month_office_budget[0].dental_budget_type == "collection":
                        budget_type = "collection"
                        budget_from_opendental = prev_collections
                prev_dental_budget = budget_from_opendental * float(prev_dental_percentage) / 100.0
                prev_office_budget = budget_from_opendental * float(prev_office_percentage) / 100.0
                new_budget.office_id = office.id
                new_budget.adjusted_production = prev_adjusted_production
                new_budget.collection = prev_collections
                new_budget.dental_budget_type = budget_type
                new_budget.dental_budget_type = budget_type
                new_budget.dental_total_budget = budget_from_opendental
                new_budget.dental_percentage = prev_dental_percentage
                new_budget.dental_budget = prev_dental_budget
                new_budget.dental_spend = "0.0"
                new_budget.office_budget_type = budget_type
                new_budget.office_total_budget = budget_from_opendental
                new_budget.office_percentage = prev_office_percentage
                new_budget.office_budget = prev_office_budget
                new_budget.office_spend = "0.0"
                new_budget.month = datetime(current_month.year, current_month.month, 1)
                office_budgets_to_created.append(new_budget)
                print(f"{office.name} from Open Dental")
        bulk_create(OfficeBudget, office_budgets_to_created)

    @staticmethod
    def load_prev_month_production_collection(day1, day2, api_key):
        with open("query/production.sql") as f:
            product_query = f.read()
        query = product_query.format(day_from=day1, day_to=day2)
        od_client = OpenDentalClient(api_key)
        json_production = od_client.query(query)
        try:
            adjusted_production, collections = (
                json_production[0][0]["Adjusted_Production"],
                json_production[0][0]["Collections"],
            )
            return adjusted_production, collections
        except Exception:
            return 0, 0

    @staticmethod
    def get_office_spent_budget_current_month(office):
        current_month = Month.from_date(timezone.now().date())
        first_day_current_month = datetime(current_month.year, current_month.month, 1)
        orders = Order.objects.filter(office=office, order_date__gte=first_day_current_month).aggregate(
            total_amount=Sum("total_amount")
        )
        total_order_amount = orders["total_amount"] if orders["total_amount"] else 0.0
        return total_order_amount


class ShippingHelper:
    @staticmethod
    def get_connected_vendor_ids(office: Union[int, str, Office]) -> List[str]:
        if not isinstance(office, Office):
            office = Office.objects.get(id=office)

        return office.connected_vendors.values_list("vendor_id", flat=True)

    @staticmethod
    def import_shipping_options_from_json(file_path, vendor_slug, office_id=None):
        if not office_id:
            office_ids = Office.objects.all().values_list("pk", flat=True).distinct()
            for office_id in office_ids:
                ShippingHelper.import_shipping_options_for_one_office(
                    file_path=file_path, vendor_slug=vendor_slug, office_id=office_id
                )
        else:
            ShippingHelper.import_shipping_options_for_one_office(
                file_path=file_path, vendor_slug=vendor_slug, office_id=office_id
            )

    @staticmethod
    def import_shipping_options_for_one_office(file_path, vendor_slug, office_id):
        with open(file_path, "r") as file:
            data = json.loads(file.read())
        vendor = VendorModel.objects.get(slug=vendor_slug)
        office = Office.objects.get(id=office_id)

        connected_vendor_ids = ShippingHelper.get_connected_vendor_ids(office_id)
        if vendor.id in connected_vendor_ids:
            default_shipping_method = data["default_shipping_method"]
            shipping_options = data["shipping_options"]
            default_shipping_option: dict = {}

            shipping_options_to_be_created = []
            office_vendor = OfficeVendorModel.objects.filter(office=office, vendor=vendor).first()
            office_vendor.shipping_options.clear()

            for option in shipping_options:
                price = shipping_options[option]["shipping"].strip("$")
                price = price if price else None
                name = shipping_options[option]["shipping_method"]
                value = shipping_options[option]["shipping_value"]
                if name == default_shipping_method:
                    default_shipping_option = shipping_options[option]
                print("Creating new shopping option")
                shipping_options_to_be_created.append(ShippingMethodModel(name=name, price=price, value=value))

            shipping_options_objs = bulk_create(model_class=ShippingMethodModel, objs=shipping_options_to_be_created)
            print(f"{vendor}: {len(shipping_options_to_be_created)} shipping options created")

            default_shipping_option_obj = [
                o for o in shipping_options_objs if o.name == default_shipping_option["shipping_method"]
            ][0]
            office_vendor.default_shipping_option = default_shipping_option_obj
            for obj in shipping_options_objs:
                office_vendor.shipping_options.add(obj)
            office_vendor.save()
