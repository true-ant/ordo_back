import asyncio
import datetime
import json
import textwrap
from typing import Dict, Optional, Union

from aiohttp import ClientResponse
from scrapy import Selector

from apps.common.utils import (
    concatenate_list_as_string,
    extract_integer_from_string,
    extract_price_from_string,
    find_numerics_from_string,
    strip_whitespaces,
)
from apps.vendor_clients import types
from apps.vendor_clients.async_clients.base import BaseClient
from apps.vendor_clients.headers import implant_direct as hdrs


class ImplantDirectClient(BaseClient):
    VENDOR_SLUG = "implant_direct"

    async def get_login_link(self):
        home_dom = await self.get_response_as_dom(
            url="https://store.implantdirect.com/",
            headers=hdrs.HOMEPAGE_HEADERS,
        )
        return home_dom.xpath('//ul/li[@class="authorization-link"]/a/@href').get()

    async def get_login_form(self, login_link):
        login_dom = await self.get_response_as_dom(login_link, headers=hdrs.LOGIN_PAGE_HEADERS)
        form_key = login_dom.xpath('//form[@id="login-form"]/input[@name="form_key"]/@value').get()
        form_action = login_dom.xpath('//form[@id="login-form"]/@action').get()
        return {
            "key": form_key,
            "action": form_action,
        }

    async def get_login_data(self, *args, **kwargs) -> Optional[types.LoginInformation]:
        login_link = await self.get_login_link()
        form = await self.get_login_form(login_link)
        headers = hdrs.LOGIN_HEADERS.copy()
        headers["referer"] = login_link

        return {
            "url": form["action"],
            "headers": headers,
            "data": {
                "form_key": form["key"],
                "login[username]": self.username,
                "login[password]": self.password,
                "send": "",
            },
        }

    async def check_authenticated(self, response: ClientResponse) -> bool:
        text = await response.text()
        dom = Selector(text=text)
        page_title = dom.css("title::text").get()
        return page_title != "Customer Login"

    async def get_cart_page(self) -> Union[Selector, dict]:
        return await self.get_response_as_dom(
            url="https://store.implantdirect.com/checkout/cart/",
            headers=hdrs.GET_CART_HEADERS,
        )

    async def remove_product_from_cart(self, data):
        await self.session.post(
            "https://store.implantdirect.com/checkout/cart/delete/", headers=hdrs.CLEAR_CART_HEADERS, data=data
        )

    async def clear_cart(self):
        cart_page_dom = await self.get_cart_page()
        form_key = cart_page_dom.xpath('//form[@id="form-validate"]//input[@name="form_key"]/@value').get()

        tasks = []
        for product in cart_page_dom.xpath(
            '//form[@id="form-validate"]//table[@id="shopping-cart-table"]/tbody[@class="cart item"]'
        ):
            product_delete_action_data = product.xpath(
                './/a[contains(@class, "action-delete")]/@data-post-action'
            ).get()
            product_delete_action_data = json.loads(product_delete_action_data)

            data = {
                "id": product_delete_action_data["data"]["id"],
                "uenc": product_delete_action_data["data"]["uenc"],
                "form_key": form_key,
            }
            tasks.append(self.remove_product_from_cart(data))

        await asyncio.gather(*tasks)

    async def add_product_to_cart(self, product: types.CartProduct, *args, **kwargs):
        # TODO: action_link can be simply generated if we fetch uenc value
        product_page_dom = await self.get_product_page(
            product_link=product["product"]["url"], headers=hdrs.GET_PRODUCT_PAGE_HEADERS
        )
        action_link = product_page_dom.xpath('//form[@id="product_addtocart_form"]/@action').get()
        data = textwrap.dedent(
            """\
        -----------------------------114617192524257728931343838898
        Content-Disposition: form-data; name="product"

        %s
        -----------------------------114617192524257728931343838898
        Content-Disposition: form-data; name="selected_configurable_option"

        -----------------------------114617192524257728931343838898
        Content-Disposition: form-data; name="related_product"

        -----------------------------114617192524257728931343838898
        Content-Disposition: form-data; name="item"

        %s
        -----------------------------114617192524257728931343838898
        Content-Disposition: form-data; name="form_key"

        nXveVoCfshd9HVbEX
        -----------------------------114617192524257728931343838898
        Content-Disposition: form-data; name="qty"

        %s
        -----------------------------114617192524257728931343838898--
        """
            % (product["product"]["product_id"], product["product"]["product_id"], product["quantity"])
        )

        await self.session.post(action_link, headers=hdrs.ADD_PRODUCT_TO_CART_HEADERS, data=data)

    async def checkout_and_review_order(self, shipping_method: Optional[str] = None) -> dict:
        pass

    async def get_order_list(
        self, from_date: Optional[datetime.date] = None, to_date: Optional[datetime.date] = None
    ) -> Dict[str, dict]:
        page = 1
        can_continue = True
        ret = {}
        while True:
            query_params = {"limit": 50, "page": page}
            orders_list_dom = await self.get_response_as_dom(
                url="https://store.implantdirect.com/sales/order/history/",
                headers=hdrs.GET_ORDERS,
                query_params=query_params,
            )
            order_numbers = int(
                find_numerics_from_string(orders_list_dom.xpath('//span[@class="toolbar-number"]/text()').get())[-1]
            )
            orders_dom = orders_list_dom.xpath('//table[@id="my-orders-table"]/tbody/tr')
            for order_dom in orders_dom:
                order_reference = order_dom.xpath('./td[contains(@class, "id")]//text()').get()
                order_date = datetime.datetime.strptime(
                    order_dom.xpath('./td[contains(@class, "date")]//text()').get(), "%m/%d/%y"
                ).date()
                if from_date and order_date < from_date:
                    can_continue = False
                    continue
                if to_date and order_date > to_date:
                    can_continue = False
                    continue

                order_link = order_dom.xpath('./td[contains(@class, "actions")]/a[@class="action view"]/@href').get()
                order_id = order_link.split("/")[-2]

                ret[order_reference] = {
                    "order_id": order_id,
                    "order_reference": order_reference,
                    "order_link": order_link,
                    "total_amount": extract_price_from_string(
                        order_dom.xpath('./td[contains(@class, "total")]//text()').get()
                    ),
                    "order_date": order_date,
                    "status": order_dom.xpath('./td[contains(@class, "status")]//text()').get(),
                }

            if not can_continue or page * 50 > order_numbers:
                break

            page += 1

        return ret

    async def _get_order(self, order_data: dict) -> Optional[types.Order]:
        response_dom = await self.get_response_as_dom(url=order_data["order_link"], headers=hdrs.GET_ORDER)
        order_dom = response_dom.xpath('//table[@id="my-orders-table"]')
        subtotal_amount = extract_price_from_string(
            order_dom.xpath('./tfoot/tr[@class="subtotal"]/td[@class="amount"]//span[@class="price"]//text()').get()
        )
        shipping_amount = extract_price_from_string(
            order_dom.xpath('./tfoot/tr[@class="shipping"]/td[@class="amount"]//span[@class="price"]//text()').get()
        )
        tax_amount = extract_price_from_string(
            order_dom.xpath('./tfoot/tr[@class="totals-tax"]/td[@class="amount"]//span[@class="price"]//text()').get()
        )
        total_amount = (
            order_data["total_amount"]
            if "total_amount" in order_data
            else extract_price_from_string(
                order_dom.xpath(
                    './tfoot/tr[@class="grand_total"]/td[@class="amount"]//span[@class="price"]//text()'
                ).get()
            )
        )
        order_products = []

        for product_dom in order_dom.xpath('./tbody/tr[starts-with(@id, "order-item-row-")]'):
            order_products.append(
                {
                    "product": {
                        "vendor": self.VENDOR_SLUG,
                        "product_id": "",
                        "sku": strip_whitespaces(product_dom.xpath('./td[contains(@class, "sku")]//text()').get()),
                        "name": concatenate_list_as_string(
                            product_dom.xpath('./td[contains(@class, "name")]//text()').extract()
                        ),
                        "url": "",
                        "images": "",
                        "price": "",
                        "product_vendor_status": "",
                        "category": "",
                        "unit": "",
                    },
                    "quantity": extract_integer_from_string(
                        concatenate_list_as_string(
                            product_dom.xpath(
                                './td[contains(@class, "qty")]/ul[@class="items-qty"]/li[@class="item"][1]//text()'
                            ).extract()
                        )
                    ),
                    "price": extract_price_from_string(
                        concatenate_list_as_string(
                            product_dom.xpath('./td[contains(@class, "price")]//text()').extract()
                        )
                    ),
                    "status": "",
                    "tracking_link": "",
                    "tracking_number": "",
                }
            )
        return {
            "vendor": self.VENDOR_SLUG,
            "order_id": order_data["order_id"],
            "order_reference": order_data["order_reference"],
            "currency": "USD",
            "subtotal_amount": subtotal_amount,
            "shipping_amount": shipping_amount,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
            "order_date": order_data["order_date"],
            "status": order_data["status"],
            "shipping_method": strip_whitespaces(
                response_dom.xpath(
                    ".//div[contains(@class, 'box-order-shipping-method')]/div[@class='box-content']/text()"
                ).get()
            ),
            "shipping_address": concatenate_list_as_string(
                response_dom.xpath(
                    ".//div[contains(@class, 'box-order-shipping-address')]//address//text()"
                ).extract(),
                delimiter=" ",
            ),
            "billing_address": concatenate_list_as_string(
                response_dom.xpath(".//div[contains(@class, 'box-order-billing-address')]//address//text()").extract(),
                delimiter=" ",
            ),
            "products": order_products,
            "invoice_link": "https://store.implantdirect.com/sales"
            f"/order/printInvoice/order_id/{order_data['order_id']}/",
        }
