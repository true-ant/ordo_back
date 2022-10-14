import asyncio
import datetime
import uuid
from asyncio import Semaphore
from collections import ChainMap
from http.cookies import SimpleCookie
from typing import Any, Dict, List, Optional, Union

from aiohttp import ClientResponse, ClientSession
from scrapy import Selector

from apps.vendor_clients import errors, types

BASE_HEADERS = {
    "Connection": "keep-alive",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


class BaseClient:
    VENDOR_SLUG = "base"
    MULTI_CONNECTIONS = 10
    subclasses = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()
        cls.subclasses.append(cls)

    @classmethod
    def make_handler(
        cls,
        vendor_slug: str,
        session: Optional[ClientSession] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        klass = [subclass for subclass in cls.subclasses if subclass.VENDOR_SLUG == vendor_slug][0]
        return klass(session=session, username=username, password=password)

    def __init__(
        self, session: Optional[ClientSession] = None, username: Optional[str] = None, password: Optional[str] = None
    ):
        self.session = session
        self.username = username
        self.password = password
        self.orders = {}

    async def get_login_data(self, *args, **kwargs) -> Optional[types.LoginInformation]:
        """Provide login credentials and additional data along with headers"""
        raise NotImplementedError("`get_login_data` must be implemented")

    async def check_authenticated(self, response: ClientResponse) -> bool:
        """Check if whether session is authenticated or not"""
        raise NotImplementedError("`check_authenticated` must be implemented")

    async def get_order_list(
        self, from_date: Optional[datetime.date] = None, to_date: Optional[datetime.date] = None
    ) -> Dict[str, Union[Selector, dict]]:
        """Get a list of simple order information"""
        raise NotImplementedError("`get_order_list` must be implemented")

    async def get_cart_page(self) -> Union[Selector, dict]:
        """Get cart page in order to get products in cart"""
        raise NotImplementedError("`get_cart_page` must be implemented")

    async def remove_product_from_cart(self, product: Any):
        """Remove a single product from the cart"""
        raise NotImplementedError("`remove_product_from_cart` must be implemented")

    async def clear_cart(self):
        """Clear all products from the cart"""
        raise NotImplementedError("`clear_cart` must be implemented")

    def serialize(self, base_product: types.Product, data: Union[dict, Selector]) -> Optional[types.Product]:
        """Serialize vendor-specific product detail to our data"""
        raise NotImplementedError("`clear_cart` must be implemented")

    async def add_product_to_cart(self, product: types.CartProduct, *args, **kwargs):
        """Add single product to cart"""
        raise NotImplementedError("`add_product_to_cart` must be implemented")

    async def checkout_and_review_order(self, shipping_method: Optional[str] = None) -> dict:
        """Review the order without making real order"""
        raise NotImplementedError("Vendor client must implement `checkout`")

    async def place_order(self, *args, **kwargs) -> str:
        """Make the real order"""
        raise NotImplementedError("Vendor client must implement `place_order`")

    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> Optional[SimpleCookie]:
        """Login session"""
        if username:
            self.username = username
        if password:
            self.password = password

        login_info = await self.get_login_data()
        if login_info:
            async with self.session.post(
                login_info["url"], headers=login_info["headers"], data=login_info["data"]
            ) as resp:
                if resp.status != 200:
                    raise errors.VendorAuthenticationFailed()

                is_authenticated = await self.check_authenticated(resp)
                if not is_authenticated:
                    raise errors.VendorAuthenticationFailed()

                if hasattr(self, "after_login_hook"):
                    await self.after_login_hook(resp)

            return resp.cookies

    async def get_response_as_dom(
        self, url: str, headers: Optional[dict] = None, query_params: Optional[dict] = None, **kwargs
    ) -> Selector:
        """Return response as dom format"""
        async with self.session.get(url, headers=headers, params=query_params, **kwargs) as resp:
            text = await resp.text()
            return Selector(text=text)

    async def get_response_as_json(
        self, url: str, headers: Optional[dict] = None, query_params: Optional[dict] = None, **kwargs
    ) -> dict:
        """Return response as json format"""
        async with self.session.get(url, headers=headers, params=query_params, **kwargs) as resp:
            return await resp.json()

    async def get_product_page(self, product_link: str, headers: Optional[dict] = None):
        """Get the product page"""
        return await self.get_response_as_dom(url=product_link, headers=headers)

    async def get_order(self, *args, **kwargs) -> Optional[types.Order]:
        """Get Order information"""
        semaphore = kwargs.pop("semaphore", None)
        if semaphore:
            await semaphore.acquire()

        if hasattr(self, "_get_order"):
            queue: asyncio.Queue = kwargs.pop("queue", None)

            order = await self._get_order(*args)
            if queue:
                await queue.put(order)

            return order

        if semaphore:
            semaphore.release()

    async def get_orders(
        self,
        from_date: Optional[datetime.date] = None,
        to_date: Optional[datetime.date] = None,
        exclude_order_ids: Optional[List[str]] = None,
        queue: Optional[asyncio.Queue] = None,
    ) -> List[types.Order]:
        await self.login()
        semaphore = Semaphore(value=self.MULTI_CONNECTIONS)
        order_list = await self.get_order_list(from_date=from_date, to_date=to_date)
        tasks = []
        for order_id, order_data in order_list.items():
            if exclude_order_ids and order_id in exclude_order_ids:
                continue
            tasks.append(self.get_order(order_data, semaphore=semaphore, queue=queue))

        orders = await asyncio.gather(*tasks, return_exceptions=True)
        return [order for order in orders if isinstance(order, dict)]

    async def get_product(
        self, product: types.Product, login_required: bool = True, semaphore: Semaphore = None
    ) -> Optional[types.Product]:
        """Get the product information"""
        if semaphore:
            await semaphore.acquire()

        if login_required:
            await self.login()

        if hasattr(self, "_get_product"):
            product_detail = await self._get_product(product)
        else:
            headers = getattr(self, "GET_PRODUCT_PAGE_HEADERS")
            product_page_dom = await self.get_response_as_dom(url=product["url"], headers=headers)
            product_detail = self.serialize(product, product_page_dom)
        if semaphore:
            semaphore.release()
        print("get_product DONE")
        return product_detail

    async def get_products(
        self, products: List[types.Product], login_required: bool = True
    ) -> Dict[str, Optional[types.Product]]:
        print("get_products")
        """Get the list of product information"""
        semaphore = Semaphore(value=self.MULTI_CONNECTIONS)
        ret: Dict[str, Optional[types.Product]] = {}

        if login_required:
            await self.login()
        tasks = (self.get_product(product=product, semaphore=semaphore, login_required=False) for product in products)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for product, result in zip(products, results):
            print("result is ", result)
            if isinstance(result, dict):
                ret[product["product_id"]] = result
            else:
                ret[product["product_id"]] = None
        return ret

    async def get_products_prices(
        self, products: List[types.Product], login_required: bool = True, *args, **kwargs
    ) -> Dict[str, types.ProductPrice]:
        print("get_products_prices")
        """Get the list of products prices"""
        if login_required:
            await self.login()

        if hasattr(self, "_get_products_prices"):
            return await self._get_products_prices(products, *args, **kwargs)
        elif hasattr(self, "get_product_price"):
            semaphore = Semaphore(value=self.MULTI_CONNECTIONS)
            tasks = (
                self.get_product_price(product=product, semaphore=semaphore, login_required=False)
                for product in products
            )
            results = await asyncio.gather(*tasks, return_exceptions=True)
            results = [result for result in results if isinstance(result, dict)]
            return dict(ChainMap(*results))
        else:
            results: Dict[str, Optional[types.Product]] = await self.get_products(
                products=products, login_required=False
            )
            ret: Dict[str, types.ProductPrice] = {
                product_id: {"price": product["price"], "product_vendor_status": product["product_vendor_status"]}
                for product_id, product in results.items()
                if product is not None
            }
            return ret

    async def remove_products_from_cart(self, products: List[Any]):
        """Remove the products from cart"""
        tasks = []
        for product in products:
            tasks.append(self.remove_product_from_cart(product))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def add_products_to_cart(self, products: List[types.CartProduct]):
        """Add Products to cart"""
        tasks = []
        kwargs = {}
        if hasattr(self, "before_add_products_to_cart"):
            kwargs = await self.before_add_products_to_cart()

        for product in products:
            tasks.append(self.add_product_to_cart(product, **kwargs))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _create_order(self, products: List[types.CartProduct], shipping_method: Optional[str] = None) -> dict:
        """Create an order on vendor side before the step of placing the real one"""
        await self.login()
        await self.clear_cart()
        await self.add_products_to_cart(products)
        return await self.checkout_and_review_order(shipping_method)

    async def create_order(
        self, products: List[types.CartProduct], shipping_method: Optional[str] = None
    ) -> Dict[str, types.VendorOrderDetail]:
        result = await self._create_order(products, shipping_method)
        order_detail = result.get("order_detail")
        return {self.VENDOR_SLUG: order_detail}

    async def confirm_order(self, products: List[types.CartProduct], shipping_method=None, fake=False):
        """Place an order on vendor side"""
        result = await self._create_order(products)
        if fake:
            order_id = f"{uuid.uuid4()}"
        else:
            order_id = await self.place_order(**result)

        order_detail = result.get("order_detail")
        return {
            self.VENDOR_SLUG: order_detail,
            "order_id": order_id,
        }
