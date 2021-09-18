import asyncio
import datetime
import json
import os
import ssl
from pathlib import Path
from typing import List

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product
from apps.types.orders import CartProduct
from apps.types.scraper import LoginInformation, ProductSearch

CERTIFICATE_BASE_PATH = Path(__file__).parent.resolve()

PRE_LOGIN_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}
LOGIN_HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Origin": "https://identity.benco.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}
SEARCH_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.benco.com/",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}
PRICE_SEARCH_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
    "sec-ch-ua-platform": '"Windows"',
    "Origin": "https://shop.benco.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}
ORDER_HISTORY_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://shop.benco.com",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}
ORDER_DETAIL_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}


class BencoScraper(Scraper):
    BASE_URL = "https://shop.benco.com"

    def __init__(self, *args, **kwargs):
        self._ssl_context = ssl.create_default_context(
            cafile=os.path.join(CERTIFICATE_BASE_PATH, "certificates/benco.pem")
        )
        super().__init__(*args, **kwargs)

    async def _get_login_data(self) -> LoginInformation:
        async with self.session.get(
            f"{self.BASE_URL}/Login/Login", headers=PRE_LOGIN_HEADERS, ssl=self._ssl_context
        ) as resp:
            text = await resp.text()
            url = str(resp.url)
            modelJson = (
                text.split("id='modelJson'")[1]
                .split("</script>", 1)[0]
                .split(">", 1)[1]
                .replace("&quot;", '"')
                .strip()
            )
            idsrv_xsrf = json.loads(modelJson)["antiForgery"]["value"]
            headers = LOGIN_HEADERS.copy()
            headers["Referer"] = url
            return {
                "url": url,
                "headers": headers,
                "data": {
                    "idsrv.xsrf": idsrv_xsrf,
                    "username": self.username,
                    "password": self.password,
                },
            }

    async def _check_authenticated(self, resp: ClientResponse) -> bool:
        response_dom = Selector(text=await resp.text())
        id_token = response_dom.xpath("//input[@name='id_token']/@value").get()
        scope = response_dom.xpath("//input[@name='scope']/@value").get()
        state = response_dom.xpath("//input[@name='state']/@value").get()
        session_state = response_dom.xpath("//input[@name='session_state']/@value").get()
        if not any([id_token, scope, state, session_state]):
            return False

        headers = {
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
            "Origin": "https://identity.benco.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://identity.benco.com/",
            "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
        }

        data = {"id_token": id_token, "scope": scope, "state": state, "session_state": session_state}
        await self.session.post(self.BASE_URL, headers=headers, data=data, ssl=self._ssl_context)
        return True

    async def _after_login_hook(self, response: ClientResponse):
        pass

    async def get_order(self, order_link, referer) -> dict:
        headers = ORDER_DETAIL_HEADERS.copy()
        headers["Referer"] = referer

        order = {"products": []}
        async with self.session.get(f"{self.BASE_URL}/{order_link}", headers=headers, ssl=self._ssl_context) as resp:
            response_dom = Selector(text=await resp.text())
            order_date = (
                response_dom.xpath("//p[@class='order-details-summary']/span[1]/text()")
                .get()
                .split("on", 1)[1]
                .strip()
            )
            order["order_date"] = datetime.datetime.strptime(order_date, "%B %d, %Y").date()
            order["order_id"] = (
                response_dom.xpath("//p[@class='order-details-summary']/span[2]/text()").get().split("#", 1)[1].strip()
            )

            for row in response_dom.xpath("//div[contains(@class, 'order-container')]"):
                panel_heading = row.xpath("./div[@class='panel-heading']/h3//text()").get()
                panel_heading = panel_heading.strip() if panel_heading else None
                if panel_heading is None:
                    addresses = row.xpath(
                        ".//div[contains(@class, 'account-details-panel')]/div[2]/p//text()"
                    ).extract()

                    _, codes = addresses[-1].replace("\r\n", "").split(",")
                    codes = codes.replace(" ", "")
                    order["shipping_address"] = {
                        "address": " ".join(addresses[:-1]),
                        "region_code": codes[:2],
                        "postal_code": codes[2:],
                    }
                    order["total_amount"] = self.merge_strip_values(
                        row, ".//div[contains(@class, 'account-details-panel')]/div[4]/p//text()"
                    )
                    order["status"] = self.merge_strip_values(
                        row, ".//div[contains(@class, 'account-details-panel')]/div[5]/p//text()"
                    )
                    order["currency"] = "USD"
                else:
                    for product_row in row.xpath("./ul[@class='list-group']/li[@class='list-group-item']"):
                        other_details = product_row.xpath(".//p/text()").extract()

                        order["products"].append(
                            {
                                "product": {
                                    "product_id": other_details[0].split("#: ")[1],
                                    "name": product_row.xpath(
                                        ".//div[contains(@class, 'product-details')]/strong/a//text()"
                                    ).get(),
                                    "description": "",
                                    "url": self.BASE_URL
                                    + product_row.xpath(
                                        ".//div[contains(@class, 'product-details')]/strong/a/@href"
                                    ).get(),
                                    "image": product_row.xpath(".//img/@src").get(),
                                    "price": other_details[2].split(":")[1],
                                    "retail_price": "",
                                    "vendor_id": self.vendor_id,
                                },
                                "quantity": other_details[1].split(":")[1].strip(),
                                "unit_price": other_details[2].split(":")[1],
                            }
                        )
        return order

    async def get_orders(self, perform_login=False) -> List[Order]:
        url = f"{self.BASE_URL}/PurchaseHistory"
        if perform_login:
            await self.login()

        async with self.session.get(url, headers=ORDER_HISTORY_HEADERS, ssl=self._ssl_context) as resp:
            url = str(resp.url)
            response_dom = Selector(text=await resp.text())
            orders_links = response_dom.xpath(
                "//div[@class='order-history']"
                "//div[contains(@class, 'order-container')]/div[@class='panel-heading']//a/@href"
            ).extract()
            tasks = (self.get_order(order_link, url) for order_link in orders_links)
            orders = await asyncio.gather(*tasks, return_exceptions=True)
            return [Order.from_dict(order) for order in orders if isinstance(order, dict)]

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        page_size = 24
        data = {
            "Page": str(page),
            "Terms": query,
            "SortBy": "",
            "GroupSimilarItems": "True",
            "PromoKey": "",
            "ProductLine": "",
            "IsCompleteCart": "False",
            "IsGeneralSuggestion": "False",
            "Source": "",
            "ShowResultsAsGrid": "False",
        }
        products = {}
        product_ids = []
        async with self.session.post(
            f"{self.BASE_URL}/Search/ChangePage", headers=SEARCH_HEADERS, data=data, ssl=self._ssl_context
        ) as resp:
            url = str(resp.url)
            response_dom = Selector(text=await resp.text())
            total_size = int(
                response_dom.xpath("//ul[contains(@class, 'search-breadcrumbs')]/li[last()]//h6//text()")
                .get()
                .split("of", 1)[1]
                .strip()
            )
            products_dom = response_dom.xpath("//div[@class='product-list']/div[contains(@class, 'product-row')]")
            for product_dom in products_dom:
                product_id = self.extract_first(
                    product_dom, "./div[contains(@class, 'product-data-area')]//span[@itemprop='sku']//text()"
                )
                product_ids.append(product_id)
                products[product_id] = {
                    "product_id": product_id,
                    "name": self.extract_first(
                        product_dom, "./div[contains(@class, 'product-data-area')]//h4[@itemprop='name']//text()"
                    ),
                    "description": "",
                    "url": self.BASE_URL
                    + self.extract_first(
                        product_dom,
                        "./div[contains(@class, 'product-data-area')]/div[contains(@class, 'title')]//a/@href",
                    ),
                    "image": product_dom.xpath("./div[contains(@class, 'product-image-area')]/img/@src").get(),
                    "price": "",
                    "retail_price": "",
                    "vendor_id": self.vendor_id,
                }
        data = {"productNumbers": product_ids, "pricePartialType": "ProductPriceRow"}
        headers = PRICE_SEARCH_HEADERS.copy()
        headers["Referer"] = url
        async with self.session.post(
            "https://shop.benco.com/Search/GetPricePartialsForProductNumbers",
            headers=headers,
            json=data,
            ssl=self._ssl_context,
        ) as resp:
            res = await resp.json()
            for product_id, row in res.items():
                row_dom = Selector(text=row)

                products[product_id]["price"] = row_dom.xpath("//h4[@class='selling-price']").attrib["content"]

        return {
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": [Product.from_dict(product) for _, product in products.items()],
            "last_page": page_size * page >= total_size,
        }

    async def checkout(self, products: List[CartProduct]):
        pass