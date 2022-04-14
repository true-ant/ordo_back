from django.db import models


class BUDGET_SPEND_TYPE(models.TextChoices):
    DENTAL_SUPPLY_SPEND_BUDGET = "dental", "Dental Supply Budget"
    FRONT_OFFICE_SUPPLY_SPEND_BUDGET = "office", "Front Office Supply Budget"
    MISCELLANEOUS_SPEND_BUDGET = "miscellaneous", "Other"
