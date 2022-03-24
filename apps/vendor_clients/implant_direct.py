import asyncio
import json
import textwrap
from typing import Optional, Union

from aiohttp import ClientResponse
from scrapy import Selector

from apps.vendor_clients import types
from apps.vendor_clients.base import BaseClient

HOMEPAGE_HEADERS = {
    "authority": "store.implantdirect.com",
    "cache-control": "max-age=0",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

LOGIN_PAGE_HEADERS = {
    "authority": "store.implantdirect.com",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "referer": "https://store.implantdirect.com/",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

LOGIN_HEADERS = {
    "authority": "store.implantdirect.com",
    "cache-control": "max-age=0",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "origin": "https://store.implantdirect.com",
    "content-type": "application/x-www-form-urlencoded",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

GET_CART_HEADERS = {
    "authority": "store.implantdirect.com",
    "pragma": "no-cache",
    "cache-control": "no-cache",
    "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "referer": "https://store.implantdirect.com/",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

CLEAR_CART_HEADERS = {
    "authority": "store.implantdirect.com",
    "pragma": "no-cache",
    "cache-control": "no-cache",
    "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "origin": "https://store.implantdirect.com",
    "content-type": "application/x-www-form-urlencoded",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "referer": "https://store.implantdirect.com/checkout/cart/",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

ADD_PRODUCT_TO_CART_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:93.0) Gecko/20100101 Firefox/93.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.5",
    "X-NewRelic-ID": "VQUAU1dTABAHXFhUDgUHXlc=",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "multipart/form-data; boundary=---------------------------114617192524257728931343838898",
    "Origin": "https://store.implantdirect.com",
    "Connection": "keep-alive",
    "Referer": "https://store.implantdirect.com/implant-directtm-dentistry-kontour-sustain"
    "-porcine-resorbable-membrane-size-15x20mm-1-membrane-box.html",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "TE": "trailers",
}

GET_PRODUCT_PAGE_HEADERS = {
    "authority": "store.implantdirect.com",
    "pragma": "no-cache",
    "cache-control": "no-cache",
    "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}


class ImplantDirectClient(BaseClient):
    VENDOR_SLUG = "implant_direct"

    async def get_login_link(self):
        home_dom = await self.get_response_as_dom(
            url="https://store.implantdirect.com/",
            headers=HOMEPAGE_HEADERS,
        )
        return home_dom.xpath('//ul/li[@class="authorization-link"]/a/@href').get()

    async def get_login_form(self, login_link):
        login_dom = await self.get_response_as_dom(login_link, headers=LOGIN_PAGE_HEADERS)
        form_key = login_dom.xpath('//form[@id="login-form"]/input[@name="form_key"]/@value').get()
        form_action = login_dom.xpath('//form[@id="login-form"]/@action').get()
        return {
            "key": form_key,
            "action": form_action,
        }

    async def get_login_data(self, *args, **kwargs) -> Optional[types.LoginInformation]:
        login_link = await self.get_login_link()
        form = await self.get_login_form(login_link)
        headers = LOGIN_HEADERS.copy()
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
            headers=GET_CART_HEADERS,
        )

    async def remove_product_from_cart(self, data):
        await self.session.post(
            "https://store.implantdirect.com/checkout/cart/delete/", headers=CLEAR_CART_HEADERS, data=data
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
            product_link=product["product"]["url"], headers=GET_PRODUCT_PAGE_HEADERS
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

        await self.session.post(action_link, headers=ADD_PRODUCT_TO_CART_HEADERS, data=data)

    async def checkout_and_review_order(self, shipping_method: Optional[str] = None) -> dict:
        pass