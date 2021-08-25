import asyncio
from datetime import datetime

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order
from apps.types.scraper import LoginInformation

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


class DarbyScraper(Scraper):
    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return res["m_Item2"] and res["m_Item2"]["username"] == self.username

    async def _get_login_data(self) -> LoginInformation:
        return {
            "url": "https://www.darbydental.com/api/Login/Login",
            "headers": HEADERS,
            "data": {"username": self.username, "password": self.password, "next": ""},
        }

    def extract_strip_value(self, dom, xpath, delimeter=""):
        return delimeter.join(filter(None, map(str.strip, dom.xpath(xpath).extract())))

    async def get_order(self, order_dom):
        link = self.extract_strip_value(order_dom, "./td[1]/a/@href")
        order = {
            "id": self.extract_strip_value(order_dom, "./td[1]//text()"),
            "total_amount": self.extract_strip_value(order_dom, ".//td[8]//text()"),
            "currency": "USD",
            "order_date": datetime.strptime(
                self.extract_strip_value(order_dom, ".//td[2]//text()"), "%m/%d/%Y"
            ).date(),
        }
        async with self.session.get(f"https://www.darbydental.com/Scripts/{link}", headers=HEADERS) as resp:
            order_detail_response = Selector(text=await resp.text())
            order["items"] = []
            for detail_row in order_detail_response.xpath(
                "//table[@id='MainContent_gvInvoiceDetail']//tr[@class='pdpHelltPrimary']"  # noqa
            ):
                order["items"].append(
                    {
                        "name": self.extract_strip_value(detail_row, "./td[2]//text()"),
                        "quantity": self.extract_strip_value(detail_row, "./td[5]//text()"),
                        "unit_price": self.extract_strip_value(detail_row, "./td[4]//text()"),
                        # "status": status
                    }
                )

        return Order.from_dict(order)

    async def get_orders(self, perform_login=False):
        url = "https://www.darbydental.com/Scripts/InvoiceHistory.aspx"

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
