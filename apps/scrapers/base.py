from http.cookies import SimpleCookie
from typing import Optional

from aiohttp import ClientResponse, ClientSession

from apps.scrapers.errors import VendorAuthenticationFailed
from apps.scrapers.utils import catch_network
from apps.types.scraper import LoginInformation, ProductSearch, VendorInformation


class Scraper:
    def __init__(
        self,
        session: ClientSession,
        vendor: VendorInformation,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.session = session
        self.vendor = vendor
        self.username = username
        self.password = password

    @catch_network
    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> SimpleCookie:
        if username:
            self.username = username
        if password:
            self.password = password

        login_info = await self._get_login_data()
        async with self.session.post(
            login_info["url"], headers=login_info["headers"], data=login_info["data"]
        ) as resp:
            if resp.status != 200:
                raise VendorAuthenticationFailed()

            is_authenticated = await self._check_authenticated(resp)
            if not is_authenticated:
                raise VendorAuthenticationFailed()

            await self._after_login_hook(resp)

        return resp.cookies

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        return True

    async def _get_login_data(self) -> LoginInformation:
        pass

    async def _after_login_hook(self, response: ClientResponse):
        pass

    def extract_first(self, dom, xpath):
        return x.strip() if (x := dom.xpath(xpath).extract_first()) else x

    def merge_strip_values(self, dom, xpath, delimeter=""):
        return delimeter.join(filter(None, map(str.strip, dom.xpath(xpath).extract())))

    def remove_thousands_separator(self, value):
        value = value.replace(" ", "")
        value = value.replace(",", "")
        return value

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        pass

    async def search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        res_products = []
        page_size = 0

        await self.login()

        while True:
            product_search = await self._search_products(query, page, min_price=min_price, max_price=max_price)
            if not page_size:
                page_size = product_search["page_size"]

            total_size = product_search["total_size"]
            products = product_search["products"]
            last_page = product_search["last_page"]
            if max_price:
                products = [product for product in products if product.price and product.price < max_price]
            if min_price:
                products = [product for product in products if product.price and product.price > min_price]

            res_products.extend(products)

            if len(res_products) > 10 or last_page:
                break
            page += 1

        return {
            "vendor_slug": self.vendor["slug"],
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": res_products,
            "last_page": last_page,
        }
