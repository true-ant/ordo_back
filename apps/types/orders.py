from decimal import Decimal
from typing import TypedDict, Union

PriceType = Union[str, Decimal]


class LinkedVendor(TypedDict):
    vendor: str
    username: str
    password: str


class CartProduct(TypedDict):
    product_id: str
    quantity: int


class VendorCartProduct(TypedDict):
    product_id: Union[str, int]
    unit_price: PriceType


class VendorOrderDetail(TypedDict):
    retail_amount: PriceType
    savings_amount: PriceType
    subtotal_amount: PriceType
    shipping_amount: PriceType
    tax_amount: PriceType
    total_amount: PriceType
    payment_method: str
    shipping_address: str
