import logging
import json
from typing import Dict, List, Tuple

from aiohttp import ClientResponse, ClientSession
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.schema import VendorOrderDetail
from apps.types.orders import CartProduct
from apps.types.scraper import LoginInformation, ProductSearch

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
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


class ImplantDirectScraper(Scraper):
    # BASE_URL = "https://www.henryschein.com"
    # CATEGORY_URL = "https://www.henryschein.com/us-en/dental/c/browsesupplies"
    # TRACKING_BASE_URL = "https://narvar.com/tracking/itemvisibility/v1/henryschein-dental/orders"

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        text = await response.text()
        dom = Selector(text=text)
        page_title = dom.css("title::text").get()
        return page_title != "Customer Login"

    async def get_login_link(self):
        async with self.session.get("https://store.implantdirect.com/", headers=HOMEPAGE_HEADERS) as resp:
            text = await resp.text()
            home_dom = Selector(text=text)
            return home_dom.xpath('//ul/li[@class="authorization-link"]/a/@href').get()

    async def get_login_form(self, login_link):
        async with self.session.get(login_link, headers=LOGIN_PAGE_HEADERS) as resp:
            text = await resp.text()
            login_dom = Selector(text=text)
            form_key = login_dom.xpath('//form[@id="login-form"]/input[@name="form_key"]/@value').get()
            form_action = login_dom.xpath('//form[@id="login-form"]/@action').get()
            print("ImplantDirect/get_login_form DONE")
            return {
                "key": form_key,
                "action": form_action,
            }

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        print("ImplantDirect/_get_login_data")
        login_link = await self.get_login_link()
        form = await self.get_login_form(login_link)
        headers = LOGIN_HEADERS.copy()
        headers["referer"] = login_link
        print("ImplantDirect/_get_login_data DONE")
        # async with self.session.get("https://store.implantdirect.com/") as resp:
        #     text = await resp.text()
        #     n = text.split("var _n =")[1].split(";")[0].strip(" '")
        # self.session.headers.update({"n": n})

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

    async def _get_check_login_state(self) -> Tuple[bool, dict]:
        login_link = await self.get_login_link()
        form = await self.get_login_form(login_link)
        if form["action"] == None:
            return True, {}
        else:
            return False, {}

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price", office_id=None
    ) -> ProductSearch:
        return await self._search_products_from_table(query, page, min_price, max_price, sort_by, office_id)

    async def getHomePage(self):
        headers = {
            'authority': 'store.implantdirect.com',
            'cache-control': 'max-age=0',
            'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'none',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        response = await self.session.get('https://store.implantdirect.com/', headers=headers)
        return response

    async def getLoginPage(self, login_link):
        headers = {
            'authority': 'store.implantdirect.com',
            'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'referer': 'https://store.implantdirect.com/',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        response = await self.session.get(login_link, headers=headers)
        return response

    async def getProductPage(self, link):
        headers = {
            'authority': 'store.implantdirect.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'none',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        response = await self.session.get(link, headers=headers)
        res = await response.text()
        return res

    
    async def getCartPage(self):
        headers = {
            'authority': 'store.implantdirect.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'referer': 'https://store.implantdirect.com/',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        response = await self.session.get('https://store.implantdirect.com/checkout/cart/', headers=headers)
        res = await response.text()
        return res
        
    async def shipping_infomation(self, payload):
        headers = {
            'authority': 'store.implantdirect.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            'x-newrelic-id': 'VQUAU1dTABAHXFhUDgUHXlc=',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
            'content-type': 'application/json',
            'accept': '*/*',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-platform': '"Windows"',
            'origin': 'https://store.implantdirect.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://store.implantdirect.com/checkout/',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        response = await self.session.post('https://store.implantdirect.com/rest/new_united_states_store_view/V1/carts/mine/shipping-information', headers=headers, json=payload)
        res = await response.json()
        return res["totals"]

    async def clear_cart(self):
        print("ImplantDirect/clear_cart")
        cart_page = await self.getCartPage()
        dom = Selector(text=cart_page)
        form_key = dom.xpath('//form[@id="form-validate"]//input[@name="form_key"]/@value').get()

        headers = {
            'authority': 'store.implantdirect.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'upgrade-insecure-requests': '1',
            'origin': 'https://store.implantdirect.com',
            'content-type': 'application/x-www-form-urlencoded',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'referer': 'https://store.implantdirect.com/checkout/cart/',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        for product in dom.xpath('//form[@id="form-validate"]//table[@id="shopping-cart-table"]/tbody[@class="cart item"]'):
            _data = product.xpath('.//a[contains(@class, "action-delete")]/@data-post-action').get()
            _data = json.loads(_data)

            data = {
                'id': _data['data']['id'],
                'uenc': _data['data']['uenc'],
                'form_key': form_key
            }

            response = await self.session.post('https://store.implantdirect.com/checkout/cart/delete/', headers=headers, data=data)

    async def add_to_cart(self, products):
        print("ImplantDirect/add_to_cart")
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:93.0) Gecko/20100101 Firefox/93.0',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.5',
            'X-NewRelic-ID': 'VQUAU1dTABAHXFhUDgUHXlc=',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'multipart/form-data; boundary=---------------------------114617192524257728931343838898',
            'Origin': 'https://store.implantdirect.com',
            'Connection': 'keep-alive',
            'Referer': 'https://store.implantdirect.com/implant-directtm-dentistry-kontour-sustain-porcine-resorbable-membrane-size-15x20mm-1-membrane-box.html',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'TE': 'trailers',
        }

        for product in products:
            product_page = await self.getProductPage(product["product_url"])
            # product_page = await self.getProductPage(product["link"])
            dom = Selector(text=product_page)
            action_link = dom.xpath('//form[@id="product_addtocart_form"]/@action').get()
            product_id = dom.xpath('//div[@data-product-id]/@data-product-id').get()

            
            data = f'-----------------------------114617192524257728931343838898\r\nContent-Disposition: form-data; name="product"\r\n\r\n{product_id}\r\n-----------------------------114617192524257728931343838898\r\nContent-Disposition: form-data; name="selected_configurable_option"\r\n\r\n\r\n-----------------------------114617192524257728931343838898\r\nContent-Disposition: form-data; name="related_product"\r\n\r\n\r\n-----------------------------114617192524257728931343838898\r\nContent-Disposition: form-data; name="item"\r\n\r\n{product_id}\r\n-----------------------------114617192524257728931343838898\r\nContent-Disposition: form-data; name="form_key"\r\n\r\nXveVoCfshd9HVbEX\r\n-----------------------------114617192524257728931343838898\r\nContent-Disposition: form-data; name="qty"\r\n\r\n{product["quantity"]}\r\n-----------------------------114617192524257728931343838898--\r\n'

            response = await self.session.post(action_link, headers=headers, data=data)

    async def checkout(self):
        print("ImplantDirect/checkout")
        headers = {
            'authority': 'store.implantdirect.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'referer': 'https://store.implantdirect.com/checkout/cart/',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        response = await self.session.get('https://store.implantdirect.com/checkout/', headers=headers)
        response_dom = Selector(text=await response.text())
        json_text = response_dom.xpath('//script[contains(text(), "totalsData")]//text()').get().strip()
        json_text = json_text.split("{", 1)[1].rsplit("}", 1)[0]
        json_data = json.loads("{"+json_text+"}")

        cartId = json_data["quoteData"]["entity_id"]
        shipping_payload = {
            'addressInformation': {
                'shipping_address': {},
                'billing_address': {},
                # shipping_method_code: 
                # - 2 Day : matrixrate_18490
                # - Next Day Air : matrixrate_18487
                # - Next Day (Saturday) : matrixrate_18486
                # - Next Day Air Early : matrixrate_18488
                # - Next Day Early (Saturday) : matrixrate_18489
                'shipping_method_code': 'matrixrate_18490',
                'shipping_carrier_code': 'matrixrate',
                'extension_attributes': {},
            },
        }
        
        shipping_address_l = json_data["customerData"]["addresses"]
        for item in shipping_address_l.values():
            if item["default_billing"]:
                shipping_payload["addressInformation"]["billing_address"]["countryId"] = item["country_id"]
                shipping_payload["addressInformation"]["billing_address"]["regionId"] = item["region_id"]
                shipping_payload["addressInformation"]["billing_address"]["region"] = item["region"]["region"]
                shipping_payload["addressInformation"]["billing_address"]["customerId"] = item["customer_id"]
                shipping_payload["addressInformation"]["billing_address"]["street"] = item["street"]
                shipping_payload["addressInformation"]["billing_address"]["company"] = item["company"]
                shipping_payload["addressInformation"]["billing_address"]["telephone"] = item["telephone"]
                shipping_payload["addressInformation"]["billing_address"]["postcode"] = item["postcode"]
                shipping_payload["addressInformation"]["billing_address"]["city"] = item["city"]
                shipping_payload["addressInformation"]["billing_address"]["firstname"] = item["firstname"]
                shipping_payload["addressInformation"]["billing_address"]["lastname"] = item["lastname"]

                billing_address = f'{item["inline"]}\n{item["telephone"]}'
                print("--- billing_address:\n", billing_address.strip() if billing_address else "")

            if item["default_shipping"]:
                shipping_payload["addressInformation"]["shipping_address"]["customerAddressId"] = item["id"]
                shipping_payload["addressInformation"]["shipping_address"]["countryId"] = item["country_id"]
                shipping_payload["addressInformation"]["shipping_address"]["regionId"] = item["region_id"]
                shipping_payload["addressInformation"]["shipping_address"]["regionCode"] = item["region"]["region_code"]
                shipping_payload["addressInformation"]["shipping_address"]["region"] = item["region"]["region"]
                shipping_payload["addressInformation"]["shipping_address"]["customerId"] = item["customer_id"]
                shipping_payload["addressInformation"]["shipping_address"]["street"] = item["street"]
                shipping_payload["addressInformation"]["shipping_address"]["company"] = item["company"]
                shipping_payload["addressInformation"]["shipping_address"]["telephone"] = item["telephone"]
                shipping_payload["addressInformation"]["shipping_address"]["fax"] = item["fax"]
                shipping_payload["addressInformation"]["shipping_address"]["postcode"] = item["postcode"]
                shipping_payload["addressInformation"]["shipping_address"]["city"] = item["city"]
                shipping_payload["addressInformation"]["shipping_address"]["firstname"] = item["firstname"]
                shipping_payload["addressInformation"]["shipping_address"]["lastname"] = item["lastname"]
                shipping_payload["addressInformation"]["shipping_address"]["middlename"] = item["middlename"]
                shipping_payload["addressInformation"]["shipping_address"]["prefix"] = item["prefix"]
                shipping_payload["addressInformation"]["shipping_address"]["suffix"] = item["suffix"]
                shipping_payload["addressInformation"]["shipping_address"]["vatId"] = item["vat_id"]
                shipping_payload["addressInformation"]["shipping_address"]["customAttributes"] = item["custom_attributes"]

                self.shipping_address = f'{item["inline"]}\n{item["telephone"]}'
                print("--- shipping_address:\n", self.shipping_address.strip() if self.shipping_address else "")

        total_info = await self.shipping_infomation(shipping_payload)
        currency = total_info["base_currency_code"]
        self.subtotal = total_info["subtotal"]
        print("--- subtotal:\n", f'{currency} {self.subtotal}'.strip() if self.subtotal else "")

        self.shipping = total_info["shipping_amount"]
        print("--- shipping:\n", f'{currency} { self.shipping}'.strip() if  self.shipping else "")

        self.discount = total_info["discount_amount"]
        print("--- discount:\n", f'{currency} {self.discount}'.strip() if self.discount else "")

        self.tax = total_info["tax_amount"]
        print("--- tax:\n", f'{currency} {self.tax}'.strip() if self.tax else "")

        self.order_total = total_info["grand_total"]
        print("--- order_total:\n", f'{currency} {self.order_total}'.strip() if self.order_total else "")

        return cartId, shipping_payload

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("Implant Direct/create_order")
        self.session = ClientSession()
        await self.login()
        await self.clear_cart()
        await self.add_to_cart(products)
        self.cartId, self.shipping_payload = await self.checkout()

        vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": self.discount,
            "subtotal_amount": self.subtotal,
            "shipping_amount": self.shipping,
            "tax_amount": self.tax,
            "total_amount": self.order_total,
            "payment_method": "",
            "shipping_address": self.shipping_address,
        }
        vendor_slug: str = self.vendor.slug
        return {
            vendor_slug: {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            },
        }

    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
        print("Implant Direct/confirm_order")
        self.session = ClientSession()
        headers = {
            'authority': 'store.implantdirect.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            'x-newrelic-id': 'VQUAU1dTABAHXFhUDgUHXlc=',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
            'content-type': 'application/json',
            'accept': '*/*',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-platform': '"Windows"',
            'origin': 'https://store.implantdirect.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://store.implantdirect.com/checkout',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        await self.login()
        await self.clear_cart()
        await self.add_to_cart(products)
        self.cartId, self.shipping_payload = await self.checkout()
        if fake:
            vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": self.discount,
            "subtotal_amount": self.subtotal,
            "shipping_amount": self.shipping,
            "tax_amount": self.tax,
            "total_amount": self.order_total,
            "payment_method": "",
            "shipping_address": self.shipping_address,
            }
            vendor_slug: str = self.vendor.slug
            return {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            }

        billingAddress = self.shipping_payload["addressInformation"]["shipping_address"]
        billingAddress["saveInAddressBook"] = None

        json_data = {
            'cartId': self.cartId,
            'billingAddress': billingAddress,
            'paymentMethod': {
                'method': 'authnetcim',
                'additional_data': {
                    'save': True,
                    'cc_type': 'VI',
                    'cc_cid': '',
                    'card_id': '1c80e875830abbb569795d889048ba9b03cb9f06',
                },
            },
        }

        response = await self.session.post('https://store.implantdirect.com/rest/new_united_states_store_view/V1/carts/mine/payment-information', headers=headers, json=json_data)
        vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": self.discount,
            "subtotal_amount": self.subtotal,
            "shipping_amount": self.shipping,
            "tax_amount": self.tax,
            "total_amount": self.order_total,
            "payment_method": "",
            "shipping_address": self.shipping_address,
        }
        vendor_slug: str = self.vendor.slug
        return {
            **vendor_order_detail,
            **self.vendor.to_dict(),
        }