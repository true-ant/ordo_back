from typing import List, TypedDict, Union

from apps.scrapers.schema import Product

SmartID = Union[str, int]
SmartProductID = SmartID


class LoginInformation(TypedDict):
    url: str
    headers: dict
    data: dict


class ProductSearch(TypedDict):
    vendor_slug: str
    total_size: int
    page: int
    page_size: int
    products: List[Product]
    last_page: bool


class VendorInformation(TypedDict):
    id: int
    name: str
    slug: str
    url: str
    logo: str
