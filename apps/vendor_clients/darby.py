import datetime
import re
from decimal import Decimal
from typing import List, Optional, Union

from aiohttp import ClientResponse
from scrapy import Selector

from apps.common.utils import concatenate_strings, convert_string_to_price
from apps.vendor_clients import types
from apps.vendor_clients.base import BASE_HEADERS, BaseClient

LOGIN_HEADERS = {
    **BASE_HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.darbydental.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.darbydental.com/DarbyHome.aspx",
}

GET_CART_HEADERS = {
    **BASE_HEADERS,
    "Upgrade-Insecure-Requests": "1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.darbydental.com/Home.aspx",
}

ADD_PRODUCTS_TO_CART_HEADERS = {
    **BASE_HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua-mobile": "?0",
    "Origin": "https://www.darbydental.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.darbydental.com",
}

CHECKOUT_HEADERS = {
    **BASE_HEADERS,
    "Upgrade-Insecure-Requests": "1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Referer": "https://www.darbydental.com/scripts/cart.aspx",
}

ORDER_HEADERS = {
    **BASE_HEADERS,
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "X-MicrosoftAjax": "Delta=true",
    "Accept": "*/*",
    "Origin": "https://www.darbydental.com",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://www.darbydental.com/scripts/checkout.aspx",
}
GET_PRODUCT_PAGE_HEADERS = {
    **BASE_HEADERS,
    "Host": "www.darbydental.com",
    "Cache-Control": "max-age=0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


class DarbyClient(BaseClient):
    VENDOR_SLUG = "darby"
    GET_PRODUCT_PAGE_HEADERS = GET_PRODUCT_PAGE_HEADERS

    async def get_login_data(self, *args, **kwargs) -> Optional[types.LoginInformation]:
        return {
            "url": "https://www.darbydental.com/api/Login/Login",
            "headers": LOGIN_HEADERS,
            "data": {"username": self.username, "password": self.password, "next": ""},
        }

    async def check_authenticated(self, response: ClientResponse) -> bool:
        res = await response.json()
        return res["m_Item2"] and res["m_Item2"]["username"] == self.username

    async def get_cart_page(self) -> Union[Selector, dict]:
        return await self.get_response_as_dom(
            url="https://www.darbydental.com/scripts/cart.aspx",
            headers=GET_CART_HEADERS,
        )

    async def clear_cart(self):
        cart_page_dom = await self.get_cart_page()

        products: List[types.CartProduct] = []
        for tr in cart_page_dom.xpath('//div[@id="MainContent_divGridScroll"]//table[@class="gridPDP"]//tr'):
            sku = tr.xpath(
                './/a[starts-with(@id, "MainContent_gvCart_lbRemoveFromCart_")][@data-prodno]/@data-prodno'
            ).get()
            if sku:
                products.append(
                    {
                        "product": {
                            "product_id": sku,
                        },
                        "quantity": 0,
                    }
                )

        if products:
            await self.add_products_to_cart(products)

    async def add_products_to_cart(self, products: List[types.CartProduct]):
        data = {}
        for index, product in enumerate(products):
            data[f"items[{index}][Sku]"] = (product["product"]["product_id"],)
            data[f"items[{index}][Quantity]"] = product["quantity"]

        await self.session.post(
            "https://www.darbydental.com/api/ShopCart/doAddToCart2", headers=ADD_PRODUCTS_TO_CART_HEADERS, data=data
        )

    def serialize(self, data: Union[dict, Selector]) -> Optional[types.Product]:
        product_id = data.xpath(".//span[@id='MainContent_lblItemNo']/text()").get()
        product_main_name = data.xpath(".//span[@id='MainContent_lblName']/text()").get()
        product_detail_name = data.xpath(
            ".//select[@id='MainContent_ddlAdditional']/option[@selected='selected']/text()"
        ).get()
        product_name = product_main_name + re.sub(r"(\d+)-(\d+)", "", product_detail_name)
        product_price = data.xpath(".//span[@id='MainContent_lblPrice']/text()").get()
        units = Decimal(product_price[:1])
        product_price = convert_string_to_price(product_price[1:]) / units
        product_category = data.xpath(".//ul[contains(@class, 'breadcrumb')]/li/a/text()").extract()[1]
        return {
            "product_id": product_id,
            "sku": product_id,
            "name": product_name,
            "url": "",
            "images": [
                "https://azfun-web-image-picker.azurewebsites.net"
                f"/api/getImage?sku={product_id.replace('-', '')}&type=WebImages"
            ],
            "price": product_price,
            "product_vendor_status": "",
            "category": product_category,
            "unit": "",
        }

    async def checkout_and_review_order(self, shipping_method: Optional[str] = None) -> dict:
        cart_page_dom = await self.get_cart_page()

        shipping_address = concatenate_strings(
            cart_page_dom.xpath('//span[@id="MainContent_lblAddress"]//text()').extract(), delimeter=", "
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
        order_detail = types.VendorOrderDetail(
            subtotal_amount=subtotal_amount,
            shipping_amount=shipping_amount,
            tax_amount=tax_amount,
            total_amount=total_amount,
            payment_method=None,
            shipping_address=shipping_address,
        )
        return {
            "order_detail": order_detail,
        }

    async def place_order(self, *args, **kwargs) -> str:
        checkout_dom = await self.get_response_as_dom(
            url="https://www.darbydental.com/scripts/checkout.aspx",
            headers=CHECKOUT_HEADERS,
        )

        data = {
            "ctl00$MainContent$pono": f"Ordo Order ({datetime.date.today().isoformat()})",
            "__ASYNCPOST": "true",
            "ctl00$masterSM": "ctl00$MainContent$UpdatePanel1|ctl00$MainContent$completeOrder",
            "ctl00$ddlPopular": "-1",
        }
        for _input in checkout_dom.xpath('//form[@id="form1"]//input[@name]'):
            _key = _input.xpath("./@name").get()
            _val = _input.xpath("./@value").get()
            data[_key] = _val
        async with self.session.post(
            "https://www.darbydental.com/scripts/checkout.aspx", headers=ORDER_HEADERS, data=data
        ) as resp:
            dom = Selector(text=await resp.text())
            order_id = dom.xpath('//span[@id="MainContent_lblInvoiceNo"]//text()').get()

        return order_id
