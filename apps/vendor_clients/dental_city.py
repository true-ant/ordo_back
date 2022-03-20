import asyncio
from typing import Optional, Union

from aiohttp import ClientResponse
from scrapy import Selector

from apps.vendor_clients.base import BaseClient
from apps.vendor_clients.types import CartProduct, LoginInformation

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

GET_CART_HEADERS = {
    "authority": "www.dentalcity.com",
    "pragma": "no-cache",
    "cache-control": "no-cache",
    "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    "accept": "*/*",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.dentalcity.com/cart/shoppingcart",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

REMOVE_PRODUCT_FROM_CART_HEADERS = {
    "authority": "www.dentalcity.com",
    "pragma": "no-cache",
    "cache-control": "no-cache",
    "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    "accept": "*/*",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "sec-ch-ua-platform": '"Windows"',
    "origin": "https://www.dentalcity.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.dentalcity.com/cart/shoppingcart",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

ADD_PRODUCT_TO_CART_HEADERS = {
    "authority": "www.dentalcity.com",
    "pragma": "no-cache",
    "cache-control": "no-cache",
    "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="98", "Google Chrome";v="98"',
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "sec-ch-ua-platform": '"Windows"',
    "origin": "https://www.dentalcity.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.dentalcity.com/cart/shoppingcart",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

GET_PRODUCT_PAGE_HEADERS = {
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
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}


class DentalCityClient(BaseClient):
    VENDOR_SLUG = "dental_city"

    async def get_login_data(self, *args, **kwargs) -> LoginInformation:
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

    async def check_authenticated(self, response: ClientResponse) -> bool:
        text = await response.text()
        dom = Selector(text=text)
        login_success = dom.xpath("//input[@id='Message']/@value").get()
        return login_success == "success"

    async def get_cart_page(self) -> Union[Selector, dict]:
        return await self.get_response_as_dom(
            url="https://www.dentalcity.com/widgets-cart/gethtml_shoppingcart",
            headers=GET_CART_HEADERS,
        )

    async def remove_product_from_cart(self, data):
        await self.session.post(
            "https://www.dentalcity.com/widgets-cart/removeitem/", headers=REMOVE_PRODUCT_FROM_CART_HEADERS, json=data
        )

    async def clear_cart(self):
        cart_dom = await self.get_cart_page()
        tasks = []
        for line_id in cart_dom.xpath('//div[@class="shoppinglist"]/ul//input[@name="qty"]/@id').extract():
            data = {"OrderLines": [{"LineID": line_id}]}
            tasks.append(self.remove_product_from_cart(data))

        await asyncio.gather(*tasks)

    async def add_product_to_cart(self, product: CartProduct, *args, **kwargs):
        # TODO: We should store sku id to our database
        product_page_dom = await self.get_product_page(
            product_link=product["product"]["url"], headers=GET_PRODUCT_PAGE_HEADERS
        )
        sku_id = product_page_dom.xpath('//input[@name="SkuId"]/@value').get()

        data = {
            "IsFreightApplicable": True,
            "IsShippingDiscountApplicable": False,
            "IsProcessRestrictedDiscounts": False,
            "ResetShipments": False,
            "MarkDiscountsAsApplied": False,
            "IsOrderDiscountApplicable": False,
            "IsLineDiscountApplicable": False,
            "RecalculateUnitPrice": False,
            "RecalculateShippingCharges": False,
            "IsOpportunity": False,
            "IsNewLine": False,
            "IsNewOrder": False,
            "IsCalculateTotal": True,
            "IsCalculateTax": True,
            "WriteInSkuConversionNotificationRequired": False,
            "OverrideExportCompleted": False,
            "OrderEntity": {
                "OrderHeader": {
                    "UpdatedPropertyBag": [
                        "PaymentTotal",
                    ],
                    "orderCount": 0,
                    "groupedOrderTotal": 0,
                    "totalQuantity": 0,
                    "totalDiscount": 0,
                    "CustomerType": 0,
                    "SendEmailOnFraud": False,
                    "RecalculatePrice": False,
                    "RecalculateTax": False,
                    "RecalculateShipping": False,
                    "ShipMethodTaxCategoryId": 0,
                    "IsOrderShipable": True,
                    "UpdateUsername": False,
                    "TrackingNumbers": [],
                    "StoreID": 0,
                    "OrderID": 0,
                    "MiscCharges": 0,
                    "PaymentTotal": 0,
                },
                "OrderLines": [
                    {
                        "UpdatedPropertyBag": [],
                        "RelatedOrderLines": [],
                        "IsNonShippableLinesExists": False,
                        "LineNum": 0,
                        "SkuId": sku_id,
                        "Qty": product["quantity"],
                        "StoreID": 0,
                        "OrderID": 0,
                        "LineID": 0,
                        "MiscCharges": 0,
                    },
                ],
                "WriteInSkuReferences": [],
                "OrderShipments": [],
            },
            "ProcessCheckList": {
                "RunHoldCheckProcess": True,
                "RunFraudCheckProcess": True,
                "RunApprovalCheckProcess": True,
                "RunAggregateOrdeLineStatusCheckProcess": True,
                "PaymentProcess": "Authorize",
            },
            "DesiredStatus": {
                "DocumentStatusId": 0,
                "OrderStatusId": 0,
            },
            "DesiredQuoteStatus": {
                "DocumentStatusId": 0,
                "QuoteStatusId": 0,
            },
            "DesiredOpportunityStatus": {
                "DocumentStatusId": 0,
                "OpportunityStatusId": 0,
            },
        }
        await self.session.post(
            "https://www.dentalcity.com/cart/addtocart", headers=ADD_PRODUCT_TO_CART_HEADERS, json=data
        )

    async def checkout_and_review_order(self, shipping_method: Optional[str] = None) -> dict:
        pass
