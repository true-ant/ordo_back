import json
from typing import Dict, List, Tuple

from aiohttp import ClientResponse, ClientSession
from scrapy import Selector

import uuid
from apps.scrapers.base import Scraper
from apps.scrapers.schema import VendorOrderDetail
from apps.types.orders import CartProduct
from apps.types.scraper import LoginInformation, ProductSearch

site_headers = {
    'authority': 'store.implantdirect.com',
    'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
    'accept': '*/*',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-user': '?1',
    'sec-fetch-dest': 'document',
    'referer': 'https://store.implantdirect.com/us/en/',
    'accept-language': 'en-US,en;q=0.9',
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

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        home_dom = Selector(text=await self.getHomePage())
        login_link = home_dom.xpath('//ul/li[contains(@class, "authorization-link")]/a/@href').get()

        login_dom = Selector(text=await self.getLoginPage(login_link))
        form_key = login_dom.xpath('//form[@id="login-form"]/input[@name="form_key"]/@value').get()
        form_action = login_dom.xpath('//form[@id="login-form"]/@action').get()

        return {
            "url": form_action,
            "headers": site_headers,
            "data": {
                "form_key": form_key,
                "login[username]": self.username,
                "login[password]": self.password,
                "send": "",
            },
        }

    async def getHomePage(self):
        resp = await self.session.get('https://store.implantdirect.com/us/en/', headers=site_headers)
        text = await resp.text()
        return text

    async def getLoginPage(self, login_link):
        resp = await self.session.get(login_link, headers=site_headers)
        text = await resp.text()
        return text

    async def getProductPage(self, link):
        response = await self.session.get(link, headers = site_headers)
        res = await response.text()
        return res
    
    async def getCartPage(self):
        response = await self.session.get('https://store.implantdirect.com/us/en/checkout/cart/', headers=site_headers)
        res = await response.text()
        return res
        
    async def shipping_infomation(self, payload):
        post_headers = {
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
            'referer': 'https://store.implantdirect.com/us/en/checkout/',
            'accept-language': 'en-US,en;q=0.9',
        }

        response = await self.session.post('https://store.implantdirect.com/us/en/rest/us_en/V1/carts/mine/shipping-information', headers=post_headers, json=payload)
        res = await response.json()
        return res["totals"]

    async def clear_cart(self):
        cart_page = await self.getCartPage()
        dom = Selector(text=cart_page)
        form_key = dom.xpath('//form[@id="form-validate"]//input[@name="form_key"]/@value').get()
        products = dom.xpath('//form[@id="form-validate"]//table[@id="shopping-cart-table"]/tbody[@class="cart item"]')
        data = {
            'form_key': form_key,
            'update_cart_action': 'empty_cart',
        }
        for product in products:
            _key = product.xpath('.//input[@data-role="cart-item-qty"]/@name').get()
            _val = product.xpath('.//input[@data-role="cart-item-qty"]/@value').get()
            data[_key] = _val
        if products:
            resp = await self.session.post('https://store.implantdirect.com/us/en/checkout/cart/updatePost/', data=data, headers=site_headers)
        
    async def add_to_cart(self, products):
        add_to_cart_headers = {
            'authority': 'store.implantdirect.com',
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
            'content-type': 'multipart/form-data; boundary=----WebKitFormBoundarytvKTimFXuo4R6Xsw',
            'origin': 'https://store.implantdirect.com',
            'referer': 'https://store.implantdirect.com/us/en/surgical-kit-grommet-small-2pk',
            'sec-ch-ua': '"Google Chrome";v="105", "Not)A;Brand";v="8", "Chromium";v="105"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }

        cookies = {
            'form_key': 'l7i7sDRkNglwFRKP',
        }

        for product in products:
            product_page = await self.getProductPage(product["product_url"])
            dom = Selector(text=product_page)
            action_link = dom.xpath('//form[@id="product_addtocart_form"]/@action').get()
            product_id = dom.xpath('//div[@data-product-id]/@data-product-id').get()

            data = f'------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="product"\r\n\r\n{product_id}\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="selected_configurable_option"\r\n\r\n\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="related_product"\r\n\r\n\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="item"\r\n\r\n{product_id}\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="form_key"\r\n\r\nl7i7sDRkNglwFRKP\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw\r\nContent-Disposition: form-data; name="qty"\r\n\r\n{product["qty"]}\r\n------WebKitFormBoundarytvKTimFXuo4R6Xsw--\r\n'

            response = await self.session.post(action_link, headers=add_to_cart_headers, data=data, cookies=cookies)

    async def checkout(self):
        print("checkout 1")
        response = await self.session.get('https://store.implantdirect.com/us/en/checkout/', headers=site_headers)
        print("checkout 2")
        response_dom = Selector(text=await response.text())
        print("checkout 3")
        json_text = response_dom.xpath('//script[contains(text(), "totalsData")]//text()').get().strip()
        json_text = json_text.split("window.checkoutConfig", 1)[1].split("window.customerData", 1)[0].split("window.isCustomerLoggedIn", 1)[0].rsplit("};", 1)[0]
        json_text = json_text.strip("\n\r\t =")
        json_data = json.loads(json_text+"}")
        print("checkout 4")

        cartId = json_data["quoteData"]["entity_id"]
        print("checkout 5")
        
        shipping_payload = {
            'addressInformation': {
                'shipping_address': {},
                'billing_address': {},
                # shipping_method_code: 
                # - Will Call – Pomona, CA: 38
                # - UPS 2 Day : 31
                # - UPS Overnight : 33
                # - UPS Overnight - AM delivery : 34
                # - UPS Overnight - Saturday delivery : UD
                # - UPS Overnight - AM Saturday delivery : 59
                'shipping_method_code': '31',
                'shipping_carrier_code': 'shippingoptions',
                'extension_attributes': {},
            },
        }
        print("checkout 6")

        
        shipping_address_l = json_data["customerData"]["addresses"]
        for item in shipping_address_l.values():
            if item["default_billing"]:
                shipping_payload["addressInformation"]["billing_address"]["customerAddressId"] = item["id"]
                shipping_payload["addressInformation"]["billing_address"]["countryId"] = item["country_id"]
                shipping_payload["addressInformation"]["billing_address"]["regionId"] = item["region_id"]
                shipping_payload["addressInformation"]["billing_address"]["regionCode"] = item["region"]["region_code"]
                shipping_payload["addressInformation"]["billing_address"]["region"] = item["region"]["region"]
                shipping_payload["addressInformation"]["billing_address"]["customerId"] = item["customer_id"]
                shipping_payload["addressInformation"]["billing_address"]["street"] = item["street"]
                shipping_payload["addressInformation"]["billing_address"]["company"] = item["company"]
                shipping_payload["addressInformation"]["billing_address"]["telephone"] = item["telephone"]
                shipping_payload["addressInformation"]["billing_address"]["fax"] = item["fax"]
                shipping_payload["addressInformation"]["billing_address"]["postcode"] = item["postcode"]
                shipping_payload["addressInformation"]["billing_address"]["city"] = item["city"]
                shipping_payload["addressInformation"]["billing_address"]["firstname"] = item["firstname"]
                shipping_payload["addressInformation"]["billing_address"]["lastname"] = item["lastname"]
                shipping_payload["addressInformation"]["billing_address"]["middlename"] = item["middlename"]
                shipping_payload["addressInformation"]["billing_address"]["prefix"] = item["prefix"]
                shipping_payload["addressInformation"]["billing_address"]["suffix"] = item["suffix"]
                shipping_payload["addressInformation"]["billing_address"]["vatId"] = item["vat_id"]
                shipping_payload["addressInformation"]["billing_address"]["customAttributes"] = list(item["custom_attributes"].values())

                billing_address = f'{item["inline"]}\n{item["telephone"]}'
                print("--- billing_address:\n", billing_address.strip() if billing_address else "")

            if item["default_shipping"]:
                shipping_payload["addressInformation"]["shipping_address"]["customerAddressId"] = item["id"]
                shipping_payload["addressInformation"]["shipping_address"]["email"] = json_data["customerData"]["email"]
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
                shipping_payload["addressInformation"]["shipping_address"]["customAttributes"] = list(item["custom_attributes"].values())

                shipping_address = f'{item["inline"]}\n{item["telephone"]}'
                print("--- shipping_address:\n", shipping_address.strip() if shipping_address else "")

        print("checkout 7")

        total_info = await self.shipping_infomation(shipping_payload)
        print("checkout 8")
        currency = total_info["base_currency_code"]
        subtotal = total_info["subtotal"]
        print("--- subtotal:\n", f'{currency} {subtotal}'.strip() if subtotal else "")

        shipping = total_info["shipping_amount"]
        print("--- shipping:\n", f'{currency} {shipping}'.strip() if shipping else "")

        discount = total_info["discount_amount"]
        print("--- discount:\n", f'{currency} {discount}'.strip() if discount else "")
        print("checkout 9")

        tax = total_info["tax_amount"]
        print("--- tax:\n", f'{currency} {tax}'.strip() if tax else "")

        order_total = total_info["grand_total"]
        print("--- order_total:\n", f'{currency} {order_total}'.strip() if order_total else "")
        print("checkout 10")

        return cartId, shipping_payload, shipping_address, subtotal, shipping, discount, tax, order_total

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("Implant Direct/create_order")
        # self.backsession = self.session
        # self.session = ClientSession()
        await self.login()
        await self.clear_cart()
        await self.add_to_cart(products)
        cartId, shipping_payload, shipping_address, subtotal, shipping, discount, tax, order_total = await self.checkout()

        vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": discount,
            "subtotal_amount": subtotal,
            "shipping_amount": shipping,
            "tax_amount": tax,
            "total_amount": order_total,
            "payment_method": "",
            "shipping_address": shipping_address,
        }
        # await self.session.close()
        # self.session = self.backsession
        vendor_slug: str = self.vendor.slug
        print("implant_direct/create_order DONE")
        return {
            vendor_slug: {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            },
        }

    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
        print("Implant Direct/confirm_order")
        # self.backsession = self.session
        # self.session = ClientSession()
        post_headers = {
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
            'referer': 'https://store.implantdirect.com/us/en/checkout/',
            'accept-language': 'en-US,en;q=0.9',
        }

        await self.login()
        await self.clear_cart()
        await self.add_to_cart(products)
        cartId, shipping_payload, shipping_address, subtotal, shipping, discount, tax, order_total = await self.checkout()

        if fake:
            # here code goes as fake(debug)
            # await self.session.close()
            # self.session = self.backsession
            vendor_order_detail = {
                "retail_amount": "",
                "savings_amount": discount,
                "subtotal_amount": subtotal,
                "shipping_amount": shipping,
                "tax_amount": tax,
                "total_amount": order_total,
                "payment_method": "",
                "shipping_address": shipping_address,
                "order_id":f"{uuid.uuid4()}",
            }
            print("Implant Direct/confirm_order DONE")

            return {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            }

        billingAddress = shipping_payload["addressInformation"]["shipping_address"]
        billingAddress["saveInAddressBook"] = None

        json_data = {
            'cartId': cartId,
            'billingAddress': billingAddress,
            "paymentMethod": {
                "method": "checkmo",
                "po_number": None,
                "additional_data": None
            }
        }

        response = await self.session.post('https://store.implantdirect.com/us/en/rest/us_en/V1/carts/mine/payment-information', headers=post_headers, json=json_data)
        response = await self.session.get('https://store.implantdirect.com/us/en/checkout/onepage/success/', headers=site_headers)
        response_dom = Selector(text=await response.text())
        order_num = response_dom.xpath('//a[@class="order-number"]/strong//text()').get()
        order_num = order_num.strip() if order_num else order_num
        print("Implant Direct/confirm_order DONE ", order_num)

        vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": discount,
            "subtotal_amount": subtotal,
            "shipping_amount": shipping,
            "tax_amount": tax,
            "total_amount": order_total,
            "payment_method": "",
            "shipping_address": shipping_address,
            "order_id": order_num
        }
        # await self.session.close()
        # self.session = self.backsession
        return {
            **vendor_order_detail,
            **self.vendor.to_dict(),
        }