from django_filters import rest_framework as filters

from .models import OfficeBudget


class OfficeBudgetFilter(filters.FilterSet):
    start_month = filters.DateFilter(field_name="month", lookup_expr="gte", input_formats=["%Y-%m"])
    end_month = filters.DateFilter(field_name="month", lookup_expr="lte", input_formats=["%Y-%m"])

    class Meta:
        model = OfficeBudget
        fields = ["start_month", "end_month"]
