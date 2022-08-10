from typing import Dict, List

from aiohttp import ClientResponse
from scrapy import Selector

from apps.scrapers.base import Scraper
from apps.scrapers.henryschein import CHECKOUT_HEADER
from apps.scrapers.schema import VendorOrderDetail
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
                            'SkuId': product['skuid'],
                            'Qty': product['qty'],
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

            response = await self.session.post('https://www.dentalcity.com/cart/addtocart', headers=ADD_CART_HEADERS, json=json_data)

    async def checkout(self):
        response = await self.session.get('https://www.dentalcity.com/widgets-checkout/getheader/html_revieworder', headers=CHECKOUT_HEADER)
        response_dom = Selector(text=await response.text())

        billing_address = "\n".join([
            "".join(item.xpath('.//text()').extract()).strip()
            for item in response_dom.xpath('//div[@id="defaultbilling"]/div')
        ])
        print("--- Billing Address:\n", billing_address.strip() if billing_address else "")

        shipping_address = "\n".join([
            "".join(item.xpath('.//text()').extract())
            for item in response_dom.xpath('//div[@id="defaultshipping"]/div')
        ])
        print("--- Shipping Address:\n", shipping_address.strip() if shipping_address else "")

        response = await self.session.get('https://www.dentalcity.com/widgets-checkout/getheader/html_ordersingleshipping', headers=SHIPPING_ADDRESS_HEADERS)
        dom = Selector(text=await response.text())

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

        await self.session.post('https://www.dentalcity.com/widgets-checkout/saveheader/html_shippingaddress/saveshippingaddress/', headers=SAVE_SHIPPING_HEADERS, data=data)

        response = await self.session.get('https://www.dentalcity.com/widgets-checkout/getheader/html_ordersingleshipping', headers=WIDGET_CHECK_HEADERS)
        response_dom = Selector(text=await response.text())

        data = {
            'OrderHeader.ShipToAddressID': response_dom.xpath('//select[@name="CurrentAddress"]/option[@selected="selected"]/@value').get().split("~")[0],
            'OrderHeader.ShipToCountryCode': response_dom.xpath('//input[@name="OrderHeader.ShipToCountryCode"]/@value').get(),
            'OrderHeader.ShipToFirstName': response_dom.xpath('//input[@name="OrderHeader.ShipToFirstName"]/@value').get(),
            'OrderHeader.ShipToLastName': response_dom.xpath('//input[@name="OrderHeader.ShipToLastName"]/@value').get(),
            'OrderHeader.ShipToCompanyName': response_dom.xpath('//input[@name="OrderHeader.ShipToCompanyName"]/@value').get(),
            'OrderHeader.ShipToAddress': response_dom.xpath('//input[@name="OrderHeader.ShipToAddress"]/@value').get(),
            'OrderHeader.ShipToAddress2': response_dom.xpath('//input[@name="OrderHeader.ShipToAddress2"]/@value').get(),
            'OrderHeader.ShipToAddress3': response_dom.xpath('//input[@name="OrderHeader.ShipToAddress3"]/@value').get(),
            'OrderHeader.ShipToPhone': response_dom.xpath('//input[@name="OrderHeader.ShipToPhone"]/@value').get(),
            'OrderHeader.ShipToPhoneExtension': response_dom.xpath('//input[@name="OrderHeader.ShipToPhoneExtension"]/@value').get(),
            'OrderHeader.ShipToPhone2': response_dom.xpath('//input[@name="OrderHeader.ShipToPhone2"]/@value').get(),
            'OrderHeader.ShipToPhoneExtension2': response_dom.xpath('//input[@name="OrderHeader.ShipToPhoneExtension2"]/@value').get(),
            'OrderHeader.ShipToPhone3': response_dom.xpath('//input[@name="OrderHeader.ShipToPhone3"]/@value').get(),
            'OrderHeader.ShipToPhoneExtension3': response_dom.xpath('//input[@name="OrderHeader.ShipToPhoneExtension3"]/@value').get(),
            'OrderHeader.ShipToFax': response_dom.xpath('//input[@name="OrderHeader.ShipToFax"]/@value').get(),
            'OrderHeader.ShipToCity': response_dom.xpath('//input[@name="OrderHeader.ShipToCity"]/@value').get(),
            'OrderHeader.ShipToRegionCode': response_dom.xpath('//input[@name="OrderHeader.ShipToRegionCode"]/@value').get(),
            'OrderHeader.ShipToCounty': response_dom.xpath('//input[@name="OrderHeader.ShipToCounty"]/@value').get(),
            'OrderHeader.ShipToZipCode': response_dom.xpath('//input[@name="OrderHeader.ShipToZipCode"]/@value').get(),
            'OrderHeader.ShipToMethodID': response_dom.xpath('//input[@name="OrderHeader.ShipToMethodID"]/@value').get()
        }

        response = await self.session.post('https://www.dentalcity.com/checkout/gethtml_shippingquotations/', headers=SECURE_CHECKOUT_HEADERS, data=data)
        response_dom = Selector(text=await response.text())
        
        data = {
            'SelectedShippingMethodValue': response_dom.xpath('//input[@name="SelectedShippingMethodValue"]/@value').get(),
            'Message': ''
        }

        response = await self.session.post(
            'https://www.dentalcity.com/widgets-checkout/saveheader/html_shippingquotations/saveshippingquotations',
            headers=SECURE_CHECKOUT_HEADERS, data=data
        )

        response = await self.session.post('https://www.dentalcity.com/widgets-checkout/getheader/html_totalcalculations', headers=CALCULATION_HEADERS)
        response_dom = Selector(text=await response.text())

        sub_total = response_dom.xpath('//span[@id="ordersubtotal"]//text()').get()
        print("--- sub_total:\n", sub_total.strip() if sub_total else "")
            
        shipping = response_dom.xpath('//label[contains(text(), "Shipping")]/following-sibling::span[@class="price"]//text()').get()
        print("--- shipping:\n", shipping.strip() if shipping else "")
            
        tax = response_dom.xpath('//label[contains(text(), "Tax")]/following-sibling::span[@class="price"]//text()').get()
        print("--- tax:\n", tax.strip() if tax else "")
            
        saved = response_dom.xpath('//label[contains(text(), "You Saved")]/following-sibling::span[@class="price"]//text()').get()
        print("--- saved:\n", saved.strip() if saved else "")

        order_total = response_dom.xpath('//label[contains(text(), "Order Total")]/following-sibling::span[@class="price"]//text()').get()
        print("--- order_total:\n", order_total.strip() if order_total else "")

        return shipping_address, sub_total, shipping, tax, saved, order_total

    async def create_order(self, products: List[CartProduct], shipping_method=None) -> Dict[str, VendorOrderDetail]:
        await self.login()
        await self.clear_cart()
        await self.add_to_cart(products)
        shipping_address, sub_total, shipping, tax, saved, order_total = await self.checkout()

        vendor_order_detail = {
            "retail_amount": "",
            "savings_amount": saved,
            "subtotal_amount": sub_total,
            "shipping_amount": shipping,
            "tax_amount": tax,
            "total_amount": order_total,
            "payment_method": "",
            "shipping_address": shipping_address,
        }
        vendor_slug: str = self.vendor.slug
        return {
            vendor_slug: {
                **vendor_order_detail,
                **self.vendor.to_dict(),
            },
        }

    async def confirm_order(self, products: List[CartProduct], shipping_method=None, fake=False):
        await self.login()
        await self.clear_cart()
        await self.add_to_cart(products)
        shipping_address, sub_total, shipping, tax, saved, order_total = await self.checkout()
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

