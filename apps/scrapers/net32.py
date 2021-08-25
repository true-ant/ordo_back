from typing import List

from aiohttp import ClientResponse
from django.utils.dateparse import parse_datetime

from apps.scrapers.base import Scraper
from apps.scrapers.errors import OrderFetchException
from apps.scrapers.schema import Order
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
