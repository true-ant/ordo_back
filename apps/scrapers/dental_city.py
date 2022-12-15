
import asyncio
import datetime
from decimal import Decimal
import uuid
import scrapy
import re
from typing import Dict, List, Optional

from aiohttp import ClientResponse, ClientSession
from scrapy import Selector

from apps.common import messages as msgs
from apps.scrapers.base import Scraper
from apps.scrapers.schema import VendorOrderDetail, Order
from apps.scrapers.utils import catch_network, semaphore_coroutine
from apps.types.orders import CartProduct
from apps.types.scraper import LoginInformation, ProductSearch

LOGIN_PAGE_HEADERS = {
    "authority": "www.dentalcity.com",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "referer": "https://www.dentalcity.com/",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

LOGIN_HEADERS = {
    "authority": "www.dentalcity.com",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "accept": "*/*",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
    "sec-ch-ua-platform": '"Windows"',
    "origin": "https://www.dentalcity.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.dentalcity.com/account/login",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

CART_PAGE_HEADERS = {
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    'accept': '*/*',
    'x-requested-with': 'XMLHttpRequest',
    'sec-ch-ua-mobile': '?0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://www.dentalcity.com/cart/shoppingcart',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
CLEAR_CART_HEADERS = {
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    'accept': '*/*',
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'x-requested-with': 'XMLHttpRequest',
    'sec-ch-ua-mobile': '?0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
    'sec-ch-ua-platform': '"Windows"',
    'origin': 'https://www.dentalcity.com',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://www.dentalcity.com/cart/shoppingcart',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
ADD_CART_HEADERS = {
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    'accept': 'application/json, text/javascript, */*; q=0.01',
    'x-requested-with': 'XMLHttpRequest',
    'sec-ch-ua-mobile': '?0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
    'sec-ch-ua-platform': '"Windows"',
    'origin': 'https://www.dentalcity.com',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://www.dentalcity.com/cart/shoppingcart',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
CHECKOUT_HEADER ={
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
    'accept': '*/*',
    'content-type': 'text/html; charset=utf-8',
    'x-requested-with': 'XMLHttpRequest',
    'sec-ch-ua-mobile': '?0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
SHIPPING_ADDRESS_HEADERS ={
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
    'accept': '*/*',
    'content-type': 'text/html; charset=utf-8',
    'x-requested-with': 'XMLHttpRequest',
    'sec-ch-ua-mobile': '?0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
SAVE_SHIPPING_HEADERS = {
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
    'accept': '*/*',
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'x-requested-with': 'XMLHttpRequest',
    'sec-ch-ua-mobile': '?0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
    'sec-ch-ua-platform': '"Windows"',
    'origin': 'https://www.dentalcity.com',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
WIDGET_CHECK_HEADERS = {
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
    'accept': '*/*',
    'content-type': 'text/html; charset=utf-8',
    'x-requested-with': 'XMLHttpRequest',
    'sec-ch-ua-mobile': '?0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
SECURE_CHECKOUT_HEADERS = {
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
    'accept': '*/*',
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'x-requested-with': 'XMLHttpRequest',
    'sec-ch-ua-mobile': '?0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36',
    'sec-ch-ua-platform': '"Windows"',
    'origin': 'https://www.dentalcity.com',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}

CALCULATION_HEADERS = {
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
    'accept': '*/*',
    'content-type': 'text/html; charset=utf-8',
    'x-requested-with': 'XMLHttpRequest',
    'sec-ch-ua-mobile': '?0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
SUBMIT_HEADERS = {
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
    'accept': '*/*',
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'x-requested-with': 'XMLHttpRequest',
    'sec-ch-ua-mobile': '?0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
    'sec-ch-ua-platform': '"Windows"',
    'origin': 'https://www.dentalcity.com',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
PROCESS_PAYMENT_HEADERS = {
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
    'accept': '*/*',
    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'x-requested-with': 'XMLHttpRequest',
    'sec-ch-ua-mobile': '?0',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
    'sec-ch-ua-platform': '"Windows"',
    'origin': 'https://www.dentalcity.com',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
ORDER_COMPLETE_HEADERS = {
    'authority': 'www.dentalcity.com',
    'pragma': 'no-cache',
    'cache-control': 'no-cache',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-user': '?1',
    'sec-fetch-dest': 'document',
    'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}
ORDER_HEADERS ={
    'authority': 'www.dentalcity.com',
    'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-user': '?1',
    'sec-fetch-dest': 'document',
    'referer': 'https://www.dentalcity.com/account/login',
    'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
}

def extractContent(dom, xpath):
    return re.sub(r"\s+", " ", " ".join(dom.xpath(xpath).extract())).strip()
class DentalCityScraper(Scraper):
    BASE_URL = "https://www.dentalcity.com"
    CATEGORY_URL = "https://www.henryschein.com/us-en/dental/c/browsesupplies"
    TRACKING_BASE_URL = "https://narvar.com/tracking/itemvisibility/v1/henryschein-dental/orders"

    async def _check_authenticated(self, response: ClientResponse) -> bool:
        text = await response.text()
        dom = Selector(text=text)
        login_success = dom.xpath("//input[@id='Message']/@value").get()
        return login_success == "success"

    async def _get_login_data(self, *args, **kwargs) -> LoginInformation:
        await self.session.get("https://www.dentalcity.com/account/login", headers=LOGIN_PAGE_HEADERS)
        return {
            "url": "https://www.dentalcity.com/account/login/",
            "headers": LOGIN_HEADERS,
            "data": {
                "UserName": self.username,
                "Password": self.password,
                "ReturnUrl": "",
                "Message": "",
                "Name": "",
                "DashboardURL": "https://www.dentalcity.com/profile/dashboard",
            },
        }

    async def _search_products(
        self, query: str, page: int = 1, min_price: int = 0, max_price: int = 0, sort_by="price", office_id=None
    ) -> ProductSearch:
        return await self._search_products_from_table(query, page, min_price, max_price, sort_by, office_id)

    async def clear_cart(self):
        response = await self.session.get('https://www.dentalcity.com/widgets-cart/gethtml_shoppingcart', headers=CART_PAGE_HEADERS)
        cart_page = await response.text()
        dom = Selector(text=cart_page)

        for line_id in dom.xpath('//div[@class="shoppinglist"]/ul//input[@name="qty"]/@id').extract():
            data = {"OrderLines": [{"LineID":line_id}]}
            response = await self.session.post('https://www.dentalcity.com/widgets-cart/removeitem/', headers=CLEAR_CART_HEADERS, json=data)
        
    async def add_to_cart(self, products):
        headers = {
            'authority': 'www.dentalcity.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'origin': 'https://www.dentalcity.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.dentalcity.com/cart/shoppingcart',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        for product in products:
            json_data = {
                'IsFreightApplicable': True,
                'IsShippingDiscountApplicable': False,
                'IsProcessRestrictedDiscounts': False,
                'ResetShipments': False,
                'MarkDiscountsAsApplied': False,
                'IsOrderDiscountApplicable': False,
                'IsLineDiscountApplicable': False,
                'RecalculateUnitPrice': False,
                'RecalculateShippingCharges': False,
                'IsOpportunity': False,
                'IsNewLine': False,
                'IsNewOrder': False,
                'IsCalculateTotal': True,
                'IsCalculateTax': True,
                'WriteInSkuConversionNotificationRequired': False,
                'OverrideExportCompleted': False,
                'OrderEntity': {
                    'OrderHeader': {
                        'UpdatedPropertyBag': [
                            'PaymentTotal',
                        ],
                        'orderCount': 0,
                        'groupedOrderTotal': 0,
                        'totalQuantity': 0,
                        'totalDiscount': 0,
                        'CustomerType': 0,
                        'SendEmailOnFraud': False,
                        'RecalculatePrice': False,
                        'RecalculateTax': False,
                        'RecalculateShipping': False,
                        'ShipMethodTaxCategoryId': 0,
                        'IsOrderShipable': True,
                        'UpdateUsername': False,
                        'TrackingNumbers': [],
                        'StoreID': 0,
                        'OrderID': 0,
                        'MiscCharges': 0,
                        'PaymentTotal': 0,
                    },
                    'OrderLines': [
                        {
                            'UpdatedPropertyBag': [],
                            'RelatedOrderLines': [],
                            'IsNonShippableLinesExists': False,
                            'LineNum': 0,
                            'SkuId': product['product_id'],
                            'Qty': product['quantity'],
                            'StoreID': 0,
                            'OrderID': 0,
                            'LineID': 0,
                            'MiscCharges': 0,
                        },
                    ],
                    'WriteInSkuReferences': [],
                    'OrderShipments': [],
                },
                'ProcessCheckList': {
                    'RunHoldCheckProcess': True,
                    'RunFraudCheckProcess': True,
                    'RunApprovalCheckProcess': True,
                    'RunAggregateOrdeLineStatusCheckProcess': True,
                    'PaymentProcess': 'Authorize',
                },
                'DesiredStatus': {
                    'DocumentStatusId': 0,
                    'OrderStatusId': 0,
                },
                'DesiredQuoteStatus': {
                    'DocumentStatusId': 0,
                    'QuoteStatusId': 0,
                },
                'DesiredOpportunityStatus': {
                    'DocumentStatusId': 0,
                    'OpportunityStatusId': 0,
                },
            }

            response = await self.session.post('https://www.dentalcity.com/cart/addtocart', headers=headers, json=json_data)

    async def proceed_checkout(self):
        headers = {
            'authority': 'www.dentalcity.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            'accept': '*/*',
            'content-type': 'text/html; charset=utf-8',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        response = await self.session.get('https://www.dentalcity.com/widgets-checkout/getheader/html_revieworder', headers=headers)
        response_dom = Selector(text=await response.text())

        billing_address = "\n".join([
            "".join(item.xpath('.//text()').extract()).strip()
            for item in response_dom.xpath('//div[@id="defaultbilling"]/div')
        ])
        # print("--- Billing Address:\n", billing_address.strip() if billing_address else "")

        shipping_address = "\n".join([
            "".join(item.xpath('.//text()').extract())
            for item in response_dom.xpath('//div[@id="defaultshipping"]/div')
        ])
        # print("--- Shipping Address:\n", shipping_address.strip() if shipping_address else "")
        return shipping_address

    async def save_shipping_address(self):
        headers = {
            'authority': 'www.dentalcity.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            'accept': '*/*',
            'content-type': 'text/html; charset=utf-8',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        response = await self.session.get('https://www.dentalcity.com/widgets-checkout/getheader/html_ordersingleshipping', headers=headers)
        dom = Selector(text=await response.text())

        headers = {
            'authority': 'www.dentalcity.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'origin': 'https://www.dentalcity.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        data = {
            'OrderHeader.ShipToAddressName': '',
            'ShippingAddress.CurrentAddress': '',
            'ShippingAddress.CurrentSelectedAddress': '',
            'Message': '',
            'ShippingAddress.i_address_type': '',
            'ShippingAddress.IsPrimary': '',
            'OrderHeader.ShipToState': '',
            'OrderHeader.ShipToMethodID': '',
            'OrderHeader.ShipToCountryCode': '',
            'OrderHeader.ShipToRegionCode': '',
            'OrderHeader.ShipToCounty': '',
            'OrderHeader.ShipToFirstName': '',
            'OrderHeader.ShipToLastName': '',
            'OrderHeader.ShipToCompanyName': '',
            'OrderHeader.ShipToAddress': '',
            'OrderHeader.ShipToAddress2': '',
            'OrderHeader.ShipToAddress3': '',
            'OrderHeader.OrderPlacedBy': '',
            'OrderHeader.ShipToPhone': '',
            'OrderHeader.ShipToPhoneExtension': '',
            'OrderHeader.ShipToPhone2': '',
            'OrderHeader.ShipToPhoneExtension2': '',
            'OrderHeader.ShipToPhone3': '',
            'OrderHeader.ShipToPhoneExtension3': '',
            'OrderHeader.ShipToFax': '',
            'OrderHeader.ShipToCity': '',
            'OrderHeader.ShipToZipCode': '',
            'guestuserregistered': '',
        }

        for key in data.keys():
            val = dom.xpath(f'//input[@name="{key}"]/@value').get()
            data[key] = val if val else ""

        await self.session.post('https://www.dentalcity.com/widgets-checkout/saveheader/html_shippingaddress/saveshippingaddress/', headers=headers, data=data)

    async def shipping_quotation(self):
        headers = {
            'authority': 'www.dentalcity.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            'accept': '*/*',
            'content-type': 'text/html; charset=utf-8',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        response = await self.session.get('https://www.dentalcity.com/widgets-checkout/getheader/html_ordersingleshipping', headers=headers)
        response_dom = Selector(text=await response.text())

        headers = {
            'authority': 'www.dentalcity.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'origin': 'https://www.dentalcity.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }
        data = {
            "OrderHeader.ShipToAddressName": "PRIMARY",
            "guestuserregistered": "",
        }
        for form_value_ele in response_dom.xpath('//form[@id="shippingaddressform"]/input[@name]'):
            _key = form_value_ele.xpath('./@name').get()
            _val = form_value_ele.xpath('./@value').get()
            data[_key] = _val

        response = await self.session.post('https://www.dentalcity.com/checkout/gethtml_shippingquotations/', headers=headers, data=data)
        response_dom = Selector(text=await response.text())
        data = {
            'SelectedShippingMethodValue': response_dom.xpath('//input[@name="SelectedShippingMethodValue"]/@value').get(),
            'Message': ''
        }

        response = await self.session.post(
            'https://www.dentalcity.com/widgets-checkout/saveheader/html_shippingquotations/saveshippingquotations',
            headers=headers, data=data
        )

    async def total_calculation(self):
        headers = {
            'authority': 'www.dentalcity.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            'accept': '*/*',
            'content-type': 'text/html; charset=utf-8',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        response = await self.session.post('https://www.dentalcity.com/widgets-checkout/getheader/html_totalcalculations', headers=headers)
        response_dom = Selector(text=await response.text())

        sub_total = response_dom.xpath('//span[@id="ordersubtotal"]//text()').get()
        # print("--- sub_total:\n", sub_total.strip() if sub_total else "")
            
        shipping = response_dom.xpath('//label[contains(text(), "Shipping")]/following-sibling::span[@class="price"]//text()').get()
        # print("--- shipping:\n", shipping.strip() if shipping else "")
            
        tax = response_dom.xpath('//label[contains(text(), "Tax")]/following-sibling::span[@class="price"]//text()').get()
        # print("--- tax:\n", tax.strip() if tax else "")
            
        saved = response_dom.xpath('//label[contains(text(), "You Saved")]/following-sibling::span[@class="price"]//text()').get()
        # print("--- saved:\n", saved.strip() if saved else "")

        order_total = response_dom.xpath('//label[contains(text(), "Order Total")]/following-sibling::span[@class="price"]//text()').get()
        # print("--- order_total:\n", order_total.strip() if order_total else "")
        return saved, sub_total, shipping, tax, order_total
    
    async def orderDetail(self, order_history):     
        _link = order_history["order_detail_link"]
        order = dict()

        headers = {
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-User': '?1',
        'Sec-Fetch-Dest': 'document',
        'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        response = await self.session.get(_link, headers=headers)
        dom = scrapy.Selector(text=await response.text())
        billing_address = extractContent(
            dom,
            '//div[@id="ordercomplete"]/div[@class="row"]/div[1]'
            '/table[@class="billing-address"]//td/div[@id="Address1"]//text()'
        ) + " " + extractContent(
            dom,
            '//div[@id="ordercomplete"]/div[@class="row"]/div[1]'
            '/table[@class="billing-address"]//td/div[@id="Address2"]//text()'
        )
        shipping_address = extractContent(
            dom,
            '//div[@id="ordercomplete"]/div[@class="row"]/div[2]/'
            'table[@class="billing-address"]//td/div[@id="ShipToAddressLine1n2"]//text()'
        ) + " " + extractContent(
            dom,
            '//div[@id="ordercomplete"]/div[@class="row"]/div[2]/'
            'table[@class="billing-address"]//td/div[@id="ShipToAddressDetails"]//text()'
        )
        order["billing_address"] = billing_address
        order["shipping_address"] = shipping_address
        return order

    @semaphore_coroutine
    async def get_order(self, sem, order, office=None) -> dict:
        print(" === get order ==", office, order)
        order_dict=await self.orderDetail(order_history=order)
        order_dict.update(order)
        order_dict.update({"currency":"USD"})
        print(order_dict)
        
        if office:
            await self.save_order_to_db(office, order=Order.from_dict(order_dict))
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
        if perform_login:
            await self.login()
        results=[]
        url="https://www.dentalcity.com/profile/myorders/"
        async with self.session.get(url, headers=ORDER_HEADERS) as response:
            tasks = []
            dom = scrapy.Selector(text=await response.text())
            __RequestVerificationToken = extractContent(dom, '//form[@id="myordersform"]/input[@name="__RequestVerificationToken"]/@value')
            headers = {
                'authority': 'www.dentalcity.com',
                'accept': '*/*',
                'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
                'cache-control': 'no-cache',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': 'https://www.dentalcity.com',
                'pragma': 'no-cache',
                'referer': 'https://www.dentalcity.com/profile/myorders/',
                'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="100", "Google Chrome";v="100"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36',
                'x-requested-with': 'XMLHttpRequest',
            }

            data = {
                '__RequestVerificationToken': __RequestVerificationToken,
                'OrderStartDate': '',
                'OrderEndDate': '',
                'SelectedOrderType': 'ALLEXCEPTQUOTE',
                'pager.PageSize': '10',
                'pager.TotalItems': '0',
                'pager.CurrentPage': '1',
            }
            response = await self.session.post('https://www.dentalcity.com/profile/gethtml_ordersandquotes', headers=headers, data=data)
            dom = scrapy.Selector(text=await response.text())
            for tr_ele in dom.xpath(
                '//form[@id="html_ordersandquotesform"]/div[@class="linecolumn"]'
            ):
                order_history = dict()
                order_history["order_id"] = extractContent(tr_ele, './div[contains(@class, "orderheader")]/div[1]/a//text()')
                order_history["order_date"] = extractContent(tr_ele, './div[contains(@class, "orderheader")]/div[1]/span[@class="place_order"]//text()')
                order_history["status"] = extractContent(tr_ele, './div[contains(@class, "orderheader")]/div[2]/label//text()')
                order_detail_link = extractContent(tr_ele, './div[contains(@class, "orderheader")]/div[1]/a/@href')
                order_history["order_detail_link"] = order_detail_link
                for product_row in tr_ele.xpath('./div[@class="ord-lin-cont"]/table//tr'):
                    if not product_row.xpath('./td[@data-th="SKU"]'): continue
                    product = dict()
                    product["product_id"] = extractContent(product_row, './td[@data-th="SKU"]//text()')
                    product["name"] = extractContent(product_row, './td[@class="product"]/a//text()')
                    product["qty"] = extractContent(product_row, './td[@data-th="Qty"]//text()')
                    product["product_url"] = extractContent(product_row, './td[@data-th="SKU"]/a[@class="productlink"]/@href')
                    product["vendor"] = self.vendor.to_dict()
                    order_history["products"].append({
                                "product":product, 
                                "quantity": product.pop("qty"),
                                "unit_price": product.pop("unit_price"),
                            })
                results.append(order_history)
            
            tasks=[]
            print("===========33434============")
            print(completed_order_ids)
            for order_data in results:
                print("================= #1 ===")
                print(order_data, from_date, to_date)
                month, day, year= order_data["order_date"].split("/")                
                order_date = datetime.date(int(year), int(month), int(day))
                order_data["order_date"] = order_date
                if from_date and to_date and (order_date < from_date or order_date > to_date):
                    continue

                if completed_order_ids and str(order_data["order_id"]) in completed_order_ids:
                    continue

                tasks.append(self.get_order(sem, order_data, office))
            print("================= #2 ===")
            print(tasks)
            if tasks:
                orders = await asyncio.gather(*tasks)
                return [Order.from_dict(order) for order in orders if isinstance(order, dict)]
            else:
                return [] 
    async def submit_order(self):
        headers = {
            'authority': 'www.dentalcity.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'origin': 'https://www.dentalcity.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        data = {
            'OrderHeader.OrderComments1': '',
        }

        response = await self.session.post('https://www.dentalcity.com/widgets-checkout/saveheader/html_ordercomments/saveordercomments', headers=headers, data=data)

        headers = {
            'authority': 'www.dentalcity.com',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'x-requested-with': 'XMLHttpRequest',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.84 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'origin': 'https://www.dentalcity.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.dentalcity.com/widgets-checkout/securedcheckout',
            'accept-language': 'en-US,en;q=0.9,ko;q=0.8,pt;q=0.7',
        }

        data = 'OrderHeader.creditCardId=6648&OrderHeader.CCCSCCode=&txtccYearMonth=XXXXX-XXXXX&OrderHeader.UDF3=&guestuserregistered=&OrderHeader.LastFourDigit=5020&SaveCreditCard=false&guestuserregistered=&PaymentOptionsGroup=Terms+(PO)&txtcompanyName=Columbine+Creek+Dentistry&txtAccountNumber=222234&OrderHeader.ReferenceNumber1=&guestuserregistered=&OrderHeader.PaymentMethod=Terms+(PO)&guestuserregistered='

        data = [
            ('OrderHeader.creditCardId', '6648'),
            ('OrderHeader.CCCSCCode', ''),
            ('txtccYearMonth', 'XXXXX-XXXXX'),
            ('OrderHeader.UDF3', ''),
            ('guestuserregistered', ''),
            ('guestuserregistered', ''),
            ('guestuserregistered', ''),
            ('guestuserregistered', ''),
            ('OrderHeader.LastFourDigit', '5020'),
            ('SaveCreditCard', 'false'),
            ('PaymentOptionsGroup', 'Terms (PO)'),
            ('txtcompanyName', 'Columbine Creek Dentistry'),
            ('txtAccountNumber', '222234'),
            ('OrderHeader.ReferenceNumber1', ''),
            ('OrderHeader.PaymentMethod', 'Terms (PO)'),
        ]

        await self.session.post('https://www.dentalcity.com/widgets-checkout/processpayment', headers=headers, data=data)


    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        print("dentalcity/create_order")
        try:
            await asyncio.sleep(0.5)
            raise Exception()
            await self.login()
            await self.clear_cart()
            await self.add_to_cart(products)
            shipping_address = await self.proceed_checkout()
            await self.save_shipping_address()
            await self.shipping_quotation()
            saved, sub_total, shipping, tax, order_total = await self.total_calculation()
            vendor_order_detail = VendorOrderDetail.from_dict({
                "retail_amount": "",
                "savings_amount": saved.strip("$") if isinstance(saved, str) else saved,
                "subtotal_amount": sub_total.strip("$") if isinstance(sub_total, str) else sub_total,
                "shipping_amount": shipping.strip("$") if isinstance(shipping, str) else shipping,
                "tax_amount": tax.strip("$") if isinstance(tax, str) else tax,
                "total_amount": order_total.strip("$") if isinstance(order_total, str) else order_total,
                "reduction_amount": order_total.strip("$") if isinstance(order_total, str) else order_total,
                "payment_method": "",
                "shipping_address": shipping_address,
            })
        except:
            subtotal_manual = sum([prod['price']*prod['quantity'] for prod in products])
            vendor_order_detail =VendorOrderDetail(
                retail_amount=0,
                savings_amount=0,
                subtotal_amount=Decimal(subtotal_manual),
                shipping_amount=0,
                tax_amount=0,
                total_amount=Decimal(subtotal_manual),
                reduction_amount=Decimal(subtotal_manual),
                payment_method="",
                shipping_address="",
            )
        
        vendor_slug: str = self.vendor.slug
        print("dentalcity/create_order DONE")
        return {
            vendor_slug: {
                **vendor_order_detail.to_dict(),
                **self.vendor.to_dict(),
            },
        }

    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False, redundancy=False):
        print("dental_city/confirm_order")
        self.backsession = self.session
        self.session = ClientSession()
        try:
            await asyncio.sleep(1)
            raise Exception()
            await self.login()
            await self.clear_cart()
            await self.add_to_cart(products)
            shipping_address = await self.proceed_checkout()
            await self.save_shipping_address()
            await self.shipping_quotation()
            saved, sub_total, shipping, tax, order_total = await self.total_calculation()
            if fake:
                vendor_order_detail = VendorOrderDetail.from_dict({
                    "retail_amount": "0.0",
                    "savings_amount": saved.strip("$") if isinstance(saved, str) else saved,
                    "subtotal_amount": sub_total.strip("$") if isinstance(sub_total, str) else sub_total,
                    "shipping_amount": shipping.strip("$") if isinstance(shipping, str) else shipping,
                    "tax_amount": tax.strip("$") if isinstance(tax, str) else tax,
                    "total_amount": order_total.strip("$") if isinstance(order_total, str) else order_total,
                    "payment_method": "",
                    "shipping_address": shipping_address
                })
                await self.session.close()
                self.session = self.backsession
                return {
                    **vendor_order_detail.to_dict(),
                    **self.vendor.to_dict(),
                    "order_id":f"{uuid.uuid4()}",
                    "order_type": msgs.ORDER_TYPE_ORDO
                }
            data = {
                'OrderHeader.OrderComments1': '',
            }

            response = await self.session.post('https://www.dentalcity.com/widgets-checkout/saveheader/html_ordercomments/saveordercomments', headers=SUBMIT_HEADERS, data=data)
            data = [
                ('OrderHeader.creditCardId', '6648'),
                ('OrderHeader.CCCSCCode', ''),
                ('txtccYearMonth', 'XXXXX-XXXXX'),
                ('OrderHeader.UDF3', ''),
                ('guestuserregistered', ''),
                ('guestuserregistered', ''),
                ('guestuserregistered', ''),
                ('guestuserregistered', ''),
                ('OrderHeader.LastFourDigit', '5020'),
                ('SaveCreditCard', 'false'),
                ('PaymentOptionsGroup', 'Terms (PO)'),
                ('txtcompanyName', 'Columbine Creek Dentistry'),
                ('txtAccountNumber', '222234'),
                ('OrderHeader.ReferenceNumber1', ''),
                ('OrderHeader.PaymentMethod', 'Terms (PO)'),
            ]

            await self.session.post('https://www.dentalcity.com/widgets-checkout/processpayment', headers=PROCESS_PAYMENT_HEADERS, data=data)
            response = await self.session.get('https://www.dentalcity.com/checkout/ordercomplete', headers=ORDER_COMPLETE_HEADERS)
            
            dom = Selector(text=await response.text())
            order_num = dom.xpath('//div[@class="ordercomplete-total"]/ul/li//a[@title]/@title').get()
            print("Order Num:", order_num)
            
            vendor_order_detail = VendorOrderDetail.from_dict({
                "retail_amount": "0.0",
                "savings_amount": saved.strip("$") if isinstance(saved, str) else saved,
                "subtotal_amount": sub_total.strip("$") if isinstance(sub_total, str) else sub_total,
                "shipping_amount": shipping.strip("$") if isinstance(shipping, str) else shipping,
                "tax_amount": tax.strip("$") if isinstance(tax, str) else tax,
                "total_amount": order_total.strip("$") if isinstance(order_total, str) else order_total,
                "payment_method": "",
                "shipping_address": shipping_address,
                "order_id": order_num,
                "order_type": msgs.ORDER_TYPE_ORDO
            })
            await self.session.close()
            self.session = self.backsession
            return {
                **vendor_order_detail.to_dict(),
                **self.vendor.to_dict(),
            }
        except:
            print("dental_city/confirm_order Except")
            subtotal_manual = sum([prod['price']*prod['quantity'] for prod in products])
            vendor_order_detail =VendorOrderDetail(
                retail_amount=Decimal(0),
                savings_amount=Decimal(0),
                subtotal_amount=Decimal(subtotal_manual),
                shipping_amount=Decimal(0),
                tax_amount=Decimal(0),
                total_amount=Decimal(subtotal_manual),
                reduction_amount=Decimal(subtotal_manual),
                payment_method="",
                shipping_address=""
            )
            return {
                **vendor_order_detail.to_dict(),
                **self.vendor.to_dict(),
                "order_id":f"{uuid.uuid4()}",
                "order_type": msgs.ORDER_TYPE_REDUNDANCY
            }

