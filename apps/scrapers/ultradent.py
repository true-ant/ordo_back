import asyncio

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order
from apps.types.scraper import LoginInformation

HEADERS = {
    "authority": "www.ultradent.com",
    "cache-control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "sec-ch-ua-mobile": "?0",
    "upgrade-insecure-requests": "1",
    "origin": "https://www.ultradent.com",
    "content-type": "application/x-www-form-urlencoded",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",  # noqa
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",  # noqa
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "referer": "https://www.ultradent.com/account",
    "accept-language": "en-US,en;q=0.9",
}

ORDER_HEADERS = {
    "authority": "www.ultradent.com",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "accept": "*/*",
    "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1bmlxdWVfbmFtZSI6ImluZm9AY29sdW1iaW5lY3JlZWtkZW50aXN0cnkuY29tIiwiaHR0cDovL3NjaGVtYXMubWljcm9zb2Z0LmNvbS93cy8yMDA4LzA2L2lkZW50aXR5L2NsYWltcy91c2VyZGF0YSI6IntcIkRhdGFcIjp7XCJVc2VySWRcIjoyMjg3NjUsXCJBY2NvdW50TnVtYmVyXCI6Mzk0NzYwLFwiVXNlckd1aWRcIjpcImZlZWUyYWZhLTM4YmMtNGIwOS1hYmY3LWY5YjcyNjMyNTUyMlwiLFwiRW1haWxcIjpcImluZm9AY29sdW1iaW5lY3JlZWtkZW50aXN0cnkuY29tXCIsXCJGaXJzdE5hbWVcIjpcIkFMRVhBTkRSQVwiLFwiU2FsZXNDaGFubmVsXCI6MX0sXCJVc2VyVHlwZVwiOjAsXCJSb2xlc1wiOltdLFwiUHJldmlld01vZGVcIjpmYWxzZX0iLCJuYmYiOjE2Mjk3ODkyNDEsImV4cCI6MTYyOTc5Mjg0MSwiaWF0IjoxNjI5Nzg5MjQxLCJpc3MiOiJodHRwczovL3d3dy51bHRyYWRlbnQuY29tIiwiYXVkIjoiaHR0cHM6Ly93d3cudWx0cmFkZW50LmNvbSJ9.aYwtN7JvDoZ8WeSJ1BkympQXlGgYpWuOtvTS0M2q2jM",  # noqa
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",  # noqa
    "content-type": "application/json",
    "origin": "https://www.ultradent.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.ultradent.com/account/order-history",
    "accept-language": "en-US,en;q=0.9",
}


class UltraDentScraper(Scraper):
    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.text()
        res_dom = Selector(text=res)
        return self.username == res_dom.xpath("//meta[@name='mUserName']/@content").get()

    async def _get_login_data(self) -> LoginInformation:
        url = "https://www.ultradent.com/login"
        async with self.session.get(url, headers=HEADERS) as resp:
            login_get_response_dom = Selector(text=await resp.text())
            token = login_get_response_dom.xpath("//input[@name='__RequestVerificationToken']/@value").get()

        return {
            "url": url,
            "headers": HEADERS,
            "data": {
                "Email": self.username,
                "Password": self.password,
                "__RequestVerificationToken": token,
            },
        }

    async def get_order(self, order):
        json_data = {
            "variables": {"orderNumber": order["orderNumber"]},
            "query": """
                query GetOrderDetailWithTrackingHtml($orderNumber: Int!) {
                    orderHtml(orderNumber: $orderNumber) {
                        orderDetailWithShippingHtml
                        __typename
                    }
                }
            """,
        }
        order["order_id"] = order["id"]
        order["status"] = order["orderStatus"]
        order["order_date"] = order["orderDate"]
        order["items"] = []
        async with self.session.post(
            "https://www.ultradent.com/api/ecommerce", headers=ORDER_HEADERS, json=json_data
        ) as resp:
            oder_html = (await resp.json())["data"]["orderHtml"]["orderDetailWithShippingHtml"]
            order_dom = Selector(text=oder_html)

            for order_detail in order_dom.xpath("//section[@class='order-details']/ul[@class='odr-line-list']/li"):
                order_item = dict()
                if order_detail.xpath("./@class").get() == "odr-line-header":
                    continue
                elif order_detail.xpath("./@class").get() == "odr-line-footer":
                    order["base_amount"] = self.extract_first(
                        order_detail, "//div[@class='subtotal']/span[contains(@class, 'value')]//text()"
                    )
                    order["shipping_amount"] = self.extract_first(
                        order_detail,
                        "//div[@class='shipping-total']/span[contains(@class, 'value')]//text()",
                    )
                    order["tax_amount"] = self.extract_first(
                        order_detail,
                        "//div[@class='tax']/span[contains(@class, 'value')]//text()",
                    )
                    order["total_amount"] = self.extract_first(
                        order_detail,
                        "//div[@class='odr-total']/span[contains(@class, 'value')]//text()",
                    )
                else:
                    order_item["name"] = self.extract_first(order_detail, "./span[@class='sku-product-name']//text()")
                    order_item["quantity"] = self.extract_first(order_detail, "./span[@class='sku-qty']//text()")
                    order_item["unit_price"] = self.extract_first(order_detail, "./span[@class='sku-price']//text()")
                    order["items"].append(order_item)

        return Order.from_dict(order)

    async def get_orders(self, perform_login=False):
        url = "https://www.ultradent.com/api/ecommerce"

        json_data = {
            "variables": {"numberOfDays": 546, "numberOfRows": 150},
            "query": """
                query GetOrderHeaders($numberOfDays: Int!, $numberOfRows: Int!) {
                    orders(numberOfDays: $numberOfDays, numberOfRows: $numberOfRows) {
                        id
                        orderGuid
                        orderNumber
                        poNumber
                        orderStatus
                        orderDate
                        shippingAddress {
                            id
                            __typename
                        }
                        __typename
                    }
                }
            """,
        }
        if perform_login:
            await self.login()

        async with self.session.post(url, headers=ORDER_HEADERS, json=json_data) as resp:
            orders_data = (await resp.json())["data"]["orders"]

            tasks = (self.get_order(order_data) for order_data in orders_data)
            return await asyncio.gather(*tasks, return_exceptions=True)
