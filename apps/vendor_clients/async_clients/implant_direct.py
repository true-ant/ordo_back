import asyncio
import datetime
import json
import logging
import textwrap
from typing import Dict, Optional, Union

from aiohttp import ClientResponse
import scrapy
from scrapy import Selector
from unicaps import CaptchaSolver, CaptchaSolvingService

from apps.common.utils import (
    concatenate_list_as_string,
    extract_integer_from_string,
    extract_price_from_string,
    find_numerics_from_string,
    strip_whitespaces,
)
from apps.orders.models import OfficeProduct
from apps.orders.updater import STATUS_ACTIVE, STATUS_UNAVAILABLE
from apps.scrapers.utils import catch_network
from apps.vendor_clients import types
from apps.vendor_clients.async_clients.base import BaseClient, PriceInfo
from apps.vendor_clients.headers import implant_direct as hdrs
from apps.vendor_clients import errors, types

ANTI_CAPTCHA_API_KEY = 'c5fe215b8d10e582e21b52622c66be4e'
SITE_KEY = '6LeUI1YlAAAAAHc-5405p6x2aXI-e9R5o0RO9R9Z'
MIN_SCORE = 0.9
UESR_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36'

logger = logging.getLogger(__name__)


class ImplantDirectClient(BaseClient):
    VENDOR_SLUG = "implant_direct"
    aiohttp_mode = False

    def getHomePage(self):
        response = self.session.get("https://store.implantdirect.com/us/en/", headers=hdrs.HOMEPAGE_HEADERS)
        print("Home Page:", response.status_code)
        return response
    
    def getLoginPage(self, login_link):
        response = self.session.get(login_link, headers=hdrs.LOGIN_PAGE_HEADERS)
        print("LogIn Page:", response.status_code)
        return response
    
    async def get_login_link(self):
        async with self.session.get("https://store.implantdirect.com/",  headers=hdrs.HOMEPAGE_HEADERS,) as resp:
            text = await resp.text()
            login_dom = Selector(text=text)
            return login_dom.xpath('//ul/li[@class="authorization-link"]/a/@href').get()

    async def get_login_form(self, login_link):
        async with self.session.get(login_link, headers=hdrs.LOGIN_PAGE_HEADERS) as resp:
            text = await resp.text()
            login_dom = Selector(text=text)

            form_key = login_dom.xpath('//form[@id="login-form"]/input[@name="form_key"]/@value').get()
            form_action = login_dom.xpath('//form[@id="login-form"]/@action').get()
            solver = CaptchaSolver(
                CaptchaSolvingService.ANTI_CAPTCHA,
                ANTI_CAPTCHA_API_KEY
            )

            solved = solver.solve_recaptcha_v3(
                site_key=SITE_KEY,
                page_url=resp.url,
                is_enterprise=True,
                min_score=MIN_SCORE,
                api_domain="recaptcha.net"
            )

            recaptcha_token = solved.solution.token

            return {
                'key': form_key,
                'recaptcha_token': recaptcha_token,
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
                'g-recaptcha-response': form["recaptcha_token"],
                'token': form["recaptcha_token"],
            },
        }
    
    @catch_network
    async def login(self, username: Optional[str] = None, password: Optional[str] = None):
        """Login session"""
        if username:
            self.username = username
        if password:
            self.password = password

        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, self.login_proc)
        print("login DONE")
    
    def login_proc(self):
        headers = {
            "authority": "store.implantdirect.com",
            "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit"
            "/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
            "accept": "*/*",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "navigate",
            "sec-fetch-user": "?1",
            "sec-fetch-dest": "document",
            "referer": "https://store.implantdirect.com/us/en/",
            "accept-language": "en-US,en;q=0.9",
        }
        
        home_resp = self.getHomePage()
        home_dom = scrapy.Selector(text=home_resp.text)
        login_link = home_dom.xpath('//ul/li[contains(@class, "authorization-link")]/a/@href').get()
        login_resp = self.getLoginPage(login_link)
        login_dom = scrapy.Selector(text=login_resp.text)
        is_authenticated = self._check_authenticated(login_resp)
        if is_authenticated:
            return True
        
        solver = CaptchaSolver(
            CaptchaSolvingService.ANTI_CAPTCHA,
            ANTI_CAPTCHA_API_KEY
        )
        form_key = login_dom.xpath('//form[@id="login-form"]/input[@name="form_key"]/@value').get()
        form_action = login_dom.xpath('//form[@id="login-form"]/@action').get()

        retry_count = 5
        for i in range(retry_count):
            solved = solver.solve_recaptcha_v3(
                site_key=SITE_KEY,
                page_url=login_resp.url,
                is_enterprise=True,
                min_score=MIN_SCORE,
                api_domain="recaptcha.net"
            )

            recaptcha_token = solved.solution.token

            data = {
                'form_key': form_key,
                'login[username]': self.username,
                'login[password]': self.password,
                'g-recaptcha-response': recaptcha_token,
                'token': recaptcha_token,
            }

            response = self.session.post(form_action, data=data, headers=headers)
            if response.url.endswith('/customer/account/'):
                print(f"Try #{i+1} >>> Log In POST:", response.status_code)
                is_authenticated = self._check_authenticated(response)
                if not is_authenticated:
                    raise errors.VendorAuthenticationFailed()

                print(response.url)
                print("Log In POST:", response.status_code)
                return response.cookies
            else:
                if (i+1) == retry_count:
                    print(f"Exceed trying {retry_count} times!")
                    raise errors.VendorAuthenticationFailed()
                else:
                    print(f"Try #{i+1} >>> Login Faild!")
                    continue

    def _check_authenticated(self, response: ClientResponse) -> bool:
        dom = Selector(text=response.text)
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

    def get_product_dom(self, product_url):
        with self.session.get(product_url) as resp:
            return resp

    async def get_product_price_v2(self, product: OfficeProduct) -> PriceInfo:
        loop = asyncio.get_event_loop()
        if product.product.url:
            resp = await loop.run_in_executor(None, self.get_product_dom, product.product.url)
            response_dom = Selector(text=resp.text)

            price = response_dom.xpath(".//meta[@itemprop='price']/@content").get()
            sku = response_dom.xpath(".//div[@itemprop='sku']/text()").get()
            if product.product.product_id == sku:
                product_vendor_status = STATUS_ACTIVE
                return PriceInfo(price=price, product_vendor_status=product_vendor_status)
            else:
                product_vendor_status = STATUS_UNAVAILABLE
                return PriceInfo(price=0, product_vendor_status=product_vendor_status)
        else:
            product_vendor_status = STATUS_UNAVAILABLE
            return PriceInfo(price=0, product_vendor_status=product_vendor_status)
