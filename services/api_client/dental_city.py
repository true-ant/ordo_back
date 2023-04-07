import asyncio
import os
from enum import Enum
from typing import List

from aiohttp.client import ClientSession

from services.api_client.vendor_api_types import DentalCityProduct


class Stage(Enum):
    TEST = "https://dcservicestest.azurewebsites.net"
    PROD = "https://dcservicestest.azurewebsites.net"


class DentalCityAPIClient:
    def __init__(self, session: ClientSession, stage: Stage = Stage.PROD, auth_key: str = ""):
        self.session = session
        self.stage = stage
        self.page_size = 5000
        self.session.headers.update({"x-functions-key": auth_key})

    async def get_page_products(self, page_number: int = 1) -> List[DentalCityProduct]:
        url = f"{self.stage.value}/api/ProductPriceStockAvailability"
        params = {
            "page_size": self.page_size,
            "page_number": page_number,
        }
        async with self.session.get(url, params=params) as resp:
            products = await resp.json()

            return [DentalCityProduct.from_dict(product) for product in products]

    async def get_products(self) -> List[DentalCityProduct]:
        products: List[DentalCityProduct] = []
        start_page = 1
        while True:
            end_page = start_page + 10
            tasks = (self.get_page_products(page) for page in range(start_page, end_page))
            results = await asyncio.gather(*tasks)
            products.extend([product for result in results for product in result])
            if len(products) < self.page_size * (end_page - 1):
                break
            start_page = end_page
        return products


async def main():
    async with ClientSession() as session:
        api_client = DentalCityAPIClient(session, stage=Stage.TEST, auth_key=os.environ.get("DENTAL_CITY_AUTH_KEY"))
        return await api_client.get_products()


if __name__ == "__main__":
    ret = asyncio.run(main())
    print(ret)