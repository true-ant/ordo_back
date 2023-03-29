from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ProductPrice:
    product_identifier: str
    price: Decimal
