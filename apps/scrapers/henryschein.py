import asyncio
import json
import re
from datetime import datetime
from typing import List

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product
from apps.types.scraper import LoginInformation

HEADERS = {
    "authority": "www.henryschein.com",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "n": "pikP/UtnnyEIsCZl3cphEgyUhacC9CnLZqSaDcvfufM=",
    "iscallingfromcms": "False",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",  # noqa
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://www.henryschein.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.henryschein.com/us-en/Profiles/Logout.aspx?redirdone=1",
    "accept-language": "en-US,en;q=0.9",
}

SEARCH_HEADERS = {
    "authority": "www.henryschein.com",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/92.0.4515.159 Safari/537.36",
    "accept": "text/html,application/xhtml+xml, application/xml;q=0.9, "
    "image/avif,image/webp,image/apng, */*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "sec-ch-ua-mobile": "?0",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-language": "en-US,en;q=0.9",
}


class HenryScheinScraper(Scraper):
    BASE_URL = "https://www.henryschein.com"

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return res.get("IsAuthenticated", False)

    async def _get_login_data(self) -> LoginInformation:
        return {
            "url": f"{self.BASE_URL}/webservices/LoginRequestHandler.ashx",
            "headers": HEADERS,
            "data": {
                "username": self.username,
                "password": self.password,
                "did": "dental",
                "searchType": "authenticateuser",
                "culture": "us-en",
            },
        }

    def extract_strip_value(self, dom, xpath, delimeter=""):
        return delimeter.join(filter(None, map(str.strip, dom.xpath(xpath).extract())))

    async def get_order(self, order_dom):
        link = order_dom.xpath("./td[8]/a/@href").extract_first().strip()
        order = {
            "total_amount": order_dom.xpath("./td[6]//text()").extract_first()[1:],
            "currency": "USD",
            "order_date": datetime.strptime(order_dom.xpath("./td[4]//text()").extract_first(), "%m/%d/%Y").date(),
            "status": order_dom.xpath("./td[7]//text()").extract_first(),
        }
        async with self.session.get(link) as resp:
            order_detail_response = Selector(text=await resp.text())
            order["order_id"] = (
                order_detail_response.xpath("//span[@id='ctl00_cphMainContent_referenceNbLbl']//text()").get().strip()
            )

            tasks = (
                self.get_product(
                    product_link=self.extract_strip_value(
                        dom=order_product_dom,
                        xpath="./td[1]//table[@id='tblProduct']//span[@class='ProductDisplayName']//a/@href",
                    ),
                    order_product_dom=order_product_dom,
                )
                for order_product_dom in order_detail_response.xpath(
                    "//table[contains(@class, 'tblOrderableProducts')]//tr//table[@class='SimpleList']//tr[@class='ItemRow' or @class='AlternateItemRow']"  # noqa
                )
            )

            order["products"] = await asyncio.gather(*tasks)

        return Order.from_dict(order)

    async def get_product(self, product_link, order_product_dom):
        async with self.session.get(product_link) as resp:
            res = Selector(text=await resp.text())
            product_detail = res.xpath("//script[@type='application/ld+json']//text()").extract_first()
            product_detail = json.loads(product_detail)

        quantity_price = self.extract_strip_value(
            dom=order_product_dom, xpath=".//td[@id='QtyRow']//text()", delimeter=";"
        )
        quantity, _, unit_price = quantity_price.split(";")
        unit_price = re.search(r"\$(.*)/", unit_price)

        status = self.extract_strip_value(
            dom=order_product_dom, xpath=".//span[contains(@id, 'itemStatusLbl')]//text()"
        )
        order_product = {
            "quantity": quantity,
            "unit_price": unit_price.group(1),
            "status": status,
            "product": {
                "product_id": product_detail["sku"],
                "name": product_detail["name"],
                "description": product_detail["description"],
                "url": product_detail["url"],
                "image": product_detail["image"],
                # "price": product_detail["price"],
                # "retail_price": product_detail["price"],
                # stars
                # ratings
            },
        }
        return order_product

    async def get_orders(self, perform_login=False):
        url = f"{self.BASE_URL}/us-en/Orders/OrderStatus.aspx"

        if perform_login:
            await self.login()

        async with self.session.get(url) as resp:
            text = await resp.text()
            response_dom = Selector(text=text)
            orders_dom = response_dom.xpath(
                "//table[@class='SimpleList']//tr[@class='ItemRow' or @class='AlternateItemRow']"
            )
            tasks = (self.get_order(order_dom) for order_dom in orders_dom)
            return await asyncio.gather(*tasks, return_exceptions=True)

    async def search_products(self, query: str, page: int = 1, per_page: int = 30) -> List[Product]:
        await self.login()
        url = f"{self.BASE_URL}/us-en/Search.aspx"
        params = {"searchkeyWord": query, "pagenumber": page}
        async with self.session.get(url, headers=SEARCH_HEADERS, params=params) as resp:
            response_dom = Selector(text=await resp.text())

        products = []
        for product_dom in response_dom.css("section.product-listing ol.products > li.product > .title"):
            product_detail = product_dom.xpath(".//script[@type='application/ld+json']//text()").extract_first()
            product_detail = json.loads(product_detail)
            products.append(
                Product(
                    product_id=product_detail["sku"],
                    name=product_detail["name"],
                    description=product_detail["description"],
                    url=product_detail["url"],
                    image=product_detail["image"],
                    price="",
                    retail_price="",
                )
            )

        return products
