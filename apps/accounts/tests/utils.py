import re
from typing import Iterator

from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.month import Month


def last_year_months() -> Iterator[Month]:
    this_month = Month.from_date(timezone.now().date())
    start_month = this_month - 11
    current = start_month
    while current <= this_month:
        yield current
        current += 1


def escape_to_varname(s):
    return re.sub(r"\W|^(?=\d)", "_", s)


class VersionedAPIClient(APIClient):
    def __init__(self, enforce_csrf_checks=False, version="1.0", **defaults):
        super().__init__(enforce_csrf_checks, **defaults)
        self.version = version

    def request(self, **kwargs):
        return super().request(HTTP_ACCEPT=f"application/json; version={self.version}", **kwargs)
