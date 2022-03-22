import datetime
import json
from decimal import Decimal
from typing import Dict, List, Optional, Union

from aiohttp import ClientResponse
from scrapy import Selector

from apps.common.utils import (
    concatenate_strings,
    convert_string_to_price,
    strip_whitespaces,
)
from apps.vendor_clients import types
from apps.vendor_clients.base import BASE_HEADERS, BaseClient

LOGIN_HEADERS = {
    **BASE_HEADERS,
    "authority": "www.henryschein.com",
    "n": "pikP/UtnnyEIsCZl3cphEgyUhacC9CnLZqSaDcvfufM=",
    "iscallingfromcms": "False",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "origin": "https://www.henryschein.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.henryschein.com/us-en/Profiles/Logout.aspx?redirdone=1",
}

CLEAR_CART_HEADERS = {
    **BASE_HEADERS,
    "authority": "www.henryschein.com",
    "n": "faMC175siE4Ji7eGjyxEnEahdp30gAd6F12KILNn68E=",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua-platform": '"Windows"',
    "origin": "https://www.henryschein.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx",
}

ADD_PRODUCTS_TO_CART_HEADERS = {
    "authority": "www.henryschein.com",
    "sec-ch-ua": '"Google Chrome";v="95", "Chromium";v="95", ";Not A Brand";v="99"',
    "n": "8Q66eFEZrl21cfd7A18MlrVGecsxls25GU/+P6Nw3QM=",
    "iscallingfromcms": "False",
    "sec-ch-ua-mobile": "?0",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "x-requested-with": "XMLHttpRequest",
    "sec-ch-ua-platform": '"Windows"',
    "origin": "https://www.henryschein.com",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "referer": "https://www.henryschein.com",
    "accept-language": "en-US,en;q=0.9,ko;q=0.8,pt;q=0.7",
}

CHECKOUT_HEADER = {
    **BASE_HEADERS,
    "authority": "www.henryschein.com",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "origin": "https://www.henryschein.com",
    "content-type": "application/x-www-form-urlencoded",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
}

GET_PRODUCT_PRICES_HEADERS = {
    **BASE_HEADERS,
    "authority": "www.henryschein.com",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "accept": "text/html,application/xhtml+xml, application/xml;q=0.9, "
    "image/avif,image/webp,image/apng, */*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "sec-fetch-site": "none",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
}


class HenryScheinClient(BaseClient):
    VENDOR_SLUG = "henry_schein"

    async def get_login_data(self, *args, **kwargs) -> Optional[types.LoginInformation]:
        """Provide login credentials and additional data along with headers"""
        async with self.session.get("https://www.henryschein.com/us-en/dental/Default.aspx") as resp:
            text = await resp.text()
            n = text.split("var _n =")[1].split(";")[0].strip(" '")
        self.session.headers.update({"n": n})
        return {
            "url": "https://www.henryschein.com/webservices/LoginRequestHandler.ashx",
            "headers": LOGIN_HEADERS,
            "data": {
                "username": self.username,
                "password": self.password,
                "did": "dental",
                "searchType": "authenticateuser",
                "culture": "us-en",
            },
        }

    async def check_authenticated(self, response: ClientResponse) -> bool:
        """Check if whether session is authenticated or not"""
        res = await response.json()
        return res.get("IsAuthenticated", False)

    async def get_cart_page(self) -> Union[Selector, dict]:
        """Get cart page in order to get products in cart"""
        return await self.get_response_as_dom(url="https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx")

    def get_checkout_products_sensitive_data(self, dom: Selector) -> dict:
        data = {}
        for i, product_dom in enumerate(
            dom.xpath("//div[@id='ctl00_cphMainContentHarmony_ucOrderCartShop_pnlCartDetails']/ol/li")
        ):
            product_index = f"{i + 1:02d}"
            for key in [
                "$ucProductDetailsForEnhancedView$hiddenProductId",
                "$ucProductDetailsForEnhancedView$hiddenProductAvailabilityCode",
                "$ucProductDetailsForEnhancedView$hiddenInventoryAvailabilityCode",
                "$ucProductDetailsForEnhancedView$hiddenImgProduct",
                "$hdnPriceLabel1",
                "$hdnPriceLabel2",
                "$oldQty",
                "$txtQuantity",
                "$hdnItemId",
                "$ucProductDetailsForEnhancedView$hiddenUom",
            ]:
                key = f"ctl00$cphMainContentHarmony$ucOrderCartShop$rptBasket$ctl{product_index}{key}"
                data[key] = product_dom.xpath(f'.//input[@name="{key}"]/@value').get()
        return data

    async def clear_cart(self):
        # TODO: check if the cart contains products, clear cart only if the cart contains products
        cart_page_dom = await self.get_cart_page()
        data = {
            "__LASTFOCUS": "",
            "ctl00_ScriptManager_TSM": ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, "
            "PublicKeyToken=31bf3856ad364e35:en-US:f319b152-218f-4c14-829d-050a68bb1a61:ea597d4b:b25378d2",
            "__EVENTTARGET": "ctl00$cphMainContentHarmony$ucOrderActionBarBottomShop$btnClearOrder",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": cart_page_dom.xpath("//input[@name='__VIEWSTATE']/@value").get(),
            "__VIEWSTATEGENERATOR": cart_page_dom.xpath("//input[@name='__VIEWSTATEGENERATOR']/@value").get(),
            "ctl00$ucHeader$ucSearchBarHeaderbar$txtSearch": "",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnKeywordText": "Keywords",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnCategoryText": "Category",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnManufacturerText": "Manufacturer",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnContentResultsText": "Content Result",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnRecommendedProducts": "Recommended products for",
            "ctl00$ucHeader$ucSearchBarHeaderbar$hdnAddText": "Add",
            "ctl00$cphMainContentHarmony$ucOrderTopBarShop$txtItemCode": "",
            "ctl00$cphMainContentHarmony$ucOrderTopBarShop$txtQty": "",
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPurchaseOrder": cart_page_dom.xpath(
                '//input[@name="ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPurchaseOrder"]/@value'
            ).get(),
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPromoCode": cart_page_dom.xpath(
                '//input[@name="ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPromoCode"]/@value'
            ).get(),
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtSpecialInstructions": "",
            "dest": "",
        }
        data.update(self.get_checkout_products_sensitive_data(cart_page_dom))
        await self.session.post(
            "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx", headers=CLEAR_CART_HEADERS, data=data
        )

    async def add_products_to_cart(self, products: List[types.CartProduct]):
        item_data_to_add = {"ItemDataToAdd": []}
        for product in products:
            item_data_to_add["ItemDataToAdd"].append(
                {
                    "CheckProductIdForPromoCode": "False",
                    "CheckExternalMapping": "False",
                    "CheckBackOrderStatus": "False",
                    "IsProductInventoryStatusLoaded": "True",
                    "LineItemId": "",
                    "ProductId": product["product"]["product_id"],
                    "Qty": product["quantity"],
                    "Uom": product["product"]["unit"],
                }
            )

        data = {
            "ItemArray": json.dumps(item_data_to_add),
            "searchType": "5",
            "did": "dental",
            "catalogName": "B_DENTAL",
            "endecaCatalogName": "DENTAL",
            "culture": "us-en",
        }

        await self.session.post(
            "https://www.henryschein.com/webservices/JSONRequestHandler.ashx",
            headers=ADD_PRODUCTS_TO_CART_HEADERS,
            data=data,
        )

    async def checkout(self):
        checkout_time = datetime.date.today()
        cart_page_dom = await self.get_cart_page()
        data = {
            "__LASTFOCUS": "",
            "ctl00_ScriptManager_TSM": ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, "
            "PublicKeyToken=31bf3856ad364e35:en-US:f319b152-218f-4c14-829d-050a68bb1a61:ea597d4b:b25378d2",
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": cart_page_dom.xpath("//input[@name='__VIEWSTATE']/@value").get(),
            "__VIEWSTATEGENERATOR": cart_page_dom.xpath("//input[@name='__VIEWSTATEGENERATOR']/@value").get(),
            "ctl00$ucHeader$ucSearchBarHeaderbar$txtSearch": "",
            "ctl00$cphMainContentHarmony$ucOrderActionBarBottomShop$btnCheckout": cart_page_dom.xpath(
                "//input[@name='ctl00$cphMainContentHarmony$ucOrderActionBarBottomShop$btnCheckout']/@value"
            ).get(),
            "layout": "on",
            "ctl00$cphMainContentHarmony$ucOrderTopBarShop$txtItemCode": "",
            "ctl00$cphMainContentHarmony$ucOrderTopBarShop$txtQty": "",
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPurchaseOrder": (
                f'{checkout_time.strftime("%m/%d/%Y")} - Ordo Order'
            ),
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtPromoCode": "",
            "ctl00$cphMainContentHarmony$ucOrderFinalsShop$txtSpecialInstructions": "",
            "dest": "",
        }

        data.update(self.get_checkout_products_sensitive_data(cart_page_dom))

        headers = CHECKOUT_HEADER.copy()
        headers["referer"] = "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx"
        async with self.session.post(
            "https://www.henryschein.com/us-en/Shopping/CurrentCart.aspx", headers=headers, data=data
        ) as resp:
            response_dom = Selector(text=await resp.text())
            if len(response_dom.xpath("//div[@id='MessagePanel']/div[contains(@class, 'informational')]")):
                return await self.checkout()
            else:
                return response_dom

    async def review_checkout(self, checkout_dom: Selector, shipping_method: Optional[str] = None):
        for shipping_method_option in checkout_dom.xpath(
            "//select[@name='ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ddlShippingMethod']/option"
        ):
            if shipping_method_option.xpath("./text()").get() == shipping_method:
                shipping_method_value = shipping_method_option.attrib["value"]
                break
        else:
            shipping_method_value = checkout_dom.xpath(
                "//select[@name='ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ddlShippingMethod']"
                "/option[@selected]/@value"
            ).get()

        data = {
            "ctl00_ScriptManager_TSM": ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, "
            "PublicKeyToken=31bf3856ad364e35:en-US:f319b152-218f-4c14-829d-050a68bb1a61:ea597d4b:b25378d2",
            "__EVENTTARGET": "ctl00$cphMainContentHarmony$hylNext",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": checkout_dom.xpath("//input[@name='__VIEWSTATE']/@value").get(),
            "__VIEWSTATEGENERATOR": checkout_dom.xpath("//input[@name='__VIEWSTATEGENERATOR']/@value").get(),
            "SideMenuControl1000txtItemCodeId": "",
            "SideMenuControl1000txtItemQtyId": "",
            "ctl00$ucHeader$ucSearchBarHeaderbar$txtSearch": "",
            "SideMenuControl1000txtItemCodeId9": "",
            "SideMenuControl1000txtItemQtyId9": "",
            "ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemCodeId": "",
            "ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemQtyId": "",
            "layout": "on",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ddlShippingMethod": shipping_method_value,
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ddlPaymentMethod": checkout_dom.xpath(
                "//select[@name='ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ddlPaymentMethod']"
                "/option[@selected]/@value"
            ).get(),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$hiddenModifyLink": (
                "https://www.henryschein.com/us-en/checkout/CheckoutCreditCard.aspx?action=0&ccid={0}&overlay=true"
            ),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$txtPo": checkout_dom.xpath(
                "//input[@id='ctl00_cphMainContentHarmony_ucOrderPaymentAndOptionsShop_txtPo']/@value"
            ).get(),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$": "rbnNoDelayNoRecurring",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$dpStartDate": (
                checkout_dom.xpath(
                    "//input[@name='ctl00$cphMainContentHarmony"
                    "$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$dpStartDate']/@value"
                ).get()
            ),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$ddlFrequency": "Weekly",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$dpEndDate": (
                checkout_dom.xpath(
                    "//input[@name='ctl00$cphMainContentHarmony"
                    "$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$dpEndDate']/@value"
                ).get()
            ),
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$ddlTotal": "Select One",
            "ctl00$cphMainContentHarmony$ucOrderPaymentAndOptionsShop$ucSchedulingOptions$checkoutType": "Normal",
            "dest": "",
        }

        params = {
            "PaymentIndex": "0",
        }

        headers = CHECKOUT_HEADER.copy()
        headers["referer"] = "https://www.henryschein.com/us-en/Checkout/BillingShipping.aspx"
        async with self.session.post(
            "https://www.henryschein.com/us-en/Checkout/BillingShipping.aspx",
            headers=headers,
            params=params,
            data=data,
        ) as resp:
            return Selector(text=await resp.text())

    async def review_order(self, review_checkout_dom: Selector) -> types.VendorOrderDetail:
        subtotal_amount = convert_string_to_price(
            review_checkout_dom.xpath(
                "//div[@id='ctl00_cphMainContentHarmony_divOrderSummarySubTotal']/strong//text()"
            ).get()
        )
        shipping_amount = convert_string_to_price(
            review_checkout_dom.xpath(
                "//div[@id='ctl00_cphMainContentHarmony_divOrderSummaryShipping']/strong//text()"
            ).get()
        )
        tax_amount = convert_string_to_price(
            review_checkout_dom.xpath(
                "//div[@id='ctl00_cphMainContentHarmony_divOrderSummaryTax']/strong//text()"
            ).get()
        )
        total_amount = convert_string_to_price(
            review_checkout_dom.xpath(
                "//div[@id='ctl00_cphMainContentHarmony_divOrderSummaryTotal']/strong//text()"
            ).get()
        )
        payment_method = strip_whitespaces(
            review_checkout_dom.xpath(
                "//div[@id='ctl00_cphMainContentHarmony_divOrderSummaryPaymentMethod']/strong//text()"
            ).get()
        )
        shipping_address = concatenate_strings(
            review_checkout_dom.xpath(
                "//section[contains(@class, 'order-details')]"
                "//section[contains(@class, 'half')]/div[@class='half'][1]//address/p/span[2]/text()",
            ).extract(),
            delimeter=", ",
        )

        return types.VendorOrderDetail(
            subtotal_amount=subtotal_amount,
            shipping_amount=shipping_amount,
            tax_amount=tax_amount,
            total_amount=total_amount,
            payment_method=payment_method,
            shipping_address=shipping_address,
        )

    async def checkout_and_review_order(self, shipping_method: Optional[str] = None) -> dict:
        """Review the order without making real order"""
        checkout_dom = await self.checkout()
        review_checkout_dom = await self.review_checkout(checkout_dom, shipping_method)
        order_detail = await self.review_order(review_checkout_dom)
        return {
            "order_detail": order_detail,
            "review_checkout_dom": review_checkout_dom,
        }

    async def place_order(self, *args, **kwargs) -> str:
        review_checkout_dom = kwargs.get("review_checkout_dom")
        headers = CHECKOUT_HEADER.copy()
        headers["referer"] = "https://www.henryschein.com/us-en/Checkout/OrderReview.aspx"

        data = {
            "ctl00_ScriptManager_TSM": ";;System.Web.Extensions, Version=4.0.0.0, Culture=neutral, "
            "PublicKeyToken=31bf3856ad364e35:en-US:f319b152-218f-4c14-829d-050a68bb1a61:ea597d4b:b25378d2",
            "__EVENTTARGET": "ctl00$cphMainContentHarmony$lnkNextShop",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": review_checkout_dom.xpath("//input[@name='__VIEWSTATE']/@value").get(),
            "__VIEWSTATEGENERATOR": review_checkout_dom.xpath("//input[@name='__VIEWSTATEGENERATOR']/@value").get(),
            "ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemCodeId": "",
            "ctl00_cpAsideMenu_AsideMenu_SideMenuControl1000txtItemQtyId": "",
            "layout": "on",
            "dest": "",
        }
        data.update(self.get_checkout_products_sensitive_data(review_checkout_dom))

        async with self.session.post(
            "https://www.henryschein.com/us-en/Checkout/OrderReview.aspx", headers=headers, data=data
        ) as resp:
            response = await resp.text()
            res_data = response.split("dataLayer.push(", 1)[1].split(");")[0]
            res_data = res_data.replace("'", '"')
            res_data = json.loads(res_data)
            return res_data["ecommerce"]["purchase"]["actionField"]["id"]

    async def _get_products_prices(self, products: List[types.Product], *args, **kwargs) -> Dict[str, Decimal]:
        """get vendor specific products prices"""
        keyword = kwargs.get("keyword", "")
        data = {
            "ItemArray": json.dumps(
                {
                    "ItemDataToPrice": [
                        {
                            "ProductId": int(product["product_id"]),
                            "Qty": "1",
                            "Uom": product["unit"],
                            "PromoCode": "",
                            "CatalogName": "B_DENTAL",
                            "ForceUpdateInventoryStatus": False,
                            "AvailabilityCode": "01",
                        }
                        for product in products
                    ],
                }
            ),
            "searchType": "6",
            "did": "dental",
            "catalogName": "B_DENTAL",
            "endecaCatalogName": "DENTAL",
            "culture": "us-en",
            "showPriceToAnonymousUserFromCMS": "False",
            "isCallingFromCMS": "False",
        }

        headers = GET_PRODUCT_PRICES_HEADERS.copy()
        headers["referer"] = f"https://www.henryschein.com/us-en/Search.aspx?searchkeyWord={keyword}"
        product_prices = {}
        async with self.session.post(
            "https://www.henryschein.com/webservices/JSONRequestHandler.ashx",
            data=data,
            headers=headers,
        ) as resp:
            res = await resp.json()
            for product_price in res["ItemDataToPrice"]:
                if product_price["InventoryStatus"] in ["Unavailable", "Error", "Discontinued", "Unknown"]:
                    continue
                product_prices[product_price["ProductId"]] = Decimal(product_price["CustomerPrice"])
        return product_prices
