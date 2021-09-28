from typing import List

from aiohttp import ClientResponse
from django.utils.dateparse import parse_datetime
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.errors import OrderFetchException
from apps.scrapers.schema import Order, Product
from apps.scrapers.utils import catch_network
from apps.types.orders import CartProduct
from apps.types.scraper import LoginInformation, ProductSearch

HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "Accept": "application/json",
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",  # noqa
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.net32.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.net32.com/login?origin=%2F",
    "Accept-Language": "en-US,en;q=0.9",
}

SEARCH_HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "sec-ch-ua-mobile": "?0",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",  # noqa
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",  # noqa
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Language": "en-US,en;q=0.9",
}

CART_HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "Accept": "application/json",
    "Content-Type": "application/json",
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",  # noqa
    "sec-ch-ua-platform": '"Windows"',
    "Origin": "https://www.net32.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.net32.com/shopping-cart",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}

CHECKOUT_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",  # noqa
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",  # noqa
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.net32.com/shopping-cart",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}

REVIEW_CHECKOUT_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.net32.com/shopping-cart",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}

PLACE_ORDER_HEADERS = {
    "Connection": "keep-alive",
    "Content-Length": "0",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Origin": "https://www.net32.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.net32.com/checkout/review",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}


class Net32Scraper(Scraper):
    BASE_URL = "https://www.net32.com"

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return (
            res.get("CallHeader", {}).get("StatusCode")
            and res["CallHeader"]["StatusCode"] != "SC_ERROR_BAD_LOGIN_CREDENTIALS"
        )

    async def _get_login_data(self) -> LoginInformation:
        return {
            "url": f"{self.BASE_URL}/rest/user/login",
            "headers": HEADERS,
            "data": {
                "userName": self.username,
                "password": self.password,
                "latestTosVersion": "1",
            },
        }

    @catch_network
    async def get_orders(self, perform_login=False) -> List[Order]:
        url = f"{self.BASE_URL}/rest/order/orderHistory"
        headers = HEADERS.copy()
        headers["Referer"] = f"{self.BASE_URL}/account/orders"
        params = {
            "paymentSystemId": "1",
            "startPoint": "0",
            "endPoint": "100000",
            "pendingSw": "true",
            "completeSw": "true",
        }

        if perform_login:
            await self.login()

        async with self.session.get(url, headers=headers, params=params) as resp:
            res = await resp.json()

        try:
            orders = []
            for order in res["Payload"]["orders"]:
                orders.append(
                    Order.from_dict(
                        {
                            "order_id": order["id"],
                            "total_amount": order["orderTotal"],
                            "currency": "USD",
                            "order_date": parse_datetime(order["coTime"]).date(),
                            "status": order["status"],
                            "shipping_address": {
                                "address": "".join([i for i in order["shippingAdress"]["Streets"] if i]),
                                "region_code": order["shippingAdress"]["RegionCD"],
                                "postal_code": order["shippingAdress"]["PostalCD"],
                            },
                            "products": [
                                {
                                    "product": {
                                        "product_id": line_item["id"],
                                        "name": line_item["mpName"],
                                        "description": line_item["description"],
                                        "url": f"{self.BASE_URL}/{line_item['detailLink']}",
                                        "images": [{"image": f"{self.BASE_URL}/media{line_item['mediaPath']}"}],
                                        "price": line_item["oliProdPrice"],
                                        "retail_price": line_item["oliProdRetailPrice"],
                                    },
                                    "quantity": line_item["quantity"],
                                    "unit_price": line_item["oliProdPrice"],
                                    "status": line_item["status"],
                                }
                                for vendor_order in order["vendorOrders"]
                                for line_item in vendor_order["lineItems"]
                            ],
                        }
                    )
                )
            return orders
        except KeyError:
            raise OrderFetchException()

    @catch_network
    async def get_product(self, product_id, product_url, perform_login=False) -> Product:
        pass

    @catch_network
    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        url = f"{self.BASE_URL}/search"
        page_size = 60
        params = {
            "q": query,
            "page": page,
        }
        if min_price:
            params["filter.price.low"] = min_price
        if max_price:
            params["filter.price.high"] = max_price

        async with self.session.get(url, headers=SEARCH_HEADERS, params=params) as resp:
            response_dom = Selector(text=await resp.text())

            try:
                total_size_str = response_dom.xpath(
                    "//p[@class='localsearch-result-summary-paragraph']/strong/text()"
                ).get()
                total_size = int(self.remove_thousands_separator(total_size_str))
            except (AttributeError, ValueError, TypeError):
                total_size = 0

            products = []
            products_dom = response_dom.xpath(
                "//div[@class='localsearch-results-container']//div[contains(@class, 'localsearch-result-wrapper')]"
            )

            for product_dom in products_dom:
                products.append(
                    Product.from_dict(
                        {
                            "product_id": product_dom.attrib["data-mpid"],
                            "name": self.extract_first(
                                product_dom, ".//a[@class='localsearch-result-product-name']//text()"
                            ),
                            "description": self.extract_first(
                                product_dom, ".//div[@class='localsearch-result-product-packaging-container']//text()"
                            ),
                            "url": self.BASE_URL
                            + self.extract_first(product_dom, ".//a[@class='localsearch-result-product-name']/@href"),
                            "images": [
                                {
                                    "image": self.BASE_URL
                                    + self.extract_first(
                                        product_dom, ".//img[@class='localsearch-result-product-thumbnail']/@src"
                                    )
                                }
                            ],
                            "price": self.extract_first(
                                product_dom, ".//ins[@class='localsearch-result-best-price']//text()"
                            ),
                            "retail_price": "",
                            "vendor_id": self.vendor_id,
                        }
                    )
                )

            return {
                "vendor_slug": self.vendor_slug,
                "total_size": total_size,
                "page": page,
                "page_size": page_size,
                "products": products,
                "last_page": page_size * page >= total_size,
            }

    @catch_network
    async def checkout(self, products: List[CartProduct]):
        await self.login()
        # Add cart
        data = [{"mpId": product["product_id"], "quantity": product["quantity"]} for product in products]
        await self.session.post(
            "https://www.net32.com/rest/shoppingCart/addMfrProdViaConsolidation", headers=CART_HEADERS, json=data
        )
        await self.session.get("https://www.net32.com/checkout", headers=CHECKOUT_HEADERS)

        # Review checkout
        await self.session.get("https://www.net32.com/checkout", headers=REVIEW_CHECKOUT_HEADERS)

        # Place Order
        # await self.session.post("https://www.net32.com/checkout/confirmation", headers=PLACE_ORDER_HEADERS)
