import glob
import csv
import os
import json
from django.core.management import BaseCommand

from apps.common.utils import get_file_name_and_ext
from apps.orders.helpers import ProductHelper
from apps.orders.tasks import update_promotions


class Command(BaseCommand):
    """
    python manage.py update_promotion
    """

    help = "Update promotions for all vendors"

    def handle(self, *args, **options):
        update_promotions.delay()
