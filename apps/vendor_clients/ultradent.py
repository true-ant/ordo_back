import datetime
import textwrap
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from aiohttp import ClientResponse
from scrapy import Selector

from apps.vendor_clients import types
from apps.vendor_clients.base import BASE_HEADERS, BaseClient

AUTHORIZATION = (
    "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1bmlxdWVfbmFtZSI6ImluZm9AY29sdW1iaW5lY3JlZWt"
    "kZW50aXN0cnkuY29tIiwiaHR0cDovL3NjaGVtYXMubWljcm9zb2Z0LmNvbS93cy8yMDA4LzA2L2lkZW50aXR5L2NsYW"
    "ltcy91c2VyZGF0YSI6IntcIkRhdGFcIjp7XCJVc2VySWRcIjoyMjg3NjUsXCJBY2NvdW50TnVtYmVyXCI6Mzk0NzYwL"
    "FwiVXNlckd1aWRcIjpcImZlZWUyYWZhLTM4YmMtNGIwOS1hYmY3LWY5YjcyNjMyNTUyMlwiLFwiRW1haWxcIjpcImlu"
    "Zm9AY29sdW1iaW5lY3JlZWtkZW50aXN0cnkuY29tXCIsXCJGaXJzdE5hbWVcIjpcIkFMRVhBTkRSQVwiLFwiU2FsZXN"
    "DaGFubmVsXCI6MX0sXCJVc2VyVHlwZVwiOjAsXCJSb2xlc1wiOltdLFwiUHJldmlld01vZGVcIjpmYWxzZX0iLCJuYm"
    "YiOjE2Mjk3ODkyNDEsImV4cCI6MTYyOTc5Mjg0MSwiaWF0IjoxNjI5Nzg5MjQxLCJpc3MiOiJodHRwczovL3d3dy51b"
    "HRyYWRlbnQuY29tIiwiYXVkIjoiaHR0cHM6Ly93d3cudWx0cmFkZW50LmNvbSJ9.aYwtN7JvDoZ8WeSJ1BkympQXlGg"
    "YpWuOtvTS0M2q2jM"
)
PRE_LOGIN_HEADERS = {
    **BASE_HEADERS,
    "authority": "www.ultradent.com",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "origin": "https://www.ultradent.com",
    "content-type": "application/x-www-form-urlencoded",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "referer": "https://www.ultradent.com/account",
}
GET_PRODUCTS_HEADERS = {
    **BASE_HEADERS,
    "authority": "www.ultradent.com",
    "accept": "*/*",
    "content-type": "application/json",
    "origin": "https://www.ultradent.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.ultradent.com/checkout",
}
GET_PRODUCT_HEADERS = {
    **BASE_HEADERS,
    "authority": "www.ultradent.com",
    "accept": "*/*",
    "authorization": AUTHORIZATION,
    "content-type": "application/json",
    "origin": "https://www.ultradent.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.ultradent.com/account/order-history",
}
GET_ORDERS_HEADERS = {
    **BASE_HEADERS,
    "authority": "www.ultradent.com",
    "accept": "*/*",
    "authorization": AUTHORIZATION,
    "content-type": "application/json",
    "origin": "https://www.ultradent.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.ultradent.com/account/order-history",
}
GET_ORDER_HEADERS = GET_ORDERS_HEADERS
ALL_PRODUCTS_QUERY = textwrap.dedent(
    """\
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
)
PRODUCT_DETAIL_QUERY = textwrap.dedent(
    """\
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

    fragment baseCatalogDetail on types.Product {
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

    fragment accessoryDetail on types.Product {
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
)
GET_ORDERS_QUERY = textwrap.dedent(
    """\
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
)

GET_ORDER_QUERY = textwrap.dedent(
    """\
    query GetOrderDetailWithTrackingHtml($orderNumber: Int!) {
        orderHtml(orderNumber: $orderNumber) {
            orderDetailWithShippingHtml
            __typename
        }
    }
"""
)


class UltradentClient(BaseClient):
    VENDOR_SLUG = "ultradent"

    async def get_login_data(self, *args, **kwargs) -> types.LoginInformation:
        """Provide login credentials and additional data along with headers"""
        url = "https://www.ultradent.com/login"
        login_get_response_dom = await self.get_response_as_dom(url=url, headers=PRE_LOGIN_HEADERS)
        token = login_get_response_dom.xpath("//input[@name='__RequestVerificationToken']/@value").get()

        return {
            "url": url,
            "headers": PRE_LOGIN_HEADERS,
            "data": {
                "Email": self.username,
                "Password": self.password,
                "__RequestVerificationToken": token,
            },
        }

    async def check_authenticated(self, response: ClientResponse) -> bool:
        """Check if whether session is authenticated or not"""
        res = await response.text()
        res_dom = Selector(text=res)
        return self.username == res_dom.xpath("//meta[@name='mUserName']/@content").get()

    async def get_order_list(
        self, from_date: Optional[datetime.date] = None, to_date: Optional[datetime.date] = None
    ) -> Dict[str, Union[Selector, dict]]:
        # TODO: we need to understand query meaning correctly to improve the performance
        json_data = {
            "variables": {"numberOfDays": 546, "numberOfRows": 150},
            "query": GET_ORDERS_QUERY,
        }
        async with self.session.post(
            url="https://www.ultradent.com/api/ecommerce", headers=GET_ORDERS_HEADERS, json=json_data
        ) as resp:
            res = await resp.json()
            orders: Dict[str, Any] = {}
            for order in res["data"]["orders"]:
                order_date = datetime.date.fromisoformat(order["orderDate"])
                if from_date and to_date and (order_date < from_date or order_date > to_date):
                    continue
                orders[order["orderNumber"]] = order

            return orders

    async def _get_order(self, order) -> types.Order:
        """Get vendor specific order"""
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
            "https://www.ultradent.com/api/ecommerce", headers=GET_ORDER_HEADERS, json=json_data
        ) as resp:
            oder_html = (await resp.json())["data"]["orderHtml"]["orderDetailWithShippingHtml"]
            order_dom = Selector(text=oder_html)
            tracking_dom = order_dom.xpath("//section[@data-tab='track-shipments']")
            product_images = {}
            for tracking_product in tracking_dom.xpath(".//ul/li"):
                sku = tracking_product.xpath(".//span[@class='sku-id']/text()").get()
                product_images[sku] = tracking_product.xpath(".//figure[@class='sku-thumb']/div/img/@src").get()

            shipping_dom = order_dom.xpath(
                "//section[@data-tab='order-details']/div[@class='odr-line-summary']"
                "/div[@class='grid-unit'][last()]/div[@class='address']"
            )

            codes = shipping_dom.xpath("./span[@class='location']//text()").split(", ")[1]
            region_code, postal_code, _ = codes.split()
            order["shipping_address"] = {
                "address": shipping_dom.xpath("./span[@class='street1']//text()").extract(),
                "region_code": region_code,
                "postal_code": postal_code,
            }
            for order_detail in order_dom.xpath("//section[@class='order-details']/ul[@class='odr-line-list']/li"):
                if order_detail.xpath("./@class").get() == "odr-line-header":
                    continue
                elif order_detail.xpath("./@class").get() == "odr-line-footer":
                    order["base_amount"] = order_detail.xpath(
                        "//div[@class='subtotal']/span[contains(@class, 'value')]//text()"
                    ).get()
                    order["shipping_amount"] = order_detail.xpath(
                        "//div[@class='shipping-total']/span[contains(@class, 'value')]//text()"
                    ).get()
                    order["tax_amount"] = order_detail.xpath(
                        "//div[@class='tax']/span[contains(@class, 'value')]//text()"
                    ).get()
                    order["total_amount"] = order_detail.xpath(
                        "//div[@class='odr-total']/span[contains(@class, 'value')]//text()"
                    ).get()
                else:
                    product_id = order_detail.xpath("./span[@class='sku-id']//text()").get()
                    price = order_detail.xpath("./span[@class='sku-price']//text()")

                    if product_id in product_images:
                        order_product_images = [product_images[product_id]]
                    else:
                        order_product_images = []

                    order["products"].append(
                        {
                            "product": {
                                "product_id": product_id,
                                "sku": product_id,
                                "name": order_detail.xpath("./span[@class='sku-product-name']//text()").get(),
                                "images": order_product_images,
                                "price": price,
                                "product_url": "",
                            },
                            "quantity": order_detail.xpath("./span[@class='sku-qty']//text()").get(),
                            "unit_price": price,
                            # "status": self.
                        }
                    )

        return order

    async def get_cart_page(self) -> Union[Selector, dict]:
        pass

    async def remove_product_from_cart(self, product: Any):
        pass

    async def clear_cart(self):
        pass

    async def add_products_to_cart(self, products: List[types.Product]):
        pass

    async def checkout_and_review_order(self, shipping_method: Optional[str] = None) -> dict:
        pass

    async def place_order(self, *args, **kwargs) -> str:
        pass

    def serialize(self, data: dict) -> Optional[types.Product]:
        product_url = data["url"]
        if product_url:
            category = product_url.split("/")[3]
            return {
                "product_id": data["sku"],
                "sku": data["sku"],
                "name": data["productName"],
                "url": f"https://www.ultradent.com{product_url}?sku={data['sku']}",
                "images": list(map(lambda x: x["source"], data["images"])),
                "price": Decimal(data.get("catalogPrice", "")),
                "category": category,
                "unit": "",
            }

    async def get_all_products(self) -> List[types.Product]:
        products: List[types.Product] = []

        async with self.session.post(
            url="https://www.ultradent.com/api/ecommerce",
            headers=GET_PRODUCTS_HEADERS,
            json={
                "query": ALL_PRODUCTS_QUERY,
                "variables": {
                    "includeAllSkus": True,
                    "withImages": True,
                },
            },
        ) as resp:
            res = await resp.json()
            vendor_products = res["data"]["allProducts"]
            for vendor_product in vendor_products:
                product = self.serialize(vendor_product)
                if product:
                    products.append(product)

        return products

    async def _get_product(self, product: types.Product) -> types.Product:
        async with self.session.post(
            "https://www.ultradent.com/api/ecommerce",
            headers=GET_PRODUCT_HEADERS,
            json={
                "variables": {
                    "skuValues": product["product_id"],
                    "withAccessories": False,
                    "withPrice": False,
                },
                "query": PRODUCT_DETAIL_QUERY,
            },
        ) as resp:
            res = await resp.json()
            return self.serialize(res["data"]["product"])
