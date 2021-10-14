import asyncio
import re
from http.cookies import SimpleCookie
from typing import Dict, List, Optional, Tuple, Union

from aiohttp import ClientResponse, ClientSession
from scrapy import Selector

from apps.scrapers.errors import VendorAuthenticationFailed
from apps.scrapers.schema import Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import catch_network
from apps.types.orders import CartProduct, VendorCartProduct
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
        self.orders = {}

    @staticmethod
    def extract_first(dom, xpath):
        return x.strip() if (x := dom.xpath(xpath).extract_first()) else x

    @staticmethod
    def merge_strip_values(dom, xpath, delimeter=""):
        return delimeter.join(filter(None, map(str.strip, dom.xpath(xpath).extract())))

    @staticmethod
    def remove_thousands_separator(value):
        value = value.strip(" $")
        value = value.replace(" ", "")
        value = value.replace(",", "")
        return value

    @staticmethod
    def get_category_slug(value) -> Optional[str]:
        try:
            return value.split("/")[-1]
        except (AttributeError, IndexError):
            pass

    @staticmethod
    def extract_price(value):
        prices = re.findall("\\d+\\.\\d+", value)
        return prices[0] if prices else None

    async def _get_check_login_state(self) -> Tuple[bool, dict]:
        return False, {}

    @catch_network
    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> SimpleCookie:
        if username:
            self.username = username
        if password:
            self.password = password

        is_already_login, kwargs = await self._get_check_login_state()
        if not is_already_login:
            login_info = await self._get_login_data(**kwargs)
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

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        pass

    async def _after_login_hook(self, response: ClientResponse):
        pass

    def _get_vendor_categories(self, response) -> List[ProductCategory]:
        pass

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        raise NotImplementedError()

    async def get_product(self, product_id, product_url, perform_login=False) -> Product:
        product = await self.get_product_as_dict(product_id, product_url, perform_login)
        return Product.from_dict(product)

    async def get_missing_product_fields(self, product_id, product_url, perform_login=False, fields=None) -> dict:
        product = await self.get_product_as_dict(product_id, product_url, perform_login)

        if fields and isinstance(fields, tuple):
            return {k: v for k, v in product.items() if k in fields}

    async def get_missing_products_fields(self, order_products, fields=("description",)):
        tasks = (
            self.get_missing_product_fields(
                product_id=order_product["product"]["product_id"],
                product_url=order_product["product"]["url"],
                perform_login=False,
                fields=fields,
            )
            for order_product in order_products
            if order_product["product"]["url"]
        )
        products_missing_data = await asyncio.gather(*tasks, return_exceptions=True)
        for order_product, product_missing_data in zip(order_products, products_missing_data):
            for field in fields:
                order_product["product"][field] = product_missing_data[field]

    async def get_vendor_categories(self, url=None, headers=None, perform_login=False) -> List[ProductCategory]:
        if perform_login:
            await self.login()

        url = self.CATEGORY_URL if hasattr(self, "CATEGORY_URL") else url
        if not url:
            raise ValueError

        headers = self.CATEGORY_HEADERS if hasattr(self, "CATEGORY_HEADERS") else headers

        ssl_context = self._ssl_context if hasattr(self, "_ssl_context") else None
        async with self.session.get(url, headers=headers, ssl=ssl_context) as resp:
            if resp.content_type == "application/json":
                response = await resp.json()
            else:
                response = Selector(text=await resp.text())
            return self._get_vendor_categories(response)

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        pass

    @catch_network
    async def search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        res_products = []
        page_size = 0

        if self.vendor["slug"] != "ultradent":
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

    async def add_product_to_cart(self, product: CartProduct) -> VendorCartProduct:
        raise NotImplementedError("Vendor scraper must implement `add_product_to_cart`")

    async def add_products_to_cart(self, products: List[CartProduct]) -> List[VendorCartProduct]:
        raise NotImplementedError("Vendor scraper must implement `add_products_to_cart`")

    async def remove_product_from_cart(self, product_id: Union[str, int], use_bulk: bool = True):
        raise NotImplementedError("Vendor scraper must implement `remove_product_from_cart`")

    async def clear_cart(self):
        raise NotImplementedError("Vendor scraper must implement `clear_cart`")

    async def create_order(self, products: List[CartProduct]) -> Dict[str, VendorOrderDetail]:
        raise NotImplementedError("Vendor scraper must implement `create_order`")

    async def confirm_order(self, products: List[CartProduct]):
        raise NotImplementedError("Vendor scraper must implement `confirm_order`")
