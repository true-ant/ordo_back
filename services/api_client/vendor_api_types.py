from dataclasses import dataclass, fields
from decimal import Decimal


@dataclass(frozen=True)
class Net32Product:
    mp_id: str
    price: Decimal
    inventory_quantity: int

    @property
    def product_identifier(self):
        return self.mp_id


@dataclass(frozen=True)
class DentalCityProduct:
    product_sku: str
    list_price: Decimal
    partner_price: Decimal
    web_price: Decimal
    manufacturer: str
    manufacturer_part_number: str
    manufacturer_special: str
    # partner_code: str
    # product_desc: str
    # product_long_desc: str
    # product_image_url: str
    # available_quantity: int
    # flyer_special: str
    # fulfillment_type: str
    # free_goods_id: str
    # eta_date: str
    # update_date: str  # 04/05/2023

    @property
    def product_identifier(self):
        return self.product_sku

    @property
    def price(self):
        return self.partner_price

    @classmethod
    def from_dict(cls, data: dict):
        field_names = [field.name for field in fields(cls)]
        data = {key: value for key, value in data.items() if key in field_names}
        return cls(
            list_price=Decimal(data.pop("list_price", 0)),
            partner_price=Decimal(data.pop("partner_price", 0)),
            web_price=Decimal(data.pop("web_price", 0)),
            **data
        )
