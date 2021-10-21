import asyncio
import datetime
import json
import os
import ssl
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Tuple, Union

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import catch_network
from apps.types.orders import CartProduct, VendorCartProduct
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
ADD_CART_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "*/*",
    "X-Requested-With": "XMLHttpRequest",
    "Request-Context": "appId=cid-v1:c74c9cb3-54a4-4cfa-b480-a6dc8f0d3cdc",
    "Request-Id": "|fpNl1.MtH9L",
    "sec-ch-ua-platform": '"Windows"',
    "Origin": "https://shop.benco.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://shop.benco.com/Cart",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}
CLEAR_CART_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.71 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://shop.benco.com/Cart",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}


class BencoScraper(Scraper):
    BASE_URL = "https://shop.benco.com"
    CATEGORY_URL = "https://shop.benco.com/Browse"

    def __init__(self, *args, **kwargs):
        self._ssl_context = ssl.create_default_context(
            cafile=os.path.join(CERTIFICATE_BASE_PATH, "certificates/benco.pem")
        )
        super().__init__(*args, **kwargs)

    async def _get_check_login_state(self) -> Tuple[bool, dict]:
        async with self.session.get(
            f"{self.BASE_URL}/Login/Login", headers=PRE_LOGIN_HEADERS, ssl=self._ssl_context
        ) as resp:
            text = await resp.text()
            url = str(resp.url)
            try:
                modelJson = (
                    text.split("id='modelJson'")[1]
                    .split("</script>", 1)[0]
                    .split(">", 1)[1]
                    .replace("&quot;", '"')
                    .strip()
                )
                idsrv_xsrf = json.loads(modelJson)["antiForgery"]["value"]
                return False, {"url": url, "idsrv_xsrf": idsrv_xsrf}
            except IndexError:
                return True, {}

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        headers = LOGIN_HEADERS.copy()
        url: str = kwargs.get("url")
        idsrv_xsrf = kwargs.get("idsrv_xsrf")
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

    @catch_network
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
                        product_id = other_details[0].split("#: ")[1]
                        product_name = product_row.xpath(
                            ".//div[contains(@class, 'product-details')]/strong/a//text()"
                        ).get()
                        product_url = product_row.xpath(
                            ".//div[contains(@class, 'product-details')]/strong/a/@href"
                        ).get()
                        product_url = f"{self.BASE_URL}{product_url}" if product_url else None
                        # product image is one in order history we try to fetch images on product detail
                        # product_images = product_row.xpath(".//img/@src").extract()
                        product_price = other_details[2].split(":")[1]
                        quantity = other_details[1].split(":")[1].strip()
                        order["products"].append(
                            {
                                "product": {
                                    "product_id": product_id,
                                    "name": product_name,
                                    "description": "",
                                    "url": product_url,
                                    "images": [],
                                    "category": "",
                                    "price": product_price,
                                    "vendor": self.vendor,
                                    # "images": [{"image": product_image for product_image in product_images}],
                                },
                                "unit_price": product_price,
                                "quantity": quantity,
                            }
                        )

        await self.get_missing_products_fields(
            order["products"],
            fields=(
                "description",
                "images",
                "category",
            ),
        )

        return order

    @catch_network
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

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        if perform_login:
            await self.login()

        async with self.session.get(product_url, ssl=self._ssl_context) as resp:
            res = Selector(text=await resp.text())
            product_name = self.extract_first(res, ".//h3[@class='product-name']/text()")
            product_description = self.extract_first(res, ".//p[@class='product-description']/text()")
            product_images = res.xpath(".//div[@class='thumbnail']/img/@src").extract()
            if not product_images:
                product_images = res.xpath(".//div[@id='activeImageArea']/img/@src").extract()

            product_price = self.extract_first(res, ".//div[@class='product-detail-actions-wrapper']/h3/text()")
            product_category = res.xpath(".//div[@class='breadcrumb-bar']/ul/li/a/text()").extract()[1:]
            return {
                "product_id": product_id,
                "name": product_name,
                "description": product_description,
                "url": product_url,
                "images": [{"image": product_image} for product_image in product_images],
                "category": product_category,
                "price": product_price,
                "vendor": self.vendor,
            }

    async def get_product_prices(self, product_ids, perform_login=False, **kwargs) -> Dict[str, Decimal]:
        if perform_login:
            await self.login()

        product_prices = {}
        data = {"productNumbers": product_ids, "pricePartialType": "ProductPriceRow"}
        headers = PRICE_SEARCH_HEADERS.copy()
        headers["Referer"] = kwargs.get("Referer")
        async with self.session.post(
            "https://shop.benco.com/Search/GetPricePartialsForProductNumbers",
            headers=headers,
            json=data,
            ssl=self._ssl_context,
        ) as resp:
            res = await resp.json()
            for product_id, row in res.items():
                row_dom = Selector(text=row)
                product_prices[product_id] = row_dom.xpath("//h4[@class='selling-price']").attrib["content"]
        return product_prices

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
        products = []
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
                additional_products = product_dom.xpath(".//div[contains(@class, 'additional-products')]")
                if additional_products:
                    product_image = product_dom.xpath(".//div[contains(@class, 'summary-row')]//img/@src").get()
                    product_description = self.extract_first(product_dom, ".//p[@class='description']/text()")
                    for additional_product in additional_products.xpath(".//tr"):
                        product_id = self.extract_first(additional_product, ".//td[@itemprop='sku']/text()")
                        name = self.extract_first(additional_product, ".//td[@class='product-name']/span/text()")
                        product_url = additional_product.attrib["data-click-href"]
                        product_url = f"{self.BASE_URL}{product_url}" if product_url else None
                        products.append(
                            {
                                "product_id": product_id,
                                "name": name,
                                "description": product_description,
                                "url": product_url,
                                "images": [
                                    {
                                        "image": product_image,
                                    }
                                ],
                                "price": Decimal(0),
                                "vendor_id": self.vendor,
                            }
                        )
                else:
                    product_id = self.extract_first(
                        product_dom, "./div[contains(@class, 'product-data-area')]//span[@itemprop='sku']//text()"
                    )
                    product_url = self.extract_first(
                        product_dom,
                        "./div[contains(@class, 'product-data-area')]/div[contains(@class, 'title')]//a/@href",
                    )
                    product_url = f"{self.BASE_URL}{product_url}" if product_url else None
                    name = self.extract_first(
                        product_dom, "./div[contains(@class, 'product-data-area')]//h4[@itemprop='name']//text()"
                    )
                    product_image = product_dom.xpath("./div[contains(@class, 'product-image-area')]/img/@src").get()
                    product_description = self.extract_first(product_dom, ".//p/text()")
                    products.append(
                        {
                            "product_id": product_id,
                            "name": name,
                            "description": product_description,
                            "url": product_url,
                            "images": [
                                {
                                    "image": product_image,
                                }
                            ],
                            "price": Decimal(0),
                            "vendor": self.vendor,
                        }
                    )

        kwargs = {"Referer": url}
        product_prices = await self.get_product_prices([product["product_id"] for product in products], **kwargs)
        for product in products:
            product["price"] = product_prices[product["product_id"]]

        return {
            "vendor_slug": self.vendor["slug"],
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": [Product.from_dict(product) for product in products],
            "last_page": page_size * page >= total_size,
        }

    async def checkout(self, products: List[CartProduct]):
        pass

    def _get_vendor_categories(self, response) -> List[ProductCategory]:
        return [
            ProductCategory(
                name=category.xpath("./h4/text()").extract_first(),
                slug=category.attrib["href"].split("/")[-1],
            )
            for category in response.xpath("//div[@class='tab-header']/a")
        ]

    async def add_product_to_cart(self, product: CartProduct) -> VendorCartProduct:
        async with self.session.get("https://shop.benco.com/Cart", ssl=self._ssl_context) as resp:
            cart_page_dom = Selector(text=await resp.text())

        cart_id = cart_page_dom.xpath("//table[@id='cart_items_table']//tbody//input[@name='cartId']/@value").get()
        request_verification_token = cart_page_dom.xpath(
            "//table[@id='cart_items_table']//tbody//input[@name='__RequestVerificationToken']/@value"
        ).get()

        data = {
            "__RequestVerificationToken": request_verification_token,
            "cartId": cart_id,
            "searchId": "",
            "quantity": str(product["quantity"]),
            "prodNum": product["product_id"],
        }
        async with self.session.post(
            "https://shop.benco.com/Cart/AddQOEItem", headers=ADD_CART_HEADERS, data=data
        ) as resp:
            text = await resp.text()
            dom = Selector(text=text)
            return {"product_id": product["product_id"], "unit_price": ""}

    async def add_products_to_cart(self, products: List[CartProduct]) -> List[VendorCartProduct]:
        raise NotImplementedError("Vendor scraper must implement `add_products_to_cart`")

    async def remove_product_from_cart(self, product_id: Union[str, int], use_bulk: bool = True):
        raise NotImplementedError("Vendor scraper must implement `remove_product_from_cart`")

    async def clear_cart(self):
        async with self.session.get("https://shop.benco.com/Cart", ssl=self._ssl_context) as resp:
            cart_page_dom = Selector(text=await resp.text())
            cart_id = cart_page_dom.xpath("//table[@id='cart_items_table']//tbody//input[@name='cartId']/@value").get()
            params = {
                "cartId": cart_id,
            }

        await self.session.get("https://shop.benco.com/Cart/RemoveAllItems", headers=CLEAR_CART_HEADERS, params=params)

    async def create_order(self, products: List[CartProduct]) -> Dict[str, VendorOrderDetail]:
        raise NotImplementedError("Vendor scraper must implement `create_order`")

    async def confirm_order(self, products: List[CartProduct]):
        raise NotImplementedError("Vendor scraper must implement `confirm_order`")
