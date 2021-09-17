from typing import TypedDict


class LinkedVendor(TypedDict):
    vendor: str
    username: str
    password: str


class CartProduct(TypedDict):
    product_id: str
    quantity: int
