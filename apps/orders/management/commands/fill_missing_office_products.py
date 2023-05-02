from django.conf import settings
from django.core.management import BaseCommand
from django.db import connection

from apps.accounts.models import OfficeVendor


class Command(BaseCommand):
    help = "Fix missing office products"

    def handle(self, *args, **options):
        office_vendors = OfficeVendor.objects.filter(vendor__slug__in=settings.FORMULA_VENDORS)
        with connection.cursor() as cursor:
            for office_vendor in office_vendors:
                cursor.callproc("fill_missing_office_products", [office_vendor.office_id, office_vendor.vendor_id])
