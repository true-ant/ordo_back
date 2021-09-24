import asyncio
import re
from datetime import datetime
from typing import List

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product
from apps.scrapers.utils import catch_network
from apps.types.orders import CartProduct
from apps.types.scraper import LoginInformation, ProductSearch

HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",  # noqa
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.darbydental.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.darbydental.com/DarbyHome.aspx",
    "Accept-Language": "en-US,en;q=0.9",
}

SEARCH_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "sec-ch-ua-mobile": "?0",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/92.0.4515.159 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml; q=0.9,image/avif,"
    "image/webp,image/apng,*/*; q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.darbydental.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

CART_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
    "sec-ch-ua-platform": '"Windows"',
    "Origin": "https://www.darbydental.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.darbydental.com",
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.darbydental.com/scripts/cart.aspx",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}


class DarbyScraper(Scraper):
    BASE_URL = "https://www.darbydental.com"

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return res["m_Item2"] and res["m_Item2"]["username"] == self.username

    async def _get_login_data(self) -> LoginInformation:
        return {
            "url": f"{self.BASE_URL}/api/Login/Login",
            "headers": HEADERS,
            "data": {"username": self.username, "password": self.password, "next": ""},
        }

    @catch_network
    async def get_order(self, order_dom):
        link = self.merge_strip_values(order_dom, "./td[1]/a/@href")
        order = {
            "order_id": self.merge_strip_values(order_dom, "./td[1]//text()"),
            "total_amount": self.merge_strip_values(order_dom, ".//td[8]//text()"),
            "currency": "USD",
            "order_date": datetime.strptime(self.merge_strip_values(order_dom, ".//td[2]//text()"), "%m/%d/%Y").date(),
            # TODO: fetch darby status
            "status": "status",
        }
        async with self.session.get(f"{self.BASE_URL}/Scripts/{link}", headers=HEADERS) as resp:
            order_detail_response = Selector(text=await resp.text())
            order["products"] = []
            for detail_row in order_detail_response.xpath(
                "//table[@id='MainContent_gvInvoiceDetail']//tr[@class='pdpHelltPrimary']"  # noqa
            ):
                order["products"].append(
                    {
                        "product": {
                            "product_id": self.merge_strip_values(detail_row, "./td[1]/a//text()"),
                            "name": self.merge_strip_values(detail_row, "./td[2]//text()"),
                            "url": self.BASE_URL + self.merge_strip_values(detail_row, "./td[1]/a//@href"),
                            "images": [
                                {"image": self.BASE_URL + self.merge_strip_values(detail_row, "./td[1]/input//@src")}
                            ],
                            "price": self.merge_strip_values(detail_row, "./td[4]//text()"),
                        },
                        "quantity": self.merge_strip_values(detail_row, "./td[5]//text()"),
                        "unit_price": self.merge_strip_values(detail_row, "./td[4]//text()"),
                    }
                )

        return Order.from_dict(order)

    @catch_network
    async def get_orders(self, perform_login=False):
        url = f"{self.BASE_URL}/Scripts/InvoiceHistory.aspx"

        if perform_login:
            await self.login()

        async with self.session.get(url, headers=HEADERS) as resp:
            text = await resp.text()
            response_dom = Selector(text=text)
            orders_dom = response_dom.xpath(
                "//table[@id='MainContent_gvInvoiceHistory']//tr[@class='pdpHelltPrimary']"
            )
            tasks = (self.get_order(order_dom) for order_dom in orders_dom)
            return await asyncio.gather(*tasks, return_exceptions=True)

    @catch_network
    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        url = "https://www.darbydental.com/scripts/productlistview.aspx"
        page_size = 30
        params = {
            "term": query,
        }
        data = {
            "ctl00$masterSM": f"ctl00$MainContent$UpdatePanel1|ctl00$MainContent$ppager$ctl{page - 1:02}$pagelink",
            "ctl00$logonControl$txtUsername": "",
            "ctl00$logonControl$txtPassword": "",
            "ctl00$bigSearchTerm": query,
            "ctl00$searchSmall": query,
            # "ctl00$MainContent$currentPage": f"{current_page}",
            # "ctl00$MainContent$pageCount": clean_text(
            #     response, "//input[@name='ctl00$MainContent$pageCount']/@value"
            # ),
            "ctl00$MainContent$currentSort": "score",
            "ctl00$MainContent$selPerPage": f"{page_size}",
            "ctl00$MainContent$sorter": "score",
            # "ctl00$serverTime": clean_text(response, "//input[@name='ctl00$serverTime']/@value"),
            "__EVENTTARGET": f"ctl00$MainContent$ppager$ctl{page - 1:02}$pagelink",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE": "",
            "__VIEWSTATEGENERATOR": "A1889DD4",
            "__ASYNCPOST": "true",
        }
        products = []

        await self.login()

        async with self.session.post(url, headers=SEARCH_HEADERS, data=data, params=params) as resp:
            response_dom = Selector(text=await resp.text())
            total_size_str = response_dom.xpath(".//span[@id='MainContent_resultCount']/text()").extract_first()
            matches = re.search(r"of(.*?)results", total_size_str)
            total_size = int(matches.group(1).strip()) if matches else 0
            products_dom = response_dom.xpath("//div[@id='productContainer']//div[contains(@class, 'prodcard')]")
            for product_dom in products_dom:
                price = self.extract_first(product_dom, ".//div[contains(@class, 'prod-price')]//text()")
                _, price = price.split("@")
                products.append(
                    Product.from_dict(
                        {
                            "product_id": self.extract_first(product_dom, ".//div[@class='prodno']/label//text()"),
                            "name": self.extract_first(product_dom, ".//div[@class='prod-title']//text()"),
                            "description": "",
                            "url": self.BASE_URL + self.extract_first(product_dom, ".//a[@href]/@href"),
                            "images": [
                                {
                                    "image": self.extract_first(product_dom, ".//img[@class='card-img-top']/@src"),
                                }
                            ],
                            "price": price,
                            "retail_price": price,
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
        data = {}
        for i, product in enumerate(products):
            data[f"items[{i}][Sku]"] = product["product_id"]
            data[f"items[{i}][Quantity]"] = product["quantity"]
        await self.session.post(
            "https://www.darbydental.com/api/ShopCart/doAddToCart2", headers=CART_HEADERS, data=data
        )
        await self.session.get("https://www.darbydental.com/scripts/checkout.aspx", headers=REVIEW_CHECKOUT_HEADERS)
