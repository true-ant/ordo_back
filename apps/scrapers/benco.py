from typing import List

from aiohttp import ClientResponse

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product
from apps.types.orders import CartProduct
from apps.types.scraper import LoginInformation

SEARCH_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.benco.com/",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}


class BencoScraper(Scraper):
    BASE_URL = "https://www.pattersondental.com"

    async def _get_login_data(self) -> LoginInformation:
        pass

    async def _check_authenticated(self, resp: ClientResponse) -> bool:
        pass

    async def _after_login_hook(self, response: ClientResponse):
        pass

    async def get_orders(self, perform_login=False) -> List[Order]:
        pass

    async def get_product(self, product_dom):
        pass

    async def search_products(self, query: str, page: int = 1, per_page: int = 30) -> List[Product]:
        pass

    async def checkout(self, products: List[CartProduct]):
        pass
