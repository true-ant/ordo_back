import asyncio
import re
from datetime import datetime

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order
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


class HenryScheinScraper(Scraper):
    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return res.get("IsAuthenticated", False)

    def _get_login_data(self, username: str, password: str) -> LoginInformation:
        return {
            "url": "https://www.henryschein.com/webservices/LoginRequestHandler.ashx",
            "headers": HEADERS,
            "data": {
                "username": username,
                "password": password,
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
            order["id"] = (
                order_detail_response.xpath("//span[@id='ctl00_cphMainContent_referenceNbLbl']//text()").get().strip()
            )
            order["items"] = []
            for detail_row in order_detail_response.xpath(
                "//table[contains(@class, 'tblOrderableProducts')]//tr//table[@class='SimpleList']//tr[@class='ItemRow' or @class='AlternateItemRow']"  # noqa
            ):
                item_name = self.extract_strip_value(
                    dom=detail_row,
                    xpath="./td[1]//table[@id='tblProduct']//span[@class='ProductDisplayName']//text()",
                )
                quantity_price = self.extract_strip_value(
                    dom=detail_row, xpath="./td[@colspan='4']//table//tr[1]//td[1]//text()", delimeter=";"
                )
                quantity, _, unit_price = quantity_price.split(";")
                unit_price = re.search(r"\$(.*)/", unit_price)

                status = self.extract_strip_value(
                    dom=detail_row, xpath="./td[@colspan='4']//table//tr[1]//td[3]//text()"
                )
                order["items"].append(
                    {"name": item_name, "quantity": quantity, "unit_price": unit_price.group(1), "status": status}
                )

        return Order.from_dict(order)

    async def get_orders(self):
        url = "https://www.henryschein.com/us-en/Orders/OrderStatus.aspx"

        async with self.session.get(url) as resp:
            text = await resp.text()
            response_dom = Selector(text=text)
            orders_dom = response_dom.xpath(
                "//table[@class='SimpleList']//tr[@class='ItemRow' or @class='AlternateItemRow']"
            )
            tasks = (self.get_order(order_dom) for order_dom in orders_dom)
            return await asyncio.gather(*tasks, return_exceptions=True)
