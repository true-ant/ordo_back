from decimal import Decimal
from typing import TypedDict, Union


class LinkedVendor(TypedDict):
    vendor: str
    username: str
    password: str


class CartProduct(TypedDict):
    product_id: str
    quantity: int


class VendorCartProduct(TypedDict):
    product_id: Union[str, int]
    unit_price: Union[str, Decimal]
