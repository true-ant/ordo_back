from typing import List

from aiohttp import ClientResponse
from django.utils.dateparse import parse_datetime
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.errors import OrderFetchException
from apps.scrapers.schema import Order, Product
from apps.types.scraper import LoginInformation

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


class Net32Scraper(Scraper):
    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return (
            res.get("CallHeader", {}).get("StatusCode")
            and res["CallHeader"]["StatusCode"] != "SC_ERROR_BAD_LOGIN_CREDENTIALS"
        )

    async def _get_login_data(self) -> LoginInformation:
        return {
            "url": "https://www.net32.com/rest/user/login",
            "headers": HEADERS,
            "data": {
                "userName": self.username,
                "password": self.password,
                "latestTosVersion": "1",
            },
        }

    async def get_orders(self, perform_login=False) -> List[Order]:
        url = "https://www.net32.com/rest/order/orderHistory"
        headers = HEADERS.copy()
        headers["Referer"] = "https://www.net32.com/account/orders"
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
                            "items": [
                                {
                                    "name": line_item["title"],
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

    async def search_products(self, query: str, perform_login: bool = False) -> List[Product]:
        url = "https://www.net32.com/search"
        params = {
            "q": query,
            "page": 1,
        }
        async with self.session.get(url, headers=SEARCH_HEADERS, params=params) as resp:
            response_dom = Selector(text=await resp.text())

            products = []
            products_dom = response_dom.xpath(
                "//div[@class='localsearch-results-container']//div[@class='localsearch-result-container']"
            )

            for product_dom in products_dom:
                products.append(
                    Product(
                        name=self.extract_first(product_dom, ".//a[@class='localsearch-result-product-name']//text()"),
                        link="https://www.net32.com"
                        + self.extract_first(product_dom, ".//a[@class='localsearch-result-product-name']/@href"),
                        description=self.extract_first(
                            product_dom, ".//div[@class='localsearch-result-product-packaging-container']//text()"
                        ),
                        image="https://www.net32.com"
                        + self.extract_first(
                            product_dom, ".//img[@class='localsearch-result-product-thumbnail']/@src"
                        ),
                        price=price_
                        if (
                            price_ := self.extract_first(
                                product_dom, ".//ins[@class='localsearch-result-best-price']//text()"
                            )
                        )
                        else "Currently out of stock",
                        retail_price=self.extract_first(
                            product_dom, ".//del[@class='localsearch-result-retail-price']//text()"
                        ),
                        stars=self.extract_first(
                            product_dom,
                            ".//span[contains(@class, 'star-rating localsearch-result-star-rating')]//text()",
                        ),
                        ratings=self.extract_first(
                            product_dom, ".//span[@class='localsearch-result-star-rating-count-container']//text()"
                        ),
                    )
                )

            return products
