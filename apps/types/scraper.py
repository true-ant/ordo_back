from typing import List, TypedDict

from apps.scrapers.schema import Product


class LoginInformation(TypedDict):
    url: str
    headers: dict
    data: dict


class ProductSearch(TypedDict):
    total_size: int
    page: int
    page_size: int
    products: List[Product]
    last_page: bool
