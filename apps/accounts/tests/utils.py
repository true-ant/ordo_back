import re
from typing import Iterator

from django.utils import timezone

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
