import asyncio
import re
from datetime import datetime
from typing import List, Optional

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product, ProductCategory
from apps.scrapers.utils import catch_network, semaphore_coroutine
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
    CATEGORY_URL = "https://www.darbydental.com/scripts/Categories.aspx"

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return res["m_Item2"] and res["m_Item2"]["username"] == self.username

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        return {
            "url": f"{self.BASE_URL}/api/Login/Login",
            "headers": HEADERS,
            "data": {"username": self.username, "password": self.password, "next": ""},
        }

    async def get_shipping_track(self, order, order_id):
        async with self.session.get(
            f"{self.BASE_URL}/Scripts/InvoiceTrack.aspx?invno={order_id}", headers=HEADERS
        ) as resp:
            try:
                track_response_dom = Selector(text=await resp.text())
                tracking_dom = track_response_dom.xpath(
                    "//table[contains(@id, 'MainContent_rpt_gvInvoiceTrack_')]//tr[@class='pdpHelltPrimary']"
                )[0]
                order["status"] = self.extract_first(tracking_dom, "./td[4]//text()")
            except IndexError:
                order["status"] = "Unknown"

    async def get_order_products(self, order, link):
        async with self.session.get(f"{self.BASE_URL}/Scripts/{link}", headers=HEADERS) as resp:
            order_detail_response = Selector(text=await resp.text())
            order["products"] = []
            for detail_row in order_detail_response.xpath(
                "//table[@id='MainContent_gvInvoiceDetail']//tr[@class='pdpHelltPrimary']"  # noqa
            ):
                product_id = self.merge_strip_values(detail_row, "./td[1]/a//text()")
                product_name = self.merge_strip_values(detail_row, "./td[2]//text()")
                product_url = self.merge_strip_values(detail_row, "./td[1]/a//@href")
                if product_url:
                    product_url = f"{self.BASE_URL}{product_url}"

                product_image = self.merge_strip_values(detail_row, "./td[1]/input//@src")
                product_image = f"{self.BASE_URL}{product_image}" if product_image else None
                product_price = self.merge_strip_values(detail_row, "./td[4]//text()")
                quantity = self.merge_strip_values(detail_row, "./td[5]//text()")
                order["products"].append(
                    {
                        "product": {
                            "product_id": product_id,
                            "name": product_name,
                            "description": "",
                            "url": product_url,
                            "category": "",
                            "images": [{"image": product_image}],
                            "price": product_price,
                            "vendor": self.vendor.to_dict(),
                        },
                        "unit_price": product_price,
                        "quantity": quantity,
                    }
                )
        await self.get_missing_products_fields(
            order["products"],
            fields=(
                "description",
                # "images",
                "category",
            ),
        )
        return order

    @semaphore_coroutine
    async def get_order(self, sem, order_dom, order_date: Optional[datetime.date] = None, office=None):
        link = self.merge_strip_values(order_dom, "./td[1]/a/@href")
        order_id = self.merge_strip_values(order_dom, "./td[1]//text()")
        invoice_link = self.merge_strip_values(order_dom, "./td[9]/a/@href")
        order = {
            "order_id": order_id,
            "total_amount": self.merge_strip_values(order_dom, ".//td[8]//text()"),
            "currency": "USD",
            "order_date": order_date
            if order_date
            else datetime.strptime(self.merge_strip_values(order_dom, ".//td[2]//text()"), "%m/%d/%Y").date(),
            "invoice_link": f"{self.BASE_URL}{invoice_link}",
        }
        await asyncio.gather(self.get_order_products(order, link), self.get_shipping_track(order, order_id))

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
        url = f"{self.BASE_URL}/Scripts/InvoiceHistory.aspx"

        if perform_login:
            await self.login()

        orders = []
        async with self.session.get(url, headers=HEADERS) as resp:
            text = await resp.text()
            response_dom = Selector(text=text)
            orders_dom = response_dom.xpath(
                "//table[@id='MainContent_gvInvoiceHistory']//tr[@class='pdpHelltPrimary']"
            )
            tasks = []
            for order_dom in orders_dom:
                order_date = datetime.strptime(
                    self.merge_strip_values(order_dom, ".//td[2]//text()"), "%m/%d/%Y"
                ).date()
                if from_date and to_date and (order_date < from_date or order_date > to_date):
                    continue

                order_id = self.merge_strip_values(order_dom, "./td[1]//text()")
                if completed_order_ids and order_id in completed_order_ids:
                    continue

                tasks.append(self.get_order(sem, order_dom, order_date, office))

            if tasks:
                orders = await asyncio.gather(*tasks, return_exceptions=True)

        return [Order.from_dict(order) for order in orders]

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        if perform_login:
            await self.login()

        async with self.session.get(product_url) as resp:
            res = Selector(text=await resp.text())
            product_name = self.extract_first(res, ".//span[@id='MainContent_lblName']/text()")
            product_description = self.extract_first(res, ".//span[@id='MainContent_lblDescription']/text()")
            # product_images = res.xpath(".//div[contains(@class, 'productSmallImg')]/img/@src").extract()
            product_price = self.extract_first(res, ".//span[@id='MainContent_lblPrice']/text()")
            product_price = re.findall("\\d+\\.\\d+", product_price)
            product_price = product_price[0] if isinstance(product_price, list) else None
            product_category = res.xpath(".//ul[contains(@class, 'breadcrumb')]/li/a/text()").extract()[1:]

            return {
                "product_id": product_id,
                "name": product_name,
                "description": product_description,
                "url": product_url,
                "images": [
                    {
                        "image": "https://azfun-web-image-picker.azurewebsites.net/api/getImage?"
                        f"sku={product_id.replace('-', '')}&type=WebImages"
                    }
                ],
                "category": product_category,
                "price": product_price,
                "vendor": self.vendor.to_dict(),
            }

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price"
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

        async with self.session.post(url, headers=SEARCH_HEADERS, data=data, params=params) as resp:
            response_dom = Selector(text=await resp.text())
            total_size_str = response_dom.xpath(".//span[@id='MainContent_resultCount']/text()").extract_first()
            matches = re.search(r"of(.*?)results", total_size_str)
            total_size = int(matches.group(1).strip()) if matches else 0
            products_dom = response_dom.xpath("//div[@id='productContainer']//div[contains(@class, 'prodcard')]")
            for product_dom in products_dom:
                price = self.extract_first(product_dom, ".//div[contains(@class, 'prod-price')]//text()")
                if "@" not in price:
                    continue
                _, price = price.split("@")
                product_id = self.extract_first(product_dom, ".//div[@class='prodno']/label//text()")
                product_name = self.extract_first(product_dom, ".//div[@class='prod-title']//text()")
                product_url = self.BASE_URL + self.extract_first(product_dom, ".//a[@href]/@href")
                product_image = self.extract_first(product_dom, ".//img[@class='card-img-top']/@src")
                products.append(
                    Product.from_dict(
                        {
                            "product_id": product_id,
                            "name": product_name,
                            "description": "",
                            "url": product_url,
                            "images": [
                                {
                                    "image": product_image,
                                }
                            ],
                            "price": price,
                            "vendor": self.vendor.to_dict(),
                        }
                    )
                )
        return {
            "vendor_slug": self.vendor.slug,
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

    def _get_vendor_categories(self, response) -> List[ProductCategory]:
        return [
            ProductCategory(
                name=category.xpath("./text()").extract_first(),
                slug=category.attrib["href"].split("/")[-1],
            )
            for category in response.xpath(
                "//ul[@id='catCage2']//div[contains(@class, 'card-footer')]/a[contains(@class, 'topic-link')]"
            )
        ]
