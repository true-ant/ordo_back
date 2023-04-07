import asyncio
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import List

from aiohttp.client import ClientSession

from services.api_client.vendor_api_types import Net32Product


class Net32APIClient:
    def __init__(self, session: ClientSession):
        self.session = session

    async def get_products(self) -> List[Net32Product]:
        url = "https://www.net32.com/feeds/feedonomics/dental_delta_products.xml"
        products = []
        async with self.session.get(url) as resp:
            content = await resp.text()
            products_xml = ET.fromstring(content)
            for product_element in products_xml.iter("entry"):
                price_string = product_element.find("price").text
                price_string = re.search(r"[,\d]+.?\d*", price_string).group(0)
                products.append(
                    Net32Product(
                        mp_id=product_element.find("mp_id").text,
                        price=Decimal(price_string),
                        inventory_quantity=int(product_element.find("inventory_quantity").text),
                    )
                )
            return products


async def main():
    async with ClientSession() as session:
        api_client = Net32APIClient(session)
        return await api_client.get_products()


if __name__ == "__main__":
    ret = asyncio.run(main())
    print(ret)
