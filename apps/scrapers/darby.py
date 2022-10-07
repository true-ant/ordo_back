import asyncio
import datetime
from email.errors import HeaderParseError
import time
import re
from typing import Dict, List, Optional
import uuid

from aiohttp import ClientResponse, ClientSession
from scrapy import Selector

from apps.common.utils import concatenate_list_as_string
from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import (
    catch_network,
    convert_string_to_price,
    semaphore_coroutine,
)
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
GET_CART_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.darbydental.com/Home.aspx",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}
ADD_TO_CART_HEADERS = {
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
CHECKOUT_HEADERS = {
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
ORDER_HEADERS = {
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "X-MicrosoftAjax": "Delta=true",
    "sec-ch-ua-platform": '"Windows"',
    "Accept": "*/*",
    "Origin": "https://www.darbydental.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.darbydental.com/scripts/checkout.aspx",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

REVIEW_ORDER_HEADER = {
    'Connection': 'keep-alive',
    'sec-ch-ua': '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-User': '?1',
    'Sec-Fetch-Dest': 'document',
    'Referer': 'https://www.darbydental.com/scripts/cart.aspx',
    'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
}

CHECKOUT_SUBMIT_HEADER = {
    'Connection': 'keep-alive',
    'Pragma': 'no-cache',
    'Cache-Control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    'sec-ch-ua-mobile': '?0',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest',
    'X-MicrosoftAjax': 'Delta=true',
    'sec-ch-ua-platform': '"Windows"',
    'Accept': '*/*',
    'Origin': 'https://www.darbydental.com',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'Referer': 'https://www.darbydental.com/scripts/checkout.aspx',
    'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
REAL_ORDER_HEADER = {
    'Connection': 'keep-alive',
    'Pragma': 'no-cache',
    'Cache-Control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    'sec-ch-ua-mobile': '?0',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'X-Requested-With': 'XMLHttpRequest',
    'X-MicrosoftAjax': 'Delta=true',
    'sec-ch-ua-platform': '"Windows"',
    'Accept': '*/*',
    'Origin': 'https://www.darbydental.com',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'Referer': 'https://www.darbydental.com/scripts/checkout.aspx',
    'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
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
                vendor_order_status = self.extract_first(tracking_dom, "./td[4]//text()")
                order["status"] = vendor_order_status.split(" ", 1)[0].lower()
            except IndexError:
                # TODO: this is possible cases
                # mar 21 2022  4:13am out for delivery
                # feb 23 2022 10:41am package is in transit to a ups facility
                # received by ups:feb 11 2022  4:47pm
                order["status"] = "processing"

    async def get_order_products(self, order, link):
        async with self.session.get(f"{self.BASE_URL}/Scripts/{link}", headers=HEADERS) as resp:
            order_detail_response = Selector(text=await resp.text())
            order["products"] = []
            for detail_row in order_detail_response.xpath(
                "//table[@id='MainContent_gvInvoiceDetail']//tr[@class='pdpHelltPrimary']"  # noqa
            ):
                # product_id = self.merge_strip_values(detail_row, "./td[1]/a//text()")
                product_name = self.merge_strip_values(detail_row, "./td[2]//text()")
                product_url = self.merge_strip_values(detail_row, "./td[1]/a//@href")
                product_id = product_url.split("/")[-1]
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
            else datetime.datetime.strptime(self.merge_strip_values(order_dom, ".//td[2]//text()"), "%m/%d/%Y").date(),
            "invoice_link": f"{self.BASE_URL}{invoice_link}",
        }
        await asyncio.gather(self.get_order_products(order, link), self.get_shipping_track(order, order_id))

        if office:
            print("===== darby/get_order 6 =====")
            await self.save_order_to_db(office, order=Order.from_dict(order))
        print("===== darby/get_order 7 =====")

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
        print("Darby/get_orders")
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
                order_date = datetime.datetime.strptime(
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
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price", office_id=None
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
            "ctl00$MainContent$currentSort": "priceLowToHigh",
            "ctl00$MainContent$selPerPage": f"{page_size}",
            "ctl00$MainContent$sorter": "priceLowToHigh",
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

    async def get_cart_page(self):
        async with self.session.get("https://www.darbydental.com/scripts/cart.aspx", headers=GET_CART_HEADERS) as resp:
            dom = Selector(text=await resp.text())
            return dom

    async def add_products_to_cart(self, products: List[CartProduct]):
        data = {}
        for index, product in enumerate(products):
            data[f"items[{index}][Sku]"] = (product["product_id"],)
            data[f"items[{index}][Quantity]"] = product["quantity"]

        response = await self.session.post(
            "https://www.darbydental.com/api/ShopCart/doAddToCart2", headers=ADD_TO_CART_HEADERS, data=data
        )
        res = await response.text()

    async def clear_cart(self):
        cart_page_dom = await self.get_cart_page()

        products: List[CartProduct] = []
        for tr in cart_page_dom.xpath('//div[@id="MainContent_divGridScroll"]//table[@class="gridPDP"]//tr'):
            sku = tr.xpath(
                './/a[starts-with(@id, "MainContent_gvCart_lbRemoveFromCart_")][@data-prodno]/@data-prodno'
            ).get()
            if sku:
                products.append(CartProduct(product_id=sku, quantity=0))

        if products:
            await self.add_products_to_cart(products)

    async def review_order(self) -> VendorOrderDetail:
        cart_page_dom = await self.get_cart_page()

        shipping_address = concatenate_list_as_string(
            cart_page_dom.xpath('//span[@id="MainContent_lblAddress"]//text()').extract()
        )
        subtotal_amount = convert_string_to_price(
            cart_page_dom.xpath('//tbody[@id="orderTotals"]//td/span[@id="MainContent_lblSubTotal"]//text()').get()
        )
        shipping_amount = convert_string_to_price(
            cart_page_dom.xpath(
                '//tbody[@id="orderTotals"]//td/span[@id="MainContent_lblServiceCharge"]//text()'
            ).get()
        )
        tax_amount = convert_string_to_price(
            cart_page_dom.xpath('//tbody[@id="orderTotals"]//td/span[@id="MainContent_lblEstimatedTax"]//text()').get()
        )
        total_amount = convert_string_to_price(
            cart_page_dom.xpath('//tbody[@id="orderTotals"]//td/span[@id="MainContent_lblTotal"]//text()').get()
        )
        return VendorOrderDetail.from_dict(
            {
                "subtotal_amount": subtotal_amount,
                "shipping_amount": shipping_amount,
                "tax_amount": tax_amount,
                "total_amount": total_amount,
                "shipping_address": shipping_address,
            }
        )

    async def checkout(self):
        response = await self.session.get('https://www.darbydental.com/scripts/checkout.aspx', headers=REVIEW_ORDER_HEADER)
        dom = Selector(text = await response.text())

        data = {
            "__EVENTTARGET": "ctl00$MainContent$completeOrder",
            "ctl00$MainContent$paymode": "rdbAccount",
            "__EVENTARGUMENT": "",
            'ctl00$masterSM': 'ctl00$MainContent$UpdatePanel1|ctl00$MainContent$completeOrder',
            '__ASYNCPOST': 'true',
            'ctl00$ddlPopular': '-1',
            'ctl00$MainContent$pono': f"Ordo Order ({time.strftime('%Y-%m-%d')})",
        }

        for ele in dom.xpath('//input[@name]'):
            _key = ele.xpath('./@name').get()
            _val = ele.xpath('./@value').get()
            if _val is None: _val = ""
            if _key not in data:
                if _key not in [
                    "ctl00$logonControl$btnLogin",
                    "ctl00$logonControl$btnSignUp",
                    "ctl00$btnBigSearch",
                    "ctl00$MainContent$completeOrder"
                ]:
                    data[_key] = _val

        for ele in dom.xpath('//select[@name]'):
            _key = ele.xpath('./@name').get()
            _val = ele.xpath('./option[@selected="selected"]/@value').get()
            if not _val:
                _val = ele.xpath('./option[1]/@value').get()
            if _val is None: _val = ""
            if _key not in data: data[_key] = _val

        response = await self.session.post('https://www.darbydental.com/scripts/checkout.aspx', headers=CHECKOUT_SUBMIT_HEADER, data=data)
        response_text = await response.text()
        response_text = response_text.replace("%2f", "/")
        response_text = response_text.replace("%3f", "?")
        response_text = response_text.replace("%3d", "=")
        response_text = response_text.replace("%26", "&")
        response_text = response_text.strip("| ").split("|")[-1]
        redirect_link = f'https://www.darbydental.com{response_text}'
        return redirect_link


    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("darby/create_order")
        await self.login()
        await self.clear_cart()
        await self.add_products_to_cart(products)
        vendor_order_detail = await self.review_order()
        vendor_slug: str = self.vendor.slug
        print("darby/create_order DONE")
        return {
            vendor_slug: {
                **vendor_order_detail.to_dict(),
                **self.vendor.to_dict(),
            },
        }

    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
        print("darby/confirm_order")
        await self.login()
        await self.clear_cart()
        await self.add_products_to_cart(products)
        vendor_order_detail = await self.review_order()
        if fake:
            print("darby/confirm_order DONE")
            return {
                **vendor_order_detail.to_dict(),
                **self.vendor.to_dict(),
                "order_id":f"{uuid.uuid4()}",
            }

        link = await self.checkout()
        await self.session.post(link, headers = REAL_ORDER_HEADER)

        return {
            **vendor_order_detail.to_dict(),
            **self.vendor.to_dict(),
            "order_id":"invalid"
        }

    # async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
    #     vendor_order_detail = await self.create_order(products)
    #     if fake:
    #         order_id = f"{uuid.uuid4()}"
    #     else:
    #         async with self.session.get(
    #             "https://www.darbydental.com/scripts/checkout.aspx", headers=CHECKOUT_HEADERS
    #         ) as resp:
    #             checkout_dom = Selector(text=await resp.text())
    #
    #         data = {
    #             "ctl00$MainContent$pono": f"Ordo Order ({datetime.date.today().isoformat()})",
    #             "__ASYNCPOST": "true",
    #             "ctl00$masterSM": "ctl00$MainContent$UpdatePanel1|ctl00$MainContent$completeOrder",
    #             "ctl00$ddlPopular": "-1",
    #         }
    #         for _input in checkout_dom.xpath('//form[@id="form1"]//input[@name]'):
    #             _key = _input.xpath("./@name").get()
    #             _val = _input.xpath("./@value").get()
    #             data[_key] = _val
    #         async with self.session.post(
    #             "https://www.darbydental.com/scripts/checkout.aspx", headers=ORDER_HEADERS, data=data
    #         ) as resp:
    #             dom = Selector(text=await resp.text())
    #             order_id = dom.xpath('//span[@id="MainContent_lblInvoiceNo"]//text()').get()
    #
    #     return {
    #         **vendor_order_detail,
    #         "order_id": order_id,
    #     }
