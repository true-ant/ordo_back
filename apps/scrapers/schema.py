from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from typing import List, get_args, get_origin

from django.utils.dateparse import parse_datetime


def from_dict(cls, dict_data):
    def convert_dict2dataclass(field_type, v):
        if isinstance(v, field_type):
            return v
        elif field_type in (int, float, str):
            return field_type(v)
        elif field_type is Decimal:
            return Decimal(str(v).strip("$"))
        elif field_type is datetime:
            return parse_datetime(v)
        else:
            return field_type.from_dict(v)

    data = {}
    for field in fields(cls):
        key = field.name
        value = dict_data.get(key, None)
        if value is not None:
            if get_origin(field.type) is list:
                data[key] = [convert_dict2dataclass(get_args(field.type)[0], item) for item in value]
            else:
                data[key] = convert_dict2dataclass(field.type, value)
        else:
            data[key] = None

    return cls(**data)


class BaseDataClass:
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict):
        return from_dict(cls, value)


@dataclass(frozen=True)
class OrderItem(BaseDataClass):
    name: str
    quantity: int
    unit_price: Decimal
    status: str


@dataclass(frozen=True)
class Order(BaseDataClass):
    id: str
    total_amount: Decimal
    currency: str
    order_date: date
    status: str
    items: List[OrderItem]