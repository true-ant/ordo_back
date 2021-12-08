import asyncio
import datetime
import uuid
from typing import Dict, List, Optional

from aiohttp import ClientResponse
from django.utils.dateparse import parse_datetime
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.errors import OrderFetchException
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import catch_network
from apps.types.orders import CartProduct
from apps.types.scraper import (
    InvoiceFile,
    LoginInformation,
    ProductSearch,
    SmartProductID,
)

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

SEARCH_HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
    "sec-ch-ua-mobile": "?0",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",  # noqa
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",  # noqa
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Language": "en-US,en;q=0.9",
}

CART_HEADERS = {
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "Accept": "application/json",
    "Content-Type": "application/json",
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",  # noqa
    "sec-ch-ua-platform": '"Windows"',
    "Origin": "https://www.net32.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.net32.com/shopping-cart",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}

CHECKOUT_HEADERS = {
    "Connection": "keep-alive",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",  # noqa
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",  # noqa
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.net32.com/shopping-cart",
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.net32.com/shopping-cart",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}

PLACE_ORDER_HEADERS = {
    "Connection": "keep-alive",
    "Content-Length": "0",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Origin": "https://www.net32.com",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.net32.com/checkout/review",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
}


class Net32Scraper(Scraper):
    BASE_URL = "https://www.net32.com"
    CATEGORY_URL = "https://www.net32.com/rest/userAndCartSummary/get"
    CATEGORY_HEADERS = HEADERS

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return (
            res.get("CallHeader", {}).get("StatusCode")
            and res["CallHeader"]["StatusCode"] != "SC_ERROR_BAD_LOGIN_CREDENTIALS"
        )

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        return {
            "url": f"{self.BASE_URL}/rest/user/login",
            "headers": HEADERS,
            "data": {
                "userName": self.username,
                "password": self.password,
                "latestTosVersion": "1",
            },
        }

    @catch_network
    async def get_orders(
        self,
        office=None,
        perform_login=False,
        from_date: Optional[datetime.date] = None,
        to_date: Optional[datetime.date] = None,
    ) -> List[Order]:
        url = f"{self.BASE_URL}/rest/order/orderHistory"
        headers = HEADERS.copy()
        headers["Referer"] = f"{self.BASE_URL}/account/orders"
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
                order_date = parse_datetime(order["coTime"]).date()
                if from_date and to_date and (order_date < from_date or order_date > to_date):
                    continue

                orders.append(
                    {
                        "order_id": order["id"],
                        "total_amount": order["orderTotal"],
                        "currency": "USD",
                        "order_date": parse_datetime(order["coTime"]).date(),
                        "status": order["status"],
                        "shipping_address": {
                            "address": "".join([i for i in order["shippingAdress"]["Streets"] if i]),
                            "region_code": order["shippingAdress"]["RegionCD"],
                            "postal_code": order["shippingAdress"]["PostalCD"],
                        },
                        "invoice_link": f"https://www.net32.com/account/orders/invoice/{order['id']}",
                        "products": [
                            {
                                "product": {
                                    "product_id": line_item["mpId"],
                                    "name": line_item["mpName"],
                                    "description": line_item["description"],
                                    "url": f"{self.BASE_URL}/{line_item['detailLink']}",
                                    "images": [{"image": f"{self.BASE_URL}/media{line_item['mediaPath']}"}],
                                    "category": [line_item["catName"]],
                                    "price": line_item["oliProdPrice"],
                                    "vendor": self.vendor.to_dict(),
                                },
                                "quantity": line_item["quantity"],
                                "unit_price": line_item["oliProdPrice"],
                                "status": line_item["status"],
                            }
                            for vendor_order in order["vendorOrders"]
                            for line_item in vendor_order["lineItems"]
                        ],
                    }
                )

            product_categories = {}
            product_ids = list(
                set([product["product"]["product_id"] for order in orders for product in order["products"]])
            )
            tasks = (self.get_product_category_tree(product_id) for product_id in product_ids)
            categories = await asyncio.gather(*tasks)
            for product_id, category in zip(product_ids, categories):
                product_categories[product_id] = category

            for order in orders:
                for order_product in order["products"]:
                    order_product["product"]["category"] = product_categories[order_product["product"]["product_id"]]

            orders = [Order.from_dict(order) for order in orders]

            if office:
                for order in orders:
                    await self.save_order_to_db(office, order=order)

            return orders
        except KeyError:
            raise OrderFetchException()

    async def get_product_category_tree(self, product_id, product_data_dict=None):
        async with self.session.get(f"https://www.net32.com/rest/neo/pdp/{product_id}/categories-tree") as resp:
            res = await resp.json()
            categories = [item["name"] for item in res]
            if product_data_dict:
                product_data_dict["category"] = categories
            return categories

    async def get_product_detail(self, product_id, product_data_dict):
        async with self.session.get(f"https://www.net32.com/rest/neo/pdp/{product_id}") as resp:
            res = await resp.json()

            product_data_dict["name"] = res["title"]
            product_data_dict["description"] = res["description"]
            product_data_dict["images"] = [{"image": f"{self.BASE_URL}/media{res['mediaPath']}"}]
            product_data_dict["price"] = res["retailPrice"]
            product_data_dict["vendor"] = self.vendor.to_dict()

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        product_data_dict = {
            "product_id": product_id,
            "url": product_url,
        }
        tasks = (
            self.get_product_detail(product_id, product_data_dict),
            self.get_product_category_tree(product_id, product_data_dict),
        )
        await asyncio.gather(*tasks, return_exceptions=True)
        return product_data_dict

    def get_products_from_search_page(self, dom) -> List[Product]:
        products = []
        products_dom = dom.xpath(
            "//div[@class='localsearch-results-container']//div[contains(@class, 'localsearch-result-wrapper')]"
        )

        for product_dom in products_dom:
            products.append(
                Product.from_dict(
                    {
                        "product_id": product_dom.attrib["data-mpid"],
                        "name": self.extract_first(
                            product_dom, ".//a[@class='localsearch-result-product-name']//text()"
                        ),
                        "description": self.extract_first(
                            product_dom, ".//div[@class='localsearch-result-product-packaging-container']//text()"
                        ),
                        "url": self.BASE_URL
                        + self.extract_first(product_dom, ".//a[@class='localsearch-result-product-name']/@href"),
                        "images": [
                            {
                                "image": self.BASE_URL
                                + self.extract_first(
                                    product_dom, ".//img[@class='localsearch-result-product-thumbnail']/@src"
                                )
                            }
                        ],
                        "price": self.extract_first(
                            product_dom, ".//ins[@class='localsearch-result-best-price']//text()"
                        ),
                        "vendor": self.vendor.to_dict(),
                    }
                )
            )

        return products

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0
    ) -> ProductSearch:
        url = f"{self.BASE_URL}/search"
        page_size = 60
        params = {
            "q": query,
            "page": page,
        }
        if min_price:
            params["filter.price.low"] = min_price
        if max_price:
            params["filter.price.high"] = max_price

        async with self.session.get(url, headers=SEARCH_HEADERS, params=params) as resp:
            response_url = str(resp.url)
            search_result_page = "search" in response_url
            response_dom = Selector(text=await resp.text())

        if search_result_page:
            try:
                total_size_str = response_dom.xpath(
                    "//p[@class='localsearch-result-summary-paragraph']/strong/text()"
                ).get()
                total_size = int(self.remove_thousands_separator(total_size_str))
            except (AttributeError, ValueError, TypeError):
                total_size = 0

            products = self.get_products_from_search_page(response_dom)
        else:
            product_id = response_url.split("-")[-1]
            product = await self.get_product_as_dict(product_id, response_url)
            products = [Product.from_dict(product)]
            total_size = 1

        return {
            "vendor_slug": self.vendor.slug,
            "total_size": total_size,
            "page": page,
            "page_size": page_size,
            "products": products,
            "last_page": page_size * page >= total_size,
        }

    async def add_product_to_cart(self, product: CartProduct, perform_login=False) -> dict:
        if perform_login:
            await self.login()

        data = [
            {
                "mpId": product["product_id"],
                "quantity": product["quantity"],
            }
        ]

        async with self.session.post(
            "https://www.net32.com/rest/shoppingCart/addMfrProdViaConsolidation", headers=CART_HEADERS, json=data
        ) as resp:
            cart_res = await resp.json()
            for vendor in cart_res["payload"]["vendorOrders"]:
                for vendor_product in vendor["products"]:
                    if str(vendor_product["mpId"]) == str(product["product_id"]):
                        return {
                            "product_id": product["product_id"],
                            "unit_price": vendor_product["unitPrice"],
                        }

    async def add_products_to_cart(self, products: List[CartProduct]):
        data = [
            {
                "mpId": product["product_id"],
                "quantity": product["quantity"],
            }
            for product in products
        ]

        await self.session.post(
            "https://www.net32.com/rest/shoppingCart/addMfrProdViaConsolidation", headers=CART_HEADERS, json=data
        )

    async def remove_product_from_cart(
        self, product_id: SmartProductID, perform_login: bool = False, use_bulk: bool = True
    ):
        if perform_login:
            await self.login()

        async with self.session.get("https://www.net32.com/rest/shoppingCart/get", headers=CART_HEADERS) as resp:
            cart_res = await resp.json()
            data = [
                {
                    "mpId": product["mpId"],
                    "vendorProductId": product["vendorProductId"],
                    "minimumQuantity": product["minimumQuantity"],
                    "quantity": 0,
                }
                for vendor in cart_res["payload"]["vendorOrders"]
                for product in vendor["products"]
                if str(product["mpId"]) == str(product_id)
            ]
        await self.session.post("https://www.net32.com/rest/shoppingCart/modify/rev2", headers=CART_HEADERS, json=data)

    async def clear_cart(self):
        async with self.session.get("https://www.net32.com/rest/shoppingCart/get", headers=CART_HEADERS) as resp:
            cart_res = await resp.json()
            data = []
            for vendor in cart_res["payload"]["vendorOrders"]:
                for product in vendor["products"]:
                    data.append(
                        {
                            "mpId": product["mpId"],
                            "vendorProductId": product["vendorProductId"],
                            "minimumQuantity": product["minimumQuantity"],
                            "quantity": 0,
                        }
                    )
        await self.session.post("https://www.net32.com/rest/shoppingCart/modify/rev2", headers=CART_HEADERS, json=data)

    async def review_order(self) -> VendorOrderDetail:
        async with self.session.get("https://www.net32.com/checkout", headers=REVIEW_CHECKOUT_HEADERS) as resp:
            res = Selector(text=await resp.text())
            retail_amount = self.remove_thousands_separator(
                self.extract_first(res, "//table[@class='order-summary-subtotal-table']//tr[1]/td/text()")
            )
            savings_amount = self.extract_price(
                self.remove_thousands_separator(
                    self.extract_first(res, "//table[@class='order-summary-subtotal-table']//tr[2]/td/text()")
                )
            )
            subtotal_amount = self.remove_thousands_separator(
                self.extract_first(res, "//table[@class='order-summary-subtotal-table']//tr[3]/td/text()")
            )
            shipping_amount = self.remove_thousands_separator(
                self.extract_first(res, "//table[@class='order-summary-subtotal-table']//tr[4]/td/text()")
            )
            tax_amount = self.remove_thousands_separator(
                self.extract_first(res, "//table[@class='order-summary-subtotal-table']//tr[5]/td/text()")
            )
            total_amount = self.remove_thousands_separator(
                self.extract_first(
                    res,
                    "//table[@class='order-summary-grandtotal-table']"
                    "//span[@class='order-summary-grandtotal-value']/text()",
                )
            )
            payment_method = self.merge_strip_values(res, "//dl[@id='order-details-payment']/dd[1]/strong//text()")
            shipping_address = self.extract_first(res, "//dl[@id='order-details-shipping']/dd[2]/text()")

            return VendorOrderDetail.from_dict(
                {
                    "retail_amount": retail_amount,
                    "savings_amount": savings_amount,
                    "subtotal_amount": subtotal_amount,
                    "shipping_amount": shipping_amount,
                    "tax_amount": tax_amount,
                    "total_amount": total_amount,
                    "payment_method": payment_method,
                    "shipping_address": shipping_address,
                }
            )

    async def create_order(self, products: List[CartProduct]) -> Dict[str, VendorOrderDetail]:
        await self.login()
        await self.clear_cart()
        await self.add_products_to_cart(products)
        vendor_order_detail = await self.review_order()
        vendor_slug: str = self.vendor.slug
        return {
            vendor_slug: {
                **vendor_order_detail.to_dict(),
                **self.vendor.to_dict(),
            }
        }

    async def confirm_order(self, products: List[CartProduct], fake=False):
        result = await self.create_order(products)
        if fake:
            return {**result[self.vendor.slug], "order_id": f"{uuid.uuid4()}"}
        else:
            async with self.session.post(
                "https://www.net32.com/checkout/confirmation", headers=PLACE_ORDER_HEADERS
            ) as resp:
                response_dom = Selector(text=await resp.text())
                order_id = response_dom.xpath(
                    "//h2[@class='checkout-confirmation-order-number-header']//a/text()"
                ).get()
            return {**result[self.vendor.slug], "order_id": order_id}

    def _get_vendor_categories(self, response) -> List[ProductCategory]:
        return [
            ProductCategory(
                name=category["CatName"],
                slug=category["url"].split("/")[-1],
            )
            for category in response["TopCategories"]
        ]

    async def download_invoice(self, invoice_link, order_id) -> InvoiceFile:
        await self.login()
        async with self.session.get(invoice_link) as resp:
            content = await resp.content.read()
            return await self.html2pdf(content)
