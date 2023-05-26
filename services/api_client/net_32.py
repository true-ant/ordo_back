import asyncio
import re
from decimal import Decimal
from typing import List

from aiohttp.client import ClientSession
from lxml import etree

from services.api_client.vendor_api_types import Net32Product, Net32ProductInfo


def convert_string_to_price(price_string: str) -> Decimal:
    try:
        price = re.search(r"[,\d]+.?\d*", price_string).group(0)
        price = price.replace(",", "")
        return Decimal(price)
    except (KeyError, ValueError, TypeError, IndexError):
        return Decimal("0")


class Net32APIClient:
    def __init__(self, session: ClientSession):
        self.session = session

    async def get_products(self) -> List[Net32Product]:
        url = "https://www.net32.com/feeds/feedonomics/dental_delta_products.xml"
        products = []
        async with self.session.get(url) as resp:
            content = await resp.read()
            tree = etree.fromstring(content)
            product_list = tree.findall(".//entry")
            for product_element in product_list:
                products.append(
                    Net32Product(
                        mp_id=product_element.findtext("mp_id"),
                        price=convert_string_to_price(product_element.findtext("price")),
                        inventory_quantity=int(product_element.findtext("inventory_quantity")),
                    )
                )
            return products

    def parse_content(self, content: bytes):
        tree = etree.fromstring(content)
        product_elements = tree.findall(".//entry")
        return [
            Net32ProductInfo(
                mp_id=product_element.findtext(".//mp_id"),
                price=convert_string_to_price(product_element.findtext(".//price")),
                inventory_quantity=int(product_element.findtext(".//inventory_quantity")),
                name=product_element.findtext(".//title"),
                manufacturer_number=product_element.findtext(".//mp_code"),
                category=product_element.findtext(".//category"),
                url=product_element.findtext(".//link"),
                retail_price=convert_string_to_price(product_element.findtext(".//retail_price")),
                availability=product_element.findtext(".//availability"),
            )
            for product_element in product_elements
        ]

    async def get_full_products(self) -> List[Net32ProductInfo]:
        url = "https://www.net32.com/feeds/searchspring_windfall/dental_products.xml"
        async with self.session.get(url) as resp:
            content = await resp.read()
        return self.parse_content(content)


async def main():
    async with ClientSession() as session:
        api_client = Net32APIClient(session)
        return await api_client.get_full_products()


if __name__ == "__main__":
    ret = asyncio.run(main())
    print(ret)
