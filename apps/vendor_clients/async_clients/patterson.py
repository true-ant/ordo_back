import json
import logging
from decimal import Decimal
from http.cookies import SimpleCookie
from typing import Optional, Union
from urllib.parse import urlencode

from aiohttp import ClientResponse
from scrapy import Selector

from apps.orders.models import OfficeProduct
from apps.orders.updater import STATUS_ACTIVE, STATUS_UNAVAILABLE
from apps.vendor_clients import errors, types
from apps.vendor_clients.async_clients.base import BaseClient, EmptyResults, PriceInfo
from apps.vendor_clients.headers.patterson import (
    ADD_PRODUCT_CART_HEADERS,
    CLEAR_CART_HEADERS,
    GET_CART_HEADERS,
    GET_PRODUCT_PAGE_HEADERS,
    HOME_HEADERS,
    LOGIN_HEADERS,
    LOGIN_HOOK_HEADER,
    LOGIN_HOOK_HEADER2,
    PRE_LOGIN_HEADERS,
)

logger = logging.getLogger(__name__)


class PattersonClient(BaseClient):
    VENDOR_SLUG = "patterson"
    GET_PRODUCT_PAGE_HEADERS = GET_PRODUCT_PAGE_HEADERS

    async def get_login_data(self, *args, **kwargs) -> Optional[types.LoginInformation]:
        async with self.session.get(url="https://www.pattersondental.com/", headers=HOME_HEADERS) as resp:
            params = {
                "returnUrl": "/",
                "signIn": "userSignIn",
            }
            async with self.session.get(
                url="https://www.pattersondental.com/Account", headers=PRE_LOGIN_HEADERS, params=params
            ) as resp:
                login_url = str(resp.url)
                text = await resp.text()
                settings_content = text.split("var SETTINGS")[1].split(";")[0].strip(" =")
                settings = json.loads(settings_content)
                csrf = settings.get("csrf", "")
                transId = settings.get("transId", "")
                policy = settings.get("hosts", {}).get("policy", "")
                diag = {"pageViewId": settings.get("pageViewId", ""), "pageId": "CombinedSigninAndSignup", "trace": []}

                headers = LOGIN_HEADERS.copy()
                headers["Referer"] = login_url
                headers["X-CSRF-TOKEN"] = csrf

                params = (
                    ("tx", transId),
                    ("p", policy),
                )
                url = (
                    "https://pattersonb2c.b2clogin.com/pattersonb2c.onmicrosoft.com/"
                    "B2C_1A_PRODUCTION_Dental_SignInWithPwReset/SelfAsserted?" + urlencode(params)
                )

                data = {
                    "signInName": self.username,
                    "password": self.password,
                    "request_type": "RESPONSE",
                    "diag": diag,
                    "login_page_link": login_url,
                    "transId": transId,
                    "csrf": csrf,
                    "policy": policy,
                }

                return {
                    "url": url,
                    "headers": headers,
                    "data": data,
                }

    async def check_authenticated(self, resp: ClientResponse) -> bool:
        text = await resp.text()
        dom = Selector(text=text)
        return True if dom.xpath("//a[@href='/Account/LogOff']") else False

    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> Optional[SimpleCookie]:
        login_info = await self.get_login_data()
        logger.debug("Got logger data: %s", login_info)
        if login_info:
            async with self.session.post(
                url=login_info["url"], headers=login_info["headers"], data=login_info["data"]
            ) as resp:
                transId = login_info["data"]["transId"]
                policy = login_info["data"]["policy"]
                csrf = login_info["data"]["csrf"]
                diag = login_info["data"]["diag"]

                headers = LOGIN_HOOK_HEADER.copy()
                headers["Referer"] = login_info["data"]["login_page_link"]

                params = (
                    ("tx", transId),
                    ("p", policy),
                    ("rememberMe", "false"),
                    ("csrf_token", csrf),
                    ("diags", urlencode(diag)),
                )
                url = (
                    "https://pattersonb2c.b2clogin.com/pattersonb2c.onmicrosoft.com/"
                    "B2C_1A_PRODUCTION_Dental_SignInWithPwReset/api/CombinedSigninAndSignup/confirmed?"
                    + urlencode(params)
                )

                logger.debug("Logging in...")
                async with self.session.get(url, headers=headers) as resp:
                    print("Login Confirmed: ", resp.status)
                    text = await resp.text()
                    dom = Selector(text=text)
                    state = dom.xpath('//input[@name="state"]/@value').get()
                    code = dom.xpath('//input[@name="code"]/@value').get()
                    id_token = dom.xpath('//input[@name="id_token"]/@value').get()

                    headers = LOGIN_HOOK_HEADER2.copy()

                    data = {
                        "state": state,
                        "code": code,
                        "id_token": id_token,
                    }

                    async with self.session.post(
                        url="https://www.pattersondental.com/Account/LogOnPostProcessing/",
                        headers=headers,
                        data=data,
                    ) as resp:
                        async with self.session.get(
                            url="https://www.pattersondental.com/supplies/deals",
                            headers=HOME_HEADERS,
                            data=data,
                        ) as resp:
                            if resp.status != 200:
                                content = await resp.read()
                                logger.debug("Got %s status, content = %s", resp.status, content)
                                raise errors.VendorAuthenticationFailed()

                            is_authenticated = await self.check_authenticated(resp)
                            if not is_authenticated:
                                logger.debug("Still not authenticated")
                                raise errors.VendorAuthenticationFailed()

                            if hasattr(self, "after_login_hook"):
                                await self.after_login_hook(resp)

                            logger.info("Successfully logged in")

            return resp.cookies

    async def get_cart_page(self) -> Union[Selector, dict]:
        return await self.get_response_as_json(
            url="https://www.pattersondental.com/ShoppingCart/CartItemQuantities",
            headers=GET_CART_HEADERS,
        )

    async def clear_cart(self):
        products = await self.get_cart_page()
        data = []
        for product in products:
            data.append(
                {
                    "OrderItemId": product["OrderItemId"],
                    "ParentItemId": None,
                    "PublicItemNumber": product["PublicItemNumber"],
                    "PersistentItemNumber": "",
                    "ItemQuantity": product["ItemQuantity"],
                    "BasePrice": None,
                    "ItemPriceBreaks": None,
                    "UnitPriceOverride": None,
                    "IsLabelItem": False,
                    "IsTagItem": False,
                    "ItemDescription": "",
                    "UseMyCatalogQuantity": False,
                    "UnitPrice": product["UnitPrice"],
                    "ItemSubstitutionReasonModel": None,
                    "NavInkConfigurationId": None,
                    "CanBePersonalized": False,
                    "HasBeenPersonalized": False,
                    "Manufacturer": False,
                }
            )
        await self.session.post(
            url="https://www.pattersondental.com/ShoppingCart/RemoveItemsFromShoppingCart",
            headers=CLEAR_CART_HEADERS,
            json=data,
        )

    async def add_product_to_cart(self, product: types.CartProduct, *args, **kwargs):
        data = {
            "itemNumbers": product["product"]["product_id"],
            "loadItemType": "ShoppingCart",
        }
        await self.session.post(
            "https://www.pattersondental.com/Item/ValidateItems",
            headers=ADD_PRODUCT_CART_HEADERS,
            data=json.dumps(data),
        )
        data = [
            {
                "OrderItemId": None,
                "ParentItemId": None,
                "PublicItemNumber": product["product"]["product_id"],
                "PersistentItemNumber": None,
                "ItemQuantity": product["quantity"],
                "BasePrice": None,
                "ItemPriceBreaks": None,
                "UnitPriceOverride": None,
                "IsLabelItem": False,
                "IsTagItem": False,
                "ItemDescription": None,
                "UseMyCatalogQuantity": False,
                "UnitPrice": 0,
                "ItemSubstitutionReasonModel": None,
                "NavInkConfigurationId": None,
                "CanBePersonalized": False,
                "HasBeenPersonalized": False,
                "Manufacturer": False,
            }
        ]

        await self.session.post(
            "https://www.pattersondental.com/ShoppingCart/AddItemsToCart",
            headers=ADD_PRODUCT_CART_HEADERS,
            data=json.dumps(data),
        )

    async def get_product_price_v2(self, product: OfficeProduct) -> PriceInfo:
        resp = await self.session.get(url=product.product.url, headers=GET_PRODUCT_PAGE_HEADERS)
        logger.debug("Response status: %s", resp.status)
        logger.debug("Product ID: %s", product.product.product_id)

        text = await resp.text()
        if resp.status != 200:
            logger.debug("Got response: %s", text)
            raise EmptyResults()
        page_response_dom = Selector(text=text)
        products = page_response_dom.xpath('//div[@id="ItemDetailImageAndDescriptionRow"]')
        if products:
            if "ProductFamilyDetails" in product.product.url:
                for product_dom in page_response_dom.xpath('//div[@id="productFamilyDetailsGridBody"]'):
                    mfg_number = product_dom.xpath(
                        './/div[@id="productFamilyDetailsGridBodyColumnTwoInnerRowMfgNumber"]//text()'
                    ).get()
                    price = product_dom.xpath(
                        './/div[contains(@class, "productFamilyDetailsPriceBreak")][1]//text()'
                    ).get()
                    if "/" in price:
                        price = price.split("/")[0].strip()
                    if product["mfg_number"] == mfg_number:
                        product_vendor_status = STATUS_ACTIVE
                        return PriceInfo(price=price, product_vendor_status=product_vendor_status)
            else:
                item_data = json.loads(page_response_dom.xpath('//input[@name="ItemSkuDetail"]/@value').get())
                price = item_data.get("ItemPrice", 0)
                product_vendor_status = STATUS_ACTIVE
                return PriceInfo(price=price, product_vendor_status=product_vendor_status)
        else:
            product_vendor_status = STATUS_UNAVAILABLE
            return PriceInfo(price=0, product_vendor_status=product_vendor_status)

    def serialize(self, base_product: types.Product, data: Union[dict, Selector]) -> Optional[types.Product]:
        product_detail = data.xpath("//input[@id='ItemSkuDetail']/@value").get()
        try:
            product_detail = json.loads(product_detail)
            product_id = product_detail["PublicItemNumber"]
            return {
                "vendor": self.VENDOR_SLUG,
                "product_id": product_id,
                "sku": product_id,
                "name": product_detail["ItemDescription"],
                "url": f"https://www.pattersondental.com/Supplies/ItemDetail/{product_id}",
                "images": [
                    f"https://content.pattersondental.com/items/LargeSquare/images/{image['AssetFilename']}"
                    for image in product_detail["Images"]
                ],
                "price": Decimal(str(product_detail["UnitPrice"]) if not product_detail["UnitPrice"] else 0),
                "product_vendor_status": "",
                "category": "",
                "unit": "",
            }
        except (TypeError, json.decoder.JSONDecodeError):
            print("Patterson/TypeError")
            pass

    async def checkout_and_review_order(self, shipping_method: Optional[str] = None) -> dict:
        pass
