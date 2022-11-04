import asyncio
import datetime
import json
import os
import re
import ssl
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TypedDict

from aiohttp import ClientResponse, ClientSession
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import catch_network, semaphore_coroutine
from apps.types.orders import CartProduct, VendorCartProduct
from apps.types.scraper import (
    InvoiceFile,
    LoginInformation,
    ProductSearch,
    SmartProductID,
)

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
    'Connection': 'keep-alive',
    'sec-ch-ua': '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-User': '?1',
    'Sec-Fetch-Dest': 'document',
    'Referer': 'https://shop.benco.com',
    'Accept-Language': 'en-US,en;q=0.9',
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
REMOVE_PRODUCT_CART_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "*/*",
    "X-Requested-With": "XMLHttpRequest",
    "Request-Context": "appId=cid-v1:c74c9cb3-54a4-4cfa-b480-a6dc8f0d3cdc",
    "Request-Id": "|/ZBP6.Z1DPB",
    "sec-ch-ua-platform": '"Windows"',
    "Origin": "https://shop.benco.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://shop.benco.com/Cart",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
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
CREATE_ORDER_HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Origin": "https://shop.benco.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://shop.benco.com/Cart",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}
CONFIRM_ORDER_HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Origin": "https://shop.benco.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

def textParser(element):
    if not element:
        return ''
    text = re.sub(r"\s+", " ", " ".join(element.xpath('.//text()').extract()))
    return text.strip() if text else ""
    
class CartProductDetail(TypedDict):
    product_id: str
    quantity: str
    name: str
    unit_price: Decimal
    total_price: Decimal
    item_id: str
    token: str


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
        await self.session.post(
            "https://shop.benco.com/signin-oidc", headers=headers, data=data, ssl=self._ssl_context
        )
        return True

    async def _after_login_hook(self, response: ClientResponse):
        pass

    @semaphore_coroutine
    async def get_order(self, sem, order_detail_link, referer, office=None) -> dict:
        headers = ORDER_DETAIL_HEADERS.copy()
        headers["Referer"] = referer

        order = {"products": []}
        async with self.session.get(f"{self.BASE_URL}{order_detail_link}", headers=headers, verify=False) as resp:
            response_dom = Selector(text=await resp.text())
            order["date"] = textParser(response_dom.xpath("//p[@class='order-details-summary']/span[1]"))
            order["date"] = order["date"].split("on", 1)[1].strip("| ") if "on" in order["date"] else None
            # order["purchase_id"] = textParser(response_dom.xpath("//p[@class='order-details-summary']/span[3]"))
            # order["purchase_id"] = order["purchase_id"].split("#", 1)[1].strip() if "#" in order["purchase_id"] else None

            # invoice_link = response_dom.xpath("//h3[contains(@class, 'pull-right')]/a/@href").get()
            # if invoice_link:
            #     order["invoice_link"] = f"{self.BASE_URL}{invoice_link}"
            order["order_id"] = textParser(response_dom.xpath("//p[@class='order-details-summary']/span[2]"))

            for order_container in response_dom.xpath("//div[contains(@class, 'order-container')]"):
                panel_heading = textParser(order_container.xpath("./div[@class='panel-heading']/h3[1]"))
                
                if not panel_heading:
                    
                    order["shipping_address"] = textParser(order_container.xpath(
                        ".//div[contains(@class, 'account-details-panel')]/div[2]/p"
                    ))
                    order["total_amount"] = textParser(order_container.xpath(
                        ".//div[contains(@class, 'account-details-panel')]/div[4]/p"
                    ))
                    order["status"] = textParser(order_container.xpath(
                        ".//div[contains(@class, 'account-details-panel')]/div[5]/p"
                    ))
                    order["currency"] = "USD"
                else:
                    for product_row in order_container.xpath("./ul[@class='list-group']/li[@class='list-group-item']"):
                        if product_row.xpath('.//h4'):
                            continue
                        product_id = textParser(product_row.xpath(
                            ".//div[contains(@class, 'product-details')]/p[contains(text(), 'Product #:')]"
                        ))
                        product_id = product_id.split("Product #:")[1].strip() if product_id else None
                        product_name =textParser(product_row.xpath(".//div[contains(@class, 'product-details')]/strong/a"))
                        product_url = product_row.xpath(".//div[contains(@class, 'product-details')]/strong/a/@href").get()
                        # product image is one in order history we try to fetch images on product detail
                        # product_images = product_row.xpath(".//img/@src").extract()
                        product_price = textParser(product_row.xpath(
                            ".//div[contains(@class, 'product-details')]/p[contains(text(), 'Net Price:')]"
                        ))
                        product_price = product_price.split("Net Price:")[1].strip() if product_price else None
                        quantity = textParser(product_row.xpath(
                            ".//div[contains(@class, 'product-details')]/p[contains(text(), 'Quantity:')]"
                        ))
                        quantity = quantity.split("Quantity:")[1].strip() if quantity else None
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
                                    "vendor": self.vendor.to_dict(),
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

        if office:
            await self.save_order_to_db(office, order=Order.from_dict(order))
        return order

    @catch_network
    async def get_orders(
        self,
        office=None,
        perform_login=False,
        from_date: Optional[datetime.date] = None,
        to_date: Optional[datetime.date] = None,
        completed_order_ids: Optional[List[str]] = None,
    ) -> List[Order]:
        sem = asyncio.Semaphore(value=2)
        url = f"{self.BASE_URL}/PurchaseHistory/NewIndex"
        if perform_login:
            await self.login()

        # TODO: pagination not tested

        if from_date and to_date:
            params = {
                "DateRangeOption": "CustomRange",
                "OrderStatus": "all",
                "PageNumber": 0,
                "StartDate": from_date.isoformat(),
                "EndDate": to_date.isoformat(),
            }
        else:
            params = {}

        async with self.session.get(url, headers=ORDER_HISTORY_HEADERS, params=params, ssl=self._ssl_context) as resp:
            url = str(resp.url)
            text = await resp.text()
            response_dom = Selector(text=text)
            tasks = []
            for order_detail_link in response_dom.xpath("//div[@class='order-history']//div[contains(@class, 'order-container')]/div[@class='panel-heading']//a[contains(@href, 'OrderDetail')]/@href").extract():
                if not order_detail_link: continue
                tasks.append(self.get_order(sem, order_detail_link, url, office))
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
                "vendor": self.vendor.to_dict(),
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
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price", office_id=None
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
                                "vendor_id": self.vendor.to_dict(),
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
                            "vendor": self.vendor.to_dict(),
                        }
                    )

        kwargs = {"Referer": url}
        product_prices = await self.get_product_prices([product["product_id"] for product in products], **kwargs)
        for product in products:
            product["price"] = product_prices[product["product_id"]]

        return {
            "vendor_slug": self.vendor.slug,
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": [Product.from_dict(product) for product in products],
            "last_page": page_size * page >= total_size,
        }

    def _get_vendor_categories(self, response) -> List[ProductCategory]:
        return [
            ProductCategory(
                name=category.xpath("./h4/text()").extract_first(),
                slug=category.attrib["href"].split("/")[-1],
            )
            for category in response.xpath("//div[@class='tab-header']/a")
        ]

    async def get_cart(self) -> Tuple[str, str, List[CartProductDetail]]:
        async with self.session.get("https://shop.benco.com/Cart", ssl=self._ssl_context) as resp:
            cart_page_dom = Selector(text=await resp.text())
            cart_id = cart_page_dom.xpath("//table[@id='cart_items_table']//tbody//input[@name='cartId']/@value").get()
            request_verification_token = cart_page_dom.xpath(
                "//table[@id='cart_items_table']//tbody//input[@name='__RequestVerificationToken']/@value"
            ).get()

            products = []
            for product_row in cart_page_dom.xpath("//table[@id='cart_items_table']/tbody[@class='cart-items']/tr"):
                product_row_classes = product_row.xpath("./@class").get()
                if not product_row_classes or "hidden" in product_row_classes:
                    continue

                product_id = product_row.xpath("./td[4]/a//text()").get()
                quantity = product_row.xpath("./td[3]//input[@name='Quantity']//@value").get()
                name = product_row.xpath("./td[5]/b//text()").get()
                unit_price = product_row.xpath("./td[7]//text()").get()
                total_price = product_row.xpath("./td[8]//text()").get()
                item_id = (item_id := product_row.xpath(".//input[@name='ItemId']/@value").get()) and item_id.strip()
                token = product_row.xpath(
                    ".//form[contains(@action, 'UpdateItemQuantity')]/input[@name='__RequestVerificationToken']/@value"
                ).get()

                products.append(
                    CartProductDetail(
                        product_id=product_id,
                        quantity=quantity,
                        name=name,
                        unit_price=unit_price,
                        total_price=total_price,
                        item_id=item_id,
                        token=token,
                    )
                )

            return cart_id, request_verification_token, products

    async def _add_product_to_cart(
        self, product: CartProduct, cart_id, request_verification_token
    ) -> VendorCartProduct:
        data = {
            "__RequestVerificationToken": request_verification_token,
            "cartId": cart_id,
            "searchId": "",
            "quantity": str(product["quantity"]),
            "prodNum": product["product_id"],
        }
        await self.session.post(
            "https://shop.benco.com/Cart/AddQOEItem", headers=ADD_CART_HEADERS, data=data, ssl=self._ssl_context
        )

    async def add_product_to_cart(self, product: CartProduct, perform_login=False) -> VendorCartProduct:
        if perform_login:
            await self.login()

        cart_id, request_verification_token, _ = await self.get_cart()
        await self._add_product_to_cart(product, cart_id, request_verification_token)
        _, _, cart_products = await self.get_cart()
        return [
            VendorCartProduct(product_id=cart_product["product_id"], unit_price=cart_product["unit_price"])
            for cart_product in cart_products
            if product["product_id"] == product["product_id"]
        ][0]

    async def add_products_to_cart(self, products: List[CartProduct]) -> List[VendorCartProduct]:
        cart_id, request_verification_token, _ = await self.get_cart()
        tasks = (self._add_product_to_cart(product, cart_id, request_verification_token) for product in products)
        await asyncio.gather(*tasks, return_exceptions=True)
        _, _, cart_products = await self.get_cart()
        return [
            VendorCartProduct(product_id=cart_product["product_id"], unit_price=cart_product["unit_price"])
            for cart_product in cart_products
        ]

    async def remove_product_from_cart(
        self, product_id: SmartProductID, perform_login: bool = False, use_bulk: bool = True
    ):
        if perform_login:
            await self.login()
        cart_id, request_verification_token, cart_products = await self.get_cart()
        product = [cart_product for cart_product in cart_products if cart_product["product_id"] == product_id][0]

        data = {"__RequestVerificationToken": product["token"], "ItemId": product["item_id"], "CartId": cart_id}

        await self.session.post(
            "https://shop.benco.com/Cart/RemoveItem",
            headers=REMOVE_PRODUCT_CART_HEADERS,
            data=data,
            ssl=self._ssl_context,
        )

    async def clear_cart(self):
        cart_id, _, _ = await self.get_cart()
        params = {
            "cartId": cart_id,
        }

        await self.session.get(
            "https://shop.benco.com/Cart/RemoveAllItems",
            headers=CLEAR_CART_HEADERS,
            params=params
        )

    async def checkout(self) -> Tuple[str, str, VendorOrderDetail]:
        cart_id, request_verification_token, cart_products = await self.get_cart()
        params = {
            "cartId": cart_id,
        }

        async with self.session.get(
            "https://shop.benco.com/Checkout/BeginCheckout",
            params=params,
            headers=CREATE_ORDER_HEADERS,
            ssl=self._ssl_context,
        ) as resp:
            text = await resp.text()
            response_dom = Selector(text=text)

        async with self.session.get(
            f"https://shop.benco.com/Cart/TaxesAndFees/{cart_id}", ssl=self._ssl_context
        ) as resp:
            cart_status_dom = Selector(text=await resp.text())
            # billing_address = self.merge_strip_values(response_dom, "//fieldset[contains(@class, 'bill-to')]/text()")
            shipping_address = self.merge_strip_values(response_dom, "//fieldset[contains(@class, 'ship-to')]/text()")
            # shipping_method = self.merge_strip_values(
            #     response_dom, "//fieldset[contains(@class, 'shipping-method')]/text()"
            # )
            payment_method = self.merge_strip_values(
                response_dom, "//fieldset[contains(@class, 'payment-method')]/text()"
            )
            subtotal_amount = self.remove_thousands_separator(
                self.extract_first(cart_status_dom, "//th[@id='item_subtotal_value']/p/text()")
            )
            shipping_amount = self.remove_thousands_separator(
                self.extract_first(cart_status_dom, "//tr[3]/td[last()]//text()")
            )
            tax_amount = self.remove_thousands_separator(
                self.extract_first(cart_status_dom, "//tr[4]/td[last()]//text()")
            )
            savings_amount = self.remove_thousands_separator(
                self.extract_first(cart_status_dom, "//tr[5]/td[last()]//text()")
            )
            total_amount = self.remove_thousands_separator(
                self.extract_first(cart_status_dom, "//tr[last()]/th[last()]/p/text()")
            )
            return (
                cart_id,
                request_verification_token,
                VendorOrderDetail(
                    retail_amount=Decimal(0),
                    savings_amount=Decimal(savings_amount),
                    subtotal_amount=Decimal(subtotal_amount),
                    shipping_amount=Decimal(shipping_amount),
                    tax_amount=Decimal(tax_amount),
                    total_amount=Decimal(total_amount),
                    payment_method=payment_method,
                    shipping_address=shipping_address,
                ),
            )

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        try:
            await self.login()
            await self.clear_cart()
            await self.add_products_to_cart(products)
            _, _, vendor_order_detail = await self.checkout()
        except:
            print("Benco/create_order except")
            subtotal_manual = sum([prod['price'] for prod in products])
            vendor_order_detail =VendorOrderDetail(
                retail_amount=Decimal(0),
                savings_amount=Decimal(0),
                subtotal_amount=Decimal(subtotal_manual),
                shipping_amount=Decimal(0),
                tax_amount=Decimal(0),
                total_amount=Decimal(subtotal_manual),
                payment_method="",
                shipping_address="",
            )
        finally:
            vendor_slug: str = self.vendor.slug
            return {
                vendor_slug: {
                    **vendor_order_detail.to_dict(),
                    **self.vendor.to_dict(),
                },
            }

    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
        self.backsession = self.session
        self.session = ClientSession()
        try:
            await self.login()
            await self.clear_cart()
            await self.add_products_to_cart(products)
            cart_id, request_verification_token, vendor_order_detail = await self.checkout()
            if fake:
                await self.session.close()
                self.session = self.backsession
                return {
                    **vendor_order_detail.to_dict(),
                    "order_id": f"{uuid.uuid4()}",
                }
            data = {"__RequestVerificationToken": request_verification_token}
            headers = CONFIRM_ORDER_HEADERS.copy()
            headers["Referer"] = f"https://shop.benco.com/Checkout/BeginCheckout?cartId={cart_id}"
            async with self.session.post(
                "https://shop.benco.com/Checkout/Confirm", headers=headers, data=data
            ) as resp:
                response_dom = Selector(text=await resp.text())
                order_id = response_dom.xpath("//h4//span[@class='alt-dark-text']//text()").get()
                await self.session.close()
                self.session = self.backsession
                return {
                    **vendor_order_detail.to_dict(),
                    "order_id": order_id,
                }
        except:
            print("benco/confirm_order Except")
            subtotal_manual = sum([prod['price'] for prod in products])
            vendor_order_detail =VendorOrderDetail(
                retail_amount=Decimal(0),
                savings_amount=Decimal(0),
                subtotal_amount=Decimal(subtotal_manual),
                shipping_amount=Decimal(0),
                tax_amount=Decimal(0),
                total_amount=Decimal(subtotal_manual),
                payment_method="",
                shipping_address="",
                order_type="Order Redundancy"
            )
            await self.session.close()
            self.session = self.backsession
            return {
                **vendor_order_detail.to_dict(),
                "order_id": f"{uuid.uuid4()}",
            }

    async def download_invoice(self, invoice_link, order_id) -> InvoiceFile:
        await self.login()
        async with self.session.get(invoice_link, ssl=self._ssl_context) as resp:
            return await resp.content.read()