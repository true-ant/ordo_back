from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ProductPrice:
    product_identifier: str
    price: Decimal


@dataclass(frozen=True)
class DentalCityProduct:
    product_sku: str
    list_price: Decimal
    partner_price: Decimal
    web_price: Decimal
    partner_code: str
    product_desc: str
    available_quantity: int
    manufacturer: str
    manufacturer_part_number: str
    manufacturer_special: str
    flyer_special: str
    eta_date: str
    update_date: str
