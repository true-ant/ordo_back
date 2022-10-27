import datetime
import time
import re
import json
import uuid
import scrapy
import requests
import traceback
import asyncio
from scrapy import Selector
from typing import Dict, List, Optional, Tuple
from http.cookies import SimpleCookie

from apps.scrapers.base import Scraper
from apps.scrapers.utils import catch_network, semaphore_coroutine
from apps.scrapers.schema import VendorOrderDetail, Order
from apps.types.orders import CartProduct

headers = {
    'authority': 'www.dcdental.com',
    'accept': 'application/json, text/javascript, */*; q=0.01',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json; charset=UTF-8',
    'origin': 'https://www.dcdental.com',
    'referer': 'https://www.dcdental.com',
    'sec-ch-ua': '"Google Chrome";v="105", "Not)A;Brand";v="8", "Chromium";v="105"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36',
    'x-requested-with': 'XMLHttpRequest',
    'x-sc-touchpoint': 'checkout',
}

class DCDentalScraper(Scraper):

    reqsession = requests.Session()

    @catch_network
    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> SimpleCookie:
        if username:
            self.username = username
        if password:
            self.password = password

        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None,self.login_proc)
        print("login DONE")
        return res


    def login_proc(self):
        json_data = {
            'email': self.username,
            'password': self.password,
            'redirect': 'true',
        }
        resp = self.reqsession.post('https://www.dcdental.com/dc-dental/services/Account.Login.Service.ss?n=3&c=1075085', headers=headers, json=json_data)
        print(f'[INFO] Login Status : {resp.status_code}')

    def get_cart_products(self):
        resp = self.reqsession.get('https://www.dcdental.com/dc-dental/services/LiveOrder.Service.ss?c=1075085&internalid=cart', headers=headers)
        print(f'[INFO] Cart Page : {resp.status_code}')
        return resp.json()["lines"]

    def clear_cart(self):
        cart_products = self.get_cart_products()
        print(f'[INFO] Found {len(cart_products)} Products in Cart')
        for cart_product in cart_products:
            internalid = cart_product["internalid"]
            resp = self.reqsession.delete(f'https://www.dcdental.com/dc-dental/services/LiveOrder.Line.Service.ss?c=1075085&internalid={internalid}&n=3', headers=headers)
            print(f'[INFO] Removed Product {internalid} : {resp.status_code}')
        
        print("[INFO] Emptied Cart..")

    def add_to_cart(self, products):
        data = list()
        for product in products:
            item = {
                'item': {
                    'internalid': int(product["product_id"]),
                },
                'quantity': product["quantity"],
                'options': [],
                'location': '',
                'fulfillmentChoice': 'ship',
            }
            data.append(item)

        resp = self.reqsession.post('https://www.dcdental.com/dc-dental/services/LiveOrder.Line.Service.ss', headers=headers, json=data)
        print(f'[INFO] Add to Cart : {resp.status_code}')

    def checkout(self):
        resp = self.reqsession.get(f"https://www.dcdental.com/dc-dental/checkout.environment.ssp?lang=en_US&cur=USD&X-SC-Touchpoint=checkout&cart-bootstrap=T&t={int(time.time()*1000)}", headers=headers)
        print(f"[INFO] Checkout Data : {resp.status_code}")
        resp_text = resp.text

        cart_data = resp_text.split("SC.ENVIRONMENT.CART ")[1].split("\n")[0].strip(" =;")
        cart_json = json.loads(cart_data)

        ship_methods = cart_json["shipmethods"]
        cheapest_method_value = None
        cheapest_method_id = None
        for ship_method in ship_methods:
            if not cheapest_method_value:
                cheapest_method_value = ship_method["rate"]
                cheapest_method_id = ship_method["internalid"]
            else:
                if cheapest_method_value > ship_method["rate"]:
                    cheapest_method_value = ship_method["rate"]
                    cheapest_method_id = ship_method["internalid"]

        cart_json["shipmethod"] = cheapest_method_id
        resp = self.reqsession.put(f'https://www.dcdental.com/dc-dental/services/LiveOrder.Service.ss?internalid=cart&t={int(time.time()*1000)}&c=1075085&n=3', headers=headers, json=cart_json)
        print(f"[INFO] Choosen Shipmethod - {cheapest_method_id} : {resp.status_code}")

        resp_json = resp.json()
        billing_addr = ""
        shipping_addr = ""
        addresses = resp_json["addresses"]
        for address in addresses:
            if address["defaultbilling"] == "T":
                billing_addr = [
                    address["fullname"],
                    address["addr1"],
                    address["city"],
                    address["state"],
                    address["zip"],
                    address["country"],
                ]
                billing_addr = ', '.join(billing_addr)
                print("::::: Billing Address :::::")
                print(billing_addr)

            elif address["defaultshipping"] == "T":
                shipping_addr = [
                    address["fullname"],
                    address["addr1"],
                    address["city"],
                    address["state"],
                    address["zip"],
                    address["country"],
                ]
                shipping_addr = ', '.join(shipping_addr)
                print("::::: Shipping Address :::::")
                print(shipping_addr)

        subtotal = resp_json["summary"]["subtotal"]
        print("::::: Subtotal :::::")
        print(subtotal)

        flat_rate_shipping = resp_json["summary"]["handlingcost"]
        print("::::: Flat Rate Shipping :::::")
        print(flat_rate_shipping)

        return resp_json, shipping_addr, subtotal

    def review_order(self, checkout_data):
        resp = self.reqsession.put(f'https://www.dcdental.com/dc-dental/services/LiveOrder.Service.ss?internalid=cart&t={int(time.time()*1000)}&c=1075085&n=3', headers=headers, json=checkout_data)
        print(f"[INFO] Review Order: {resp.status_code}")

        return resp.json()

    def place_order(self,order_data):
        order_data["agreetermcondition"] = True
        resp = self.reqsession.post(f'https://www.dcdental.com/dc-dental/services/LiveOrder.Service.ss?t={int(time.time()*1000)}&c=1075085&n=3', headers=headers, json=order_data)
        print(f"[INFO] Place Order: {resp.status_code}")

        resp_json = resp.json()
        
        estimated_tax = resp_json["confirmation"]["summary"]["taxtotal"]
        print("::::: Estimated Tax :::::")
        print(estimated_tax)

        total = resp_json["confirmation"]["summary"]["total"]
        print("::::: Total :::::")
        print(total)

        order_num = resp_json["confirmation"]["tranid"]
        return order_num, estimated_tax, total

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("DCDental/create_order")
        loop = asyncio.get_event_loop()
        await self.login()
        await loop.run_in_executor(None,self.clear_cart)
        await loop.run_in_executor(None,self.add_to_cart, products)
        checkout_data, ship_addr, subtotal = await loop.run_in_executor(None,self.checkout)

        vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": 0,
            "subtotal_amount": subtotal,
            "shipping_amount": "",
            "tax_amount": "",
            "total_amount": "",
            "payment_method": "",
            "shipping_address": ship_addr,
            "order_id":f"{uuid.uuid4()}",
        }
        vendor_slug: str = self.vendor.slug
        return {
            vendor_slug: {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            },
        }

    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
        print("DCDental/confirm_order")
        self.reqsession = requests.Session()
        loop = asyncio.get_event_loop()
        await self.login()
        await loop.run_in_executor(None,self.clear_cart)
        await loop.run_in_executor(None,self.add_to_cart, products)
        checkout_data, ship_addr, subtotal = await loop.run_in_executor(None,self.checkout)
        if fake:
            vendor_order_detail = {
                "retail_amount": "",
                "savings_amount": 0,
                "subtotal_amount": subtotal,
                "shipping_amount": "",
                "tax_amount": "",
                "total_amount": "",
                "payment_method": "",
                "shipping_address": ship_addr,
                "order_id":f"{uuid.uuid4()}",
            }
            return {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            }
        order_data = await loop.run_in_executor(None, self.review_order, checkout_data)
        order_num, tax, total = await loop.run_in_executor(None, self.place_order, order_data)
        print("Order Number:", order_num)
        vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": 0,
            "subtotal_amount": subtotal,
            "shipping_amount": "",
            "tax_amount": tax,
            "total_amount": total,
            "payment_method": "",
            "shipping_address": ship_addr,
            "order_id":order_num,
        }
        return {
            **vendor_order_detail,
            **self.vendor.to_dict(),
        }
