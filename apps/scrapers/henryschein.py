import asyncio
import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Dict, List

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product, ProductCategory
from apps.scrapers.utils import catch_network
from apps.types.scraper import LoginInformation, ProductSearch

HEADERS = {
    "authority": "www.henryschein.com",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "n": "pikP/UtnnyEIsCZl3cphEgyUhacC9CnLZqSaDcvfufM=",
    "iscallingfromcms": "False",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
    # noqa
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
    CATEGORY_URL = "https://www.henryschein.com/us-en/dental/c/browsesupplies"

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return res.get("IsAuthenticated", False)

    async def _get_login_data(self) -> LoginInformation:
        async with self.session.get("https://www.henryschein.com/us-en/dental/Default.aspx") as resp:
            text = await resp.text()
            n = text.split("var _n =")[1].split(";")[0].strip(" '")
        self.session.headers.update({"n": n})
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

    async def get_order(self, order_dom):
        link = order_dom.xpath("./td[8]/a/@href").extract_first().strip()
        order = {
            "total_amount": order_dom.xpath("./td[6]//text()").extract_first()[1:],
            "currency": "USD",
            "order_date": datetime.strptime(order_dom.xpath("./td[4]//text()").extract_first(), "%m/%d/%Y").date(),
            "status": order_dom.xpath("./td[7]//text()").extract_first(),
            "products": [],
        }
        async with self.session.get(link) as resp:
            order_detail_response = Selector(text=await resp.text())
            order["order_id"] = (
                order_detail_response.xpath("//span[@id='ctl00_cphMainContent_referenceNbLbl']//text()").get().strip()
            )
            addresses = order_detail_response.xpath(
                "//span[@id='ctl00_cphMainContent_ucShippingAddr_lblAddress']//text()"
            ).extract()
            _, codes = addresses[-2].split(",")
            region_code, postal_code = codes.strip().split(" ")
            order["shipping_address"] = {
                "address": addresses[1],
                "region_code": region_code,
                "postal_code": postal_code,
            }

            for order_product_dom in order_detail_response.xpath(
                "//table[contains(@class, 'tblOrderableProducts')]//tr"
                "//table[@class='SimpleList']//tr[@class='ItemRow' or @class='AlternateItemRow']"
            ):
                product_name_url_dom = order_product_dom.xpath(
                    "./td[1]//table[@id='tblProduct']//span[@class='ProductDisplayName']"
                )
                product_id = self.extract_first(order_product_dom, ".//b/text()")
                product_name = self.extract_first(product_name_url_dom, ".//a/text()")
                product_url = self.merge_strip_values(product_name_url_dom, xpath=".//a/@href")
                quantity_price = self.merge_strip_values(
                    dom=order_product_dom, xpath=".//td[@id='QtyRow']//text()", delimeter=";"
                )
                quantity, _, product_price = quantity_price.split(";")
                product_price = re.search(r"\$(.*)/", product_price)
                product_price = product_price.group(1)

                status = self.merge_strip_values(
                    dom=order_product_dom, xpath=".//span[contains(@id, 'itemStatusLbl')]//text()"
                )
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
                        },
                        "quantity": quantity,
                        "unit_price": product_price,
                        "status": status,
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

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        if perform_login:
            await self.login()

        async with self.session.get(product_url) as resp:
            res = Selector(text=await resp.text())
            product_detail = res.xpath(".//ul[@id='ctl00_cphMainContentHarmony_ucProductSummary_ulProductSummary']")
            product_name = self.extract_first(product_detail, ".//h2[contains(@class, 'product-title')]/text()")
            product_description = self.extract_first(res, ".//li[@class='customer-notes']/div[@class='value']/text()")
            product_images = res.xpath(
                ".//div[@id='ctl00_cphMainContentHarmony_ucProductAssets_divImgProduct']/img/@src"
            ).extract()
            product_price = self.extract_first(
                res,
                ".//li[@id='ctl00_cphMainContentHarmony_ucProductSummary_ucPackagingOptions"
                "_rptProductList_ctl00_liProductAction']//span[contains(@class, 'amount')]/text()",
            )
            product_price = re.findall("\\d+\\.\\d+", product_price)
            product_price = product_price[0] if isinstance(product_price, list) else None
            product_category = res.xpath(
                ".//div[contains(@class, 'product-image')]/ul/li/div[@class='value']/span/text()"
            ).extract()

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

    @catch_network
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
            tasks = (self.get_order(order_dom) for order_dom in orders_dom[:1])
            orders = await asyncio.gather(*tasks, return_exceptions=True)

        return [Order.from_dict(order) for order in orders if isinstance(order, dict)]

    async def get_product_prices(self, product_ids, perform_login=False, **kwargs) -> Dict[str, Decimal]:
        if perform_login:
            await self.login()

        product_units = kwargs.get("product_units")
        products_price_data = [
            {
                "ProductId": int(product_id),
                "Qty": "1",
                "Uom": product_unit,
                "PromoCode": "",
                "CatalogName": "B_DENTAL",
                "ForceUpdateInventoryStatus": False,
                "AvailabilityCode": "01",
            }
            for product_id, product_unit in zip(product_ids, product_units)
        ]

        products_price_data = {
            "ItemArray": json.dumps(
                {
                    "ItemDataToPrice": products_price_data,
                }
            ),
            "searchType": "6",
            "did": "dental",
            "catalogName": "B_DENTAL",
            "endecaCatalogName": "DENTAL",
            "culture": "us-en",
            "showPriceToAnonymousUserFromCMS": "False",
            "isCallingFromCMS": "False",
        }

        headers = SEARCH_HEADERS.copy()
        headers["referer"] = kwargs.get("Referer")
        product_prices = {}
        async with self.session.post(
            "https://www.henryschein.com/webservices/JSONRequestHandler.ashx",
            data=products_price_data,
            headers=headers,
        ) as resp:
            res = await resp.json()
            for product_price in res["ItemDataToPrice"]:
                product_prices[product_price["ProductId"]] = product_price["CustomerPrice"]
        return product_prices

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        url = f"{self.BASE_URL}/us-en/Search.aspx"
        page_size = 25
        params = {"searchkeyWord": query, "pagenumber": page}

        async with self.session.get(url, headers=SEARCH_HEADERS, params=params) as resp:
            response_dom = Selector(text=await resp.text())

        total_size_str = response_dom.xpath(".//span[@class='result-count']/text()").extract_first()
        try:
            total_size = int(total_size_str)
        except ValueError:
            total_size = 0
        products = []
        for product_dom in response_dom.css("section.product-listing ol.products > li.product > .title"):
            product_detail = product_dom.xpath(".//script[@type='application/ld+json']//text()").extract_first()
            product_unit = self.merge_strip_values(
                product_dom,
                "./ul[@class='product-actions']"
                "//div[contains(@class, 'color-label-gray')]/span[contains(@class, 'block')]//text()",
            )
            product_detail = json.loads(product_detail)
            products.append(
                {
                    "product_id": product_detail["sku"],
                    "product_unit": product_unit,
                    "name": product_detail["name"],
                    "description": product_detail["description"],
                    "url": product_detail["url"],
                    "images": [
                        {
                            "image": product_detail["image"],
                        }
                    ],
                    "price": Decimal(0),
                    "vendor": self.vendor,
                }
            )

        kwargs = {
            "Referer": f"https://www.henryschein.com/us-en/Search.aspx?searchkeyWord={query}",
            "product_units": [product["product_unit"] for product in products],
        }
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

    def _get_vendor_categories(self, response) -> List[ProductCategory]:
        return [
            ProductCategory(
                name=category.attrib["title"],
                slug=category.attrib["href"].split("/")[-1],
            )
            for category in response.xpath("//ul[contains(@class, 'hs-categories')]/li/a")
        ]
