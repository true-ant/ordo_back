import asyncio
import datetime
from typing import Dict, List, Optional

from aiohttp import ClientResponse
from asgiref.sync import sync_to_async
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import Order, Product, ProductCategory, VendorOrderDetail
from apps.scrapers.utils import catch_network, semaphore_coroutine
from apps.types.orders import CartProduct
from apps.types.scraper import InvoiceFile, LoginInformation, ProductSearch

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

SEARCH_HEADERS = {
    "authority": "www.ultradent.com",
    "sec-ch-ua": '"Google Chrome";v="93", " Not;A Brand";v="99", "Chromium";v="93"',
    "accept": "*/*",
    "content-type": "application/json",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36",
    "sec-ch-ua-platform": '"Windows"',
    "origin": "https://www.ultradent.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.ultradent.com/checkout",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8",
}
ALL_PRODUCTS_VARIABLE = {
    "includeAllSkus": True,
    "withImages": True,
}
ALL_PRODUCTS_QUERY = """
  query Catalog($includeAllSkus: Boolean = true, $withImages: Boolean = false) {
    allProducts(includeAllSkus: $includeAllSkus) {
      sku
      brandName
      productName
      productFamily
      kitName
      url
      isOrderable
      images @include(if: $withImages) {
        source
        __typename
      }
      __typename
    }
  }
"""

PRODUCT_DETAIL_QUERY = """
    query CatalogItem($skuValues: String!, $withPrice: Boolean = false, $withAccessories: Boolean = false) {
        product(sku: $skuValues) {
            ...baseCatalogDetail
            quantityBreaks @include(if: $withPrice) {
                ...quantityBreakDetail
                __typename
            }
            accessories @include(if: $withAccessories) {
                ...accessoryDetail
                __typename
            }
            __typename
        }
    }

    fragment baseCatalogDetail on Product {
        sku
        brandId
        url
        kitName
        brandName
        productName
        productFamily
        catalogPrice
        customerPrice
        inStock
        isOrderable
        images {
            source
            __typename
        }
        __typename
    }

    fragment quantityBreakDetail on QuantityBreak {
        price
        quantity
        __typename
    }

    fragment accessoryDetail on Product {
        sku
        productFamily
        productName
        kitName
        url
        images {
            source
            __typename
        }
        __typename
    }
"""

GET_ORDERS_QUERY = """
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
"""

GET_ORDER_QUERY = """
    query GetOrderDetailWithTrackingHtml($orderNumber: Int!) {
        orderHtml(orderNumber: $orderNumber) {
            orderDetailWithShippingHtml
            __typename
        }
    }
"""

GET_ORDER_DETAIL_HTML = """
    query GetOrderDetailHtml($orderNumber: Int!) {
        orderHtml(orderNumber: $orderNumber) {
            orderDetailHtml
            __typename
        }
    }
"""


class UltraDentScraper(Scraper):
    BASE_URL = "https://www.ultradent.com"
    CATEGORY_URL = "https://www.ultradent.com/products/categories"
    CATEGORY_HEADERS = HEADERS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.product_urls = {}

    @sync_to_async
    def resolve_product_urls(self, product_ids):
        pass
        # from apps.orders.models import Product
        #
        # not_exists_product_ids = set(product_ids) - self.product_urls.keys()
        # if not_exists_product_ids:
        #     products = Product.objects.filter(product_id__in=not_exists_product_ids).values_list("product_id", "url")
        #     self.product_urls = {product["product_id"]: product["url"] for product in products}

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.text()
        res_dom = Selector(text=res)
        return self.username == res_dom.xpath("//meta[@name='mUserName']/@content").get()

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
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

    @semaphore_coroutine
    async def get_order(self, sem, order, office=None) -> dict:
        json_data = {
            "variables": {"orderNumber": order["orderNumber"]},
            "query": GET_ORDER_QUERY,
        }
        order = {
            "order_id": order["orderNumber"],
            "status": order["orderStatus"],
            "order_date": order["orderDate"],
            "currency": "USD",
            "products": [],
        }

        async with self.session.post(
            "https://www.ultradent.com/api/ecommerce", headers=ORDER_HEADERS, json=json_data
        ) as resp:
            oder_html = (await resp.json())["data"]["orderHtml"]["orderDetailWithShippingHtml"]
            order_dom = Selector(text=oder_html)
            tracking_dom = order_dom.xpath("//section[@data-tab='track-shipments']")
            product_images = {}
            for tracking_product in tracking_dom.xpath(".//ul/li"):
                sku = self.extract_first(tracking_product, ".//span[@class='sku-id']/text()")
                product_images[sku] = self.extract_first(
                    tracking_product, ".//figure[@class='sku-thumb']/div/img/@src"
                )

            # track_status = tracking_dom.xpath(".//span[contains(@class, 'shipment-package-date')]//text()").extract()
            # order["status"] = track_status[0].strip().strip(":")
            # order["tracking_date"] = track_status[1]

            shipping_dom = order_dom.xpath(
                "//section[@data-tab='order-details']/div[@class='odr-line-summary']"
                "/div[@class='grid-unit'][last()]/div[@class='address']"
            )

            codes = self.extract_first(shipping_dom, "./span[@class='location']//text()").split(", ")[1]
            region_code, postal_code, _ = codes.split()
            order["shipping_address"] = {
                "address": self.merge_strip_values(shipping_dom, "./span[@class='street1']//text()"),
                "region_code": region_code,
                "postal_code": postal_code,
            }
            for order_detail in order_dom.xpath("//section[@class='order-details']/ul[@class='odr-line-list']/li"):
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
                    product_id = self.extract_first(order_detail, "./span[@class='sku-id']//text()").strip()
                    price = self.extract_first(order_detail, "./span[@class='sku-price']//text()")

                    if product_id in product_images:
                        order_product_images = [{"image": product_images[product_id]}]
                    else:
                        order_product_images = []

                    order["products"].append(
                        {
                            "product": {
                                "product_id": product_id,
                                "name": self.extract_first(order_detail, "./span[@class='sku-product-name']//text()"),
                                "images": order_product_images,
                                "price": price,
                                "vendor": self.vendor.to_dict(),
                            },
                            "quantity": self.extract_first(order_detail, "./span[@class='sku-qty']//text()"),
                            "unit_price": price,
                            # "status": self.
                        }
                    )

        # await self.resolve_product_urls(
        #     [order_product["product"]["product_id"] for order_product in order["products"]]
        # )
        # for order_product in order["product"]:
        #     order_product["product"]["url"] = self.product_urls[order_product["product"]["product_id"]]

        # await self.get_missing_products_fields(
        #     order["products"],
        #     fields=(
        #         "description",
        #         "images",
        #         "category",
        #     ),
        # )
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
        url = "https://www.ultradent.com/api/ecommerce"

        json_data = {
            "variables": {"numberOfDays": 546, "numberOfRows": 150},
            "query": GET_ORDERS_QUERY,
        }
        if perform_login:
            await self.login()

        async with self.session.post(url, headers=ORDER_HEADERS, json=json_data) as resp:
            orders_data = (await resp.json())["data"]["orders"]
            tasks = []
            for order_data in orders_data:
                order_date = datetime.date.fromisoformat(order_data["orderDate"])
                if from_date and to_date and (order_date < from_date or order_date > to_date):
                    continue

                if completed_order_ids and str(order_data["orderNumber"]) in completed_order_ids:
                    continue

                tasks.append(self.get_order(sem, order_data, office))

            if tasks:
                orders = await asyncio.gather(*tasks, return_exceptions=True)
            return [Order.from_dict(order) for order in orders if isinstance(order, dict)]

    async def get_product_detail_as_dict(self, product_id, product_url) -> dict:
        json_data = {
            "variables": {
                "skuValues": product_id,
                "withAccessories": False,
                "withPrice": False,
            },
            "query": PRODUCT_DETAIL_QUERY,
        }

        async with self.session.post(
            "https://www.ultradent.com/api/ecommerce", headers=ORDER_HEADERS, json=json_data
        ) as resp:
            res = await resp.json()
            product = res["data"]["product"]
            return {
                "product_id": product_id,
                "name": product["productName"],
                "url": product_url,
                "images": [{"image": product_image["source"]} for product_image in product["images"]],
                "category": product["url"].split("/")[3:],
                "price": product["catalogPrice"],
                "vendor": self.vendor.to_dict(),
            }

    async def get_product_description_as_dict(self, product_url) -> dict:
        async with self.session.get(product_url) as resp:
            res = Selector(text=await resp.text())
            return {"description": res.xpath("//section[@id='productOverview']//p/text()").extract_first()}

    async def get_product_as_dict(self, product_id, product_url, perform_login=False) -> dict:
        if perform_login:
            await self.login()

        tasks = (
            self.get_product_detail_as_dict(product_id, product_url),
            self.get_product_description_as_dict(product_url),
        )
        result = await asyncio.gather(*tasks, return_exceptions=True)
        res = {}
        for r in result:
            if isinstance(r, dict):
                res.update(r)

        return res

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price", office_id=None
    ) -> ProductSearch:
        return await self._search_products_from_table(query, page, min_price, max_price, sort_by, office_id)

    def _get_vendor_categories(self, response) -> List[ProductCategory]:
        return [
            ProductCategory(
                name=category.xpath(".//h3/text()").extract_first(),
                slug=category.attrib["href"].split("/")[-1],
            )
            for category in response.xpath("//div[contains(@class, 'category-card-grid')]//a")
        ]

    async def get_all_products_data(self):
        async with self.session.post(
            "https://www.ultradent.com/api/ecommerce",
            headers=SEARCH_HEADERS,
            json={"query": ALL_PRODUCTS_QUERY, "variables": ALL_PRODUCTS_VARIABLE},
        ) as resp:
            res = await resp.json()
            ultradent_products = res["data"]["allProducts"]
            products = []
            for ultradent_product in ultradent_products:
                sku = ultradent_product["sku"]
                product_url = ultradent_product["url"]
                if not product_url:
                    continue
                products.append(
                    {
                        "product_id": sku,
                        # "name": product["productName"],
                        "url": f"{self.BASE_URL}{product_url}?sku={sku}",
                        "images": [
                            {
                                "image": image["source"],
                            }
                            for image in ultradent_product["images"]
                        ],
                        # "price": 0,
                        "vendor": self.vendor.to_dict(),
                        # "category": "category",
                    }
                )
            return products

    async def get_all_products(self) -> List[Product]:
        products = await self.get_all_products_data()
        tasks = (self.get_product(product["product_id"], product["url"]) for product in products[:1])
        products = await asyncio.gather(*tasks, return_exceptions=True)
        return [product for product in products if isinstance(product, Product)]

    async def save_product_to_db(self, queue: asyncio.Queue, office=None):
        while True:
            product = await queue.get()
            await sync_to_async(self.save_single_product_to_db)(product.to_dict(), office)
            await asyncio.sleep(3)
            queue.task_done()

    async def get_all_products_v2(self, office=None):
        products = await self.get_all_products_data()
        sem = asyncio.Semaphore(value=50)
        q = asyncio.Queue()
        producers = (
            self.get_product_v2(product_id=product["product_id"], product_url=product["url"], semaphore=sem, queue=q)
            for product in products
        )
        consumers = [asyncio.create_task(self.save_product_to_db(q, office)) for _ in range(50)]
        await asyncio.gather(*producers)
        await q.join()
        for c in consumers:
            c.cancel()

    async def download_invoice(self, invoice_link, order_id) -> InvoiceFile:
        json_data = {
            "operationName": "GetOrderDetailHtml",
            "variables": {"orderNumber": order_id},
            "query": GET_ORDER_DETAIL_HTML,
        }

        async with self.session.post(
            "https://www.ultradent.com/api/ecommerce", headers=ORDER_HEADERS, json=json_data
        ) as resp:
            order_detail_html = (await resp.json())["data"]["orderHtml"]["orderDetailHtml"]
            return await self.html2pdf(order_detail_html.encode("utf-8"))

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": "",
            "subtotal_amount": "",
            "shipping_amount": "",
            "tax_amount": "",
            "total_amount": "",
            "payment_method": "",
            "shipping_address": "",
        }
        vendor_slug: str = self.vendor.slug
        return {
            vendor_slug: {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            },
        }
